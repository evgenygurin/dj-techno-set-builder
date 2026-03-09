"""Curation tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.mcp.dependencies import (
    get_features_service,
    get_set_service,
    get_track_service,
    get_unified_scoring,
)
from app.mcp.resolve import resolve_local_id
from app.mcp.tools._scoring_helpers import score_consecutive_transitions
from app.mcp.types import (
    ClassifyResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)
from app.services.features import AudioFeaturesService
from app.services.set_curation import SetCurationService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.mood_classifier import TrackMood
from app.utils.audio.set_templates import TemplateName, get_template


def register_curation_tools(mcp: FastMCP) -> None:
    """Register curation tools on the MCP server."""

    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation"})
    async def classify_tracks(
        ctx: Context,
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> ClassifyResult:
        """Classify all analyzed tracks into 6 mood categories.

        Uses rule-based classifier on audio features (BPM, LUFS,
        kick prominence, spectral centroid, onset rate, HP ratio).

        Returns mood distribution across all tracks with features.
        """
        all_features = await features_svc.list_all()
        svc = SetCurationService()
        classified = svc.classify_features(all_features)
        dist = svc.mood_distribution(classified)

        total = sum(dist.values())
        distribution = [
            MoodDistribution(
                mood=mood.value,
                count=count,
                percentage=round(count / total * 100, 1) if total > 0 else 0.0,
            )
            for mood, count in sorted(dist.items(), key=lambda x: x[0].intensity)
        ]

        return ClassifyResult(
            total_classified=total,
            distribution=distribution,
        )

    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation"})
    async def analyze_library_gaps(
        ctx: Context,
        template: str = "classic_60",
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> LibraryGapResult:
        """Analyze library for gaps relative to a set template.

        Compares current mood distribution with what the template needs.
        Returns deficit per mood category and recommendations.

        Args:
            template: Template to compare against (default: classic_60).
        """
        all_features = await features_svc.list_all()
        svc = SetCurationService()
        classified = svc.classify_features(all_features)
        dist = svc.mood_distribution(classified)
        total = sum(dist.values())

        tmpl = get_template(TemplateName(template))

        # Count required per mood from template slots
        needed: dict[TrackMood, int] = {m: 0 for m in TrackMood}
        for slot in tmpl.slots:
            needed[slot.mood] += 1

        gaps: list[GapDescription] = []
        recommendations: list[str] = []
        for mood in TrackMood.energy_order():
            avail = dist.get(mood, 0)
            need = needed.get(mood, 0)
            if need > avail:
                deficit = need - avail
                gaps.append(
                    GapDescription(
                        mood=mood.value,
                        needed=need,
                        available=avail,
                        deficit=deficit,
                    )
                )
                recommendations.append(
                    f"Add {deficit} {mood.value} tracks (need {need}, have {avail})"
                )

        distribution = [
            MoodDistribution(
                mood=mood.value,
                count=dist.get(mood, 0),
                percentage=(round(dist.get(mood, 0) / total * 100, 1) if total > 0 else 0.0),
            )
            for mood in TrackMood.energy_order()
        ]

        return LibraryGapResult(
            total_tracks=len(all_features),
            tracks_with_features=total,
            mood_distribution=distribution,
            gaps=gaps,
            recommendations=recommendations,
        )

    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation", "setbuilder"}, timeout=120)
    async def review_set(
        set_ref: str | int,
        version_id: int,
        ctx: Context,
        template: str = "classic_60",
        set_svc: DjSetService = Depends(get_set_service),
        unified_svc: UnifiedTransitionScoringService = Depends(get_unified_scoring),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        track_svc: TrackService = Depends(get_track_service),
    ) -> SetReviewResult:
        """Review a DJ set version — identify weak spots and suggest improvements.

        Analyses transitions, energy arc, and mood variety. Returns
        weak transitions (score < 0.4), energy plateaus, and suggestions.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            version_id: Set version to review.
            template: Template to compare energy arc against (default: classic_60).
        """
        from app.utils.audio.set_generator import TrackData, lufs_to_energy, variety_score

        set_id = resolve_local_id(set_ref, "set")
        set_obj = await set_svc.get(set_id)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)

        # Use set's template if available, otherwise fall back to provided template
        actual_template = set_obj.template_name or template
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        if len(items) < 2:
            return SetReviewResult(
                overall_score=0.0,
                energy_arc_adherence=0.0,
                variety_score=0.0,
                weak_transitions=[],
                suggestions=["Set too short"],
            )

        svc = SetCurationService()

        # Score all transitions via shared helper
        score_results = await score_consecutive_transitions(
            items, unified_svc, track_svc, features_svc
        )

        weak: list[WeakTransition] = []
        scores: list[float] = []
        for i, sr in enumerate(score_results):
            scores.append(sr.total)
            if sr.total < 0.4:
                weak.append(
                    WeakTransition(
                        position=i,
                        from_track_id=sr.from_track_id,
                        to_track_id=sr.to_track_id,
                        score=round(sr.total, 3),
                        reason=("Low transition quality" if sr.total > 0 else "Missing features"),
                    )
                )

        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Variety scoring
        all_features = await features_svc.list_all()
        feat_map = {f.track_id: f for f in all_features}
        classified = svc.classify_features(all_features)

        track_data_list = []
        for item in items:
            feat = feat_map.get(item.track_id)
            mood_int = classified.get(item.track_id, TrackMood.DRIVING).intensity
            if feat:
                track_data_list.append(
                    TrackData(
                        track_id=item.track_id,
                        bpm=feat.bpm,
                        energy=lufs_to_energy(feat.lufs_i),
                        key_code=feat.key_code or 0,
                        mood=mood_int,
                    )
                )
        var_score = variety_score(track_data_list) if track_data_list else 0.0

        # Energy arc adherence: compare actual LUFS curve to template
        # Preserve original set positions - use None for missing features
        track_lufs_with_positions: list[float | None] = []
        for item in items:
            if item.track_id in feat_map:
                track_lufs_with_positions.append(feat_map[item.track_id].lufs_i)
            else:
                # For missing features, use None to mark gaps
                track_lufs_with_positions.append(None)

        # Compute arc score only if we have enough tracks with features
        if sum(1 for x in track_lufs_with_positions if x is not None) >= 2:
            arc_score = svc.compute_energy_arc_adherence_with_gaps(
                track_lufs_with_positions, actual_template
            )
        else:
            arc_score = 0.0

        suggestions: list[str] = []
        if weak:
            suggestions.append(f"{len(weak)} weak transitions (score < 0.4)")
        if var_score < 0.7:
            suggestions.append("Low variety — consider diversifying mood/key sequences")
        if arc_score < 0.5:
            suggestions.append(
                f"Energy arc adherence is low ({arc_score:.1%}) — "
                f"set does not follow {actual_template} template energy curve"
            )

        return SetReviewResult(
            overall_score=round(avg_score, 3),
            energy_arc_adherence=arc_score,
            variety_score=round(var_score, 3),
            weak_transitions=weak,
            suggestions=suggestions,
        )
