"""Curation tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.mcp.dependencies import get_features_service
from app.mcp.types_curation import (
    ClassifyResult,
    CurateCandidate,
    CurateSetResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
)
from app.services.features import AudioFeaturesService
from app.services.set_curation import SetCurationService
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

    @mcp.tool(tags={"curation"})
    async def curate_set(
        template: str,
        ctx: Context,
        target_count: int | None = None,
        exclude_track_ids: list[int] | None = None,
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> CurateSetResult:
        """Select tracks for a set template using mood-based slot matching.

        Available templates: warm_up_30, classic_60, peak_hour_60,
        roller_90, progressive_120, wave_120, closing_60, full_library.

        Args:
            template: Template name (e.g. "classic_60").
            target_count: Override template's default track count.
            exclude_track_ids: Track IDs to exclude from selection.
        """
        await ctx.report_progress(progress=0, total=100)

        # Load features
        all_features = await features_svc.list_all()

        svc = SetCurationService()
        exclude = set(exclude_track_ids or [])

        await ctx.report_progress(progress=30, total=100)

        candidates = svc.select_candidates(
            all_features,
            template_name=template,
            exclude_ids=exclude,
            target_count=target_count,
        )

        await ctx.report_progress(progress=80, total=100)

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

        tmpl = get_template(TemplateName(template))
        warnings: list[str] = []
        if len(candidates) < len(tmpl.slots):
            warnings.append(
                f"Only {len(candidates)} tracks matched, "
                f"template needs {len(tmpl.slots)} slots"
            )

        await ctx.report_progress(progress=100, total=100)

        return CurateSetResult(
            template=template,
            target_count=tmpl.target_track_count,
            selected_count=len(candidates),
            candidates=[
                CurateCandidate(
                    track_id=c.track_id,
                    mood=c.mood.value,
                    slot_score=round(c.slot_score, 3),
                    bpm=c.bpm,
                    lufs_i=c.lufs_i,
                )
                for c in candidates
            ],
            mood_distribution=distribution,
            warnings=warnings,
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
                percentage=(
                    round(dist.get(mood, 0) / total * 100, 1) if total > 0 else 0.0
                ),
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
