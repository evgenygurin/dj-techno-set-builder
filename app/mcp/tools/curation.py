"""Curation tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.core.errors import NotFoundError
from app.domain.audio.classifier.classifier import TrackMood
from app.domain.setbuilder.templates import TemplateName, get_template
from app.mcp.dependencies import (
    get_features_service,
    get_playlist_service,
    get_set_service,
    get_track_service,
    get_unified_scoring,
)
from app.mcp.providers._scoring_helpers import score_consecutive_transitions
from app.mcp.resolve import resolve_local_id
from app.mcp.types import (
    ClassifyResult,
    DistributeResult,
    GapDescription,
    LibraryGapResult,
    MoodDistribution,
    SetReviewResult,
    WeakTransition,
)
from app.schemas.playlists import DjPlaylistCreate, DjPlaylistItemCreate
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.set_curation import SetCurationService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService


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
        from app.domain.setbuilder.genetic.engine import TrackData, lufs_to_energy, variety_score

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

    @mcp.tool(
        tags={"curation"},
        annotations={"readOnlyHint": True},
        timeout=120,
    )
    async def audit_playlist(
        playlist_id: int,
        ctx: Context,
        features_svc: AudioFeaturesService = Depends(get_features_service),
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
        track_svc: TrackService = Depends(get_track_service),
    ) -> dict[str, object]:
        """Audit all playlist tracks against techno audio quality criteria.

        Checks BPM (120-155), LUFS (-20 to -4), energy, onset rate,
        kick prominence, spectral centroid, tempo confidence, etc.
        Reports which tracks pass and which fail with reasons.

        Args:
            playlist_id: Local playlist ID to audit.
        """
        items_result = await playlist_svc.list_items(playlist_id, offset=0, limit=1000)
        items = items_result.items
        total = len(items)

        passed = 0
        no_features = 0
        failures: list[dict[str, object]] = []

        for i, item in enumerate(items):
            await ctx.report_progress(progress=i, total=total)

            # Get track title for reporting
            try:
                track = await track_svc.get(item.track_id)
                title = track.title
            except NotFoundError:
                title = f"track#{item.track_id}"

            # Get latest features
            try:
                feat = await features_svc.get_latest(item.track_id)
            except NotFoundError:
                no_features += 1
                continue

            reasons: list[str] = []

            # BPM: 120-155
            if feat.bpm < 120:
                reasons.append(f"BPM {feat.bpm:.1f} < 120")
            elif feat.bpm > 155:
                reasons.append(f"BPM {feat.bpm:.1f} > 155")

            # LUFS: -20 to -4
            if feat.lufs_i < -20:
                reasons.append(f"LUFS {feat.lufs_i:.1f} < -20")
            elif feat.lufs_i > -4:
                reasons.append(f"LUFS {feat.lufs_i:.1f} > -4")

            # energy_mean > 0.05
            if feat.energy_mean <= 0.05:
                reasons.append(f"energy {feat.energy_mean:.3f} <= 0.05")

            # onset_rate_mean > 1.0
            if feat.onset_rate_mean is not None and feat.onset_rate_mean <= 1.0:
                reasons.append(f"onset_rate {feat.onset_rate_mean:.2f} <= 1.0")

            # kick_prominence > 0.05
            if feat.kick_prominence is not None and feat.kick_prominence <= 0.05:
                reasons.append(f"kick {feat.kick_prominence:.3f} <= 0.05")

            # centroid: 300-10000 Hz
            if feat.centroid_mean_hz is not None:
                if feat.centroid_mean_hz < 300:
                    reasons.append(f"centroid {feat.centroid_mean_hz:.0f}Hz < 300")
                elif feat.centroid_mean_hz > 10000:
                    reasons.append(f"centroid {feat.centroid_mean_hz:.0f}Hz > 10000")

            # flatness < 0.5
            if feat.flatness_mean is not None and feat.flatness_mean >= 0.5:
                reasons.append(f"flatness {feat.flatness_mean:.3f} >= 0.5")

            # tempo_confidence > 0.3
            if feat.tempo_confidence <= 0.3:
                reasons.append(f"tempo_conf {feat.tempo_confidence:.2f} <= 0.3")

            # bpm_stability > 0.3
            if feat.bpm_stability <= 0.3:
                reasons.append(f"bpm_stab {feat.bpm_stability:.2f} <= 0.3")

            # pulse_clarity > 0.02
            if feat.pulse_clarity is not None and feat.pulse_clarity <= 0.02:
                reasons.append(f"pulse {feat.pulse_clarity:.3f} <= 0.02")

            # hp_ratio < 8.0
            if feat.hp_ratio is not None and feat.hp_ratio >= 8.0:
                reasons.append(f"hp_ratio {feat.hp_ratio:.2f} >= 8.0")

            if reasons:
                failures.append(
                    {
                        "track_id": item.track_id,
                        "title": title,
                        "reasons": reasons,
                    }
                )
            else:
                passed += 1

        await ctx.report_progress(progress=total, total=total)

        return {
            "playlist_id": playlist_id,
            "total_tracks": total,
            "passed": passed,
            "failed": len(failures),
            "no_features": no_features,
            "failures": failures,
        }

    # -- Subgenre display names for playlist creation/lookup --
    subgenre_display: dict[str, str] = {
        "ambient_dub": "Techno: Ambient Dub",
        "dub_techno": "Techno: Dub Techno",
        "minimal": "Techno: Minimal",
        "detroit": "Techno: Detroit",
        "melodic_deep": "Techno: Melodic Deep",
        "progressive": "Techno: Progressive",
        "hypnotic": "Techno: Hypnotic",
        "driving": "Techno: Driving",
        "tribal": "Techno: Tribal",
        "breakbeat": "Techno: Breakbeat",
        "peak_time": "Techno: Peak Time",
        "acid": "Techno: Acid",
        "raw": "Techno: Raw",
        "industrial": "Techno: Industrial",
        "hard_techno": "Techno: Hard Techno",
    }

    @mcp.tool(tags={"curation"}, timeout=300)
    async def distribute_to_subgenres(
        playlist_id: int,
        ctx: Context,
        features_svc: AudioFeaturesService = Depends(get_features_service),
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> DistributeResult:
        """Classify all playlist tracks by mood and distribute to subgenre playlists.

        Uses the 15-subgenre mood classifier to categorize each track,
        then adds it to the corresponding local subgenre playlist.
        Tracks already in their target playlist are skipped.
        Missing subgenre playlists are created automatically.

        Args:
            playlist_id: Source playlist ID to distribute from.
        """
        # Stage 1: load playlist items and features
        await ctx.info("Stage 1/3 — loading playlist tracks and features...")
        await ctx.report_progress(progress=0, total=3)

        items_result = await playlist_svc.list_items(playlist_id, offset=0, limit=5000)
        track_ids = {item.track_id for item in items_result.items}

        all_features = await features_svc.list_all()

        # Stage 2: classify tracks
        await ctx.info("Stage 2/3 — classifying tracks by mood...")
        await ctx.report_progress(progress=1, total=3)

        svc = SetCurationService()
        playlist_features = [f for f in all_features if f.track_id in track_ids]
        classified = svc.classify_features(playlist_features)

        no_features = len(track_ids) - len(classified)
        distribution: dict[str, int] = {}
        for mood in classified.values():
            distribution[mood.value] = distribution.get(mood.value, 0) + 1

        # Stage 3: route to subgenre playlists
        await ctx.info("Stage 3/3 — routing tracks to subgenre playlists...")
        await ctx.report_progress(progress=2, total=3)

        # Build mood -> target playlist mapping
        all_playlists = await playlist_svc.list(offset=0, limit=200)
        name_to_playlist: dict[str, int] = {p.name: p.playlist_id for p in all_playlists.items}

        mood_to_playlist_id: dict[str, int] = {}
        for mood_val, display_name in subgenre_display.items():
            if display_name in name_to_playlist:
                mood_to_playlist_id[mood_val] = name_to_playlist[display_name]
            else:
                new_pl = await playlist_svc.create(DjPlaylistCreate(name=display_name))
                mood_to_playlist_id[mood_val] = new_pl.playlist_id

        # Load existing items for target playlists to skip duplicates
        existing_tracks: dict[int, set[int]] = {}
        for pl_id in mood_to_playlist_id.values():
            pl_items = await playlist_svc.list_items(pl_id, offset=0, limit=5000)
            existing_tracks[pl_id] = {i.track_id for i in pl_items.items}

        added = 0
        already = 0
        total_tracks = len(classified)

        for i, (track_id, mood) in enumerate(classified.items()):
            if i % 50 == 0 and total_tracks > 50:
                await ctx.info(f"Routing track {i + 1}/{total_tracks}...")

            target_pl_id = mood_to_playlist_id[mood.value]
            existing = existing_tracks.get(target_pl_id, set())

            if track_id in existing:
                already += 1
                continue

            sort_idx = len(existing)
            await playlist_svc.add_item(
                target_pl_id,
                DjPlaylistItemCreate(track_id=track_id, sort_index=sort_idx),
            )
            existing.add(track_id)
            added += 1

        await ctx.report_progress(progress=3, total=3)

        return DistributeResult(
            total_classified=len(classified),
            no_features=no_features,
            distribution=distribution,
            added_to_playlists=added,
            already_in_playlist=already,
        )
