"""Set builder tools for DJ workflow MCP server."""

from __future__ import annotations

import types

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError, ValidationError
from app.mcp.dependencies import (
    get_features_service,
    get_playlist_service,
    get_set_generation_service,
    get_set_service,
    get_track_service,
    get_unified_scoring,
)
from app.mcp.resolve import resolve_local_id
from app.mcp.session_state import save_build_result
from app.mcp.tools._scoring_helpers import score_consecutive_transitions
from app.mcp.types import SetBuildResult, TransitionScoreResult
from app.schemas.set_generation import SetGenerationRequest
from app.schemas.sets import DjSetCreate, DjSetItemCreate, DjSetVersionCreate
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.feature_conversion import orm_to_track_data
from app.utils.audio.greedy_chain import build_greedy_chain


async def _run_greedy_build(
    *,
    playlist_id: int,
    set_id: int,
    energy_arc: str,
    track_count: int,
    exclude_track_ids: list[int] | None,
    set_svc: DjSetService,
    features_svc: AudioFeaturesService,
    playlist_svc: DjPlaylistService,
    ctx: Context,
) -> SetBuildResult:
    """Run greedy chain builder and persist results as a new set version.

    Loads features from DB, converts to TrackData, calls build_greedy_chain,
    then creates DjSetVersion + DjSetItems via set_svc.
    """
    # Load all features (latest per track)
    all_features = await features_svc.list_all()
    if not all_features:
        raise ValidationError("No tracks with audio features available")

    # Filter to playlist tracks
    playlist_items = await playlist_svc.list_items(playlist_id, offset=0, limit=5000)
    allowed_ids = {item.track_id for item in playlist_items.items}
    all_features = [f for f in all_features if f.track_id in allowed_ids]

    if not all_features:
        raise ValidationError(f"No tracks with audio features in playlist {playlist_id}")

    # Exclude tracks
    if exclude_track_ids:
        excluded_set = set(exclude_track_ids)
        all_features = [f for f in all_features if f.track_id not in excluded_set]
        if not all_features:
            raise ValidationError("All tracks were excluded")

    # Convert to TrackData via unified converter (includes mood classification)
    tracks = [orm_to_track_data(f) for f in all_features]

    await ctx.report_progress(progress=30, total=100)
    await ctx.info(f"Loaded {len(tracks)} tracks, running greedy chain...")

    # Run greedy chain
    chain_result = build_greedy_chain(
        tracks=tracks,
        track_count=track_count,
        energy_arc=energy_arc,
        bpm_tolerance=4.0,
    )

    await ctx.report_progress(progress=70, total=100)

    # Create version + items via set service
    version_data = DjSetVersionCreate(
        version_label=f"greedy-{len(chain_result.track_ids)}t",
        generator_run={
            "algorithm": "greedy",
            "track_count": len(chain_result.track_ids),
            "energy_arc": energy_arc,
            "avg_score": chain_result.avg_score,
            "min_score": chain_result.min_score,
        },
        score=chain_result.avg_score,
    )
    version = await set_svc.create_version(set_id, version_data)

    for sort_index, tid in enumerate(chain_result.track_ids):
        item_data = DjSetItemCreate(sort_index=sort_index, track_id=tid)
        await set_svc.add_item(version.set_version_id, item_data)

    return SetBuildResult(
        set_id=set_id,
        version_id=version.set_version_id,
        track_count=len(chain_result.track_ids),
        total_score=chain_result.avg_score,
        avg_transition_score=chain_result.avg_score,
        energy_curve=[],
    )


def register_setbuilder_tools(mcp: FastMCP) -> None:
    """Register set builder tools on the MCP server."""

    @mcp.tool(tags={"setbuilder"}, timeout=600, annotations={"openWorldHint": True})
    async def build_set(
        playlist_ref: str | int,
        set_name: str,
        ctx: Context,
        template: str | None = None,
        energy_arc: str = "classic",
        track_count: int | None = None,
        min_transition_score: float = 0.0,
        optimizer: str = "ga",
        exclude_track_ids: list[int] | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        gen_svc: SetGenerationService = Depends(get_set_generation_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> SetBuildResult:
        """Build a DJ set from a playlist using template + genetic algorithm.

        If template is provided, GA selects and orders tracks to fit
        template slots (mood, energy, BPM). Without template, GA picks
        track_count tracks (default 20) optimizing transitions.

        When min_transition_score > 0, auto-rebuilds up to 3 times by
        excluding the worst-transition track until all scores meet the
        threshold or max iterations reached.

        Args:
            playlist_ref: Source playlist ref (int, "42", or "local:42").
            set_name: Name for the new DJ set.
            template: Template name (classic_60, peak_hour_60, etc.) or None.
            energy_arc: Energy arc shape — classic, progressive,
                        roller, or wave.
            track_count: Number of tracks to select. Defaults to 20 without
                         template. With template, uses template slot count.
            min_transition_score: Minimum acceptable transition score (0.0-1.0).
                When > 0, auto-excludes weak-bridge tracks and re-runs GA
                (max 3 iterations).
            optimizer: Algorithm to use — "ga" (genetic, default) or "greedy"
                (O(n*k), much faster for large pools).
            exclude_track_ids: Track IDs to exclude from selection.
        """
        max_auto_rebuild = 3

        playlist_id = resolve_local_id(playlist_ref, "playlist")
        # 1. Create DJ set
        await ctx.report_progress(progress=0, total=100)
        dj_set = await set_svc.create(
            DjSetCreate(name=set_name),
        )

        await ctx.report_progress(progress=10, total=100)

        # ── Greedy optimizer path ──────────────────────────────
        if optimizer == "greedy":
            await ctx.info(
                f"Created set '{set_name}' (id={dj_set.set_id}), "
                f"running greedy chain with energy_arc={energy_arc}..."
            )
            greedy_result = await _run_greedy_build(
                playlist_id=playlist_id,
                set_id=dj_set.set_id,
                energy_arc=energy_arc,
                track_count=track_count or 20,
                exclude_track_ids=exclude_track_ids,
                set_svc=set_svc,
                features_svc=features_svc,
                playlist_svc=playlist_svc,
                ctx=ctx,
            )
            await ctx.report_progress(progress=100, total=100)

            await save_build_result(
                ctx,
                set_id=dj_set.set_id,
                version_id=greedy_result.version_id,
                quality=greedy_result.avg_transition_score,
            )
            return greedy_result

        # ── GA optimizer path ──────────────────────────────────
        tmpl_info = f", template={template}" if template else ""
        await ctx.info(
            f"Created set '{set_name}' (id={dj_set.set_id}), "
            f"running GA with energy_arc={energy_arc}{tmpl_info}..."
        )

        # 2. Generate optimal ordering via GA (with auto-rebuild loop)
        excluded = list(exclude_track_ids or [])
        gen_result = None
        auto_iterations = 0

        for attempt in range(max_auto_rebuild + 1):
            request = SetGenerationRequest(
                energy_arc_type=energy_arc,
                playlist_id=playlist_id,
                template_name=template,
                track_count=track_count,
                exclude_track_ids=excluded or None,
            )
            gen_result = await gen_svc.generate(dj_set.set_id, request)

            if min_transition_score <= 0 or not gen_result.transition_scores:
                break

            # Check for weak transitions
            min_score = min(gen_result.transition_scores)
            if min_score >= min_transition_score:
                break

            if attempt >= max_auto_rebuild:
                await ctx.info(
                    f"Auto-rebuild: max iterations ({max_auto_rebuild}) reached, "
                    f"min score={min_score:.3f}"
                )
                break

            # Find worst transition and exclude the non-pinned track
            worst_idx = gen_result.transition_scores.index(min_score)
            # Exclude the "to" track of worst transition (track after the gap)
            weak_track_id = gen_result.track_ids[worst_idx + 1]
            excluded.append(weak_track_id)
            auto_iterations += 1

            await ctx.info(
                f"Auto-rebuild {auto_iterations}/{max_auto_rebuild}: "
                f"excluding track {weak_track_id} (score={min_score:.3f}), re-running GA..."
            )

        assert gen_result is not None

        await ctx.report_progress(progress=80, total=100)

        avg_score = 0.0
        if gen_result.transition_scores:
            avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

        await ctx.report_progress(progress=100, total=100)

        # Save to session state for workflow continuity
        await save_build_result(
            ctx, set_id=dj_set.set_id, version_id=gen_result.set_version_id, quality=avg_score
        )

        return SetBuildResult(
            set_id=dj_set.set_id,
            version_id=gen_result.set_version_id,
            track_count=len(gen_result.track_ids),
            total_score=gen_result.score,
            avg_transition_score=avg_score,
            energy_curve=[],
            auto_rebuild_iterations=auto_iterations,
        )

    @mcp.tool(tags={"setbuilder"}, timeout=600)
    async def rebuild_set(
        set_ref: str | int,
        ctx: Context,
        pinned_track_ids: list[int] | None = None,
        exclude_track_ids: list[int] | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        gen_svc: SetGenerationService = Depends(get_set_generation_service),
    ) -> SetBuildResult:
        """Rebuild a set respecting pinned tracks and excluding rejected ones.

        Reads pinned flags from the latest version's items unless pinned_track_ids
        is provided explicitly. Creates a new version with re-optimized track
        ordering via GA. When exclude_track_ids are provided the pool expands to
        the full library so GA can pick replacements for excluded tracks.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            pinned_track_ids: Track IDs that MUST appear in the new version.
                Overrides pinned flags stored in the latest version.
            exclude_track_ids: Track IDs to ban from the new version.
                GA will pick replacements from the full library.
        """
        set_id = resolve_local_id(set_ref, "set")
        dj_set = await set_svc.get(set_id)

        # Get latest version
        versions = await set_svc.list_versions(set_id)
        if not versions.items:
            raise NotFoundError("DjSetVersion", set_id=set_id)
        latest = max(versions.items, key=lambda v: v.set_version_id)

        items_list = await set_svc.list_items(latest.set_version_id, offset=0, limit=500)
        items = items_list.items

        # Use explicit pinned_track_ids if provided, otherwise read from version
        if pinned_track_ids is not None:
            pinned_ids = pinned_track_ids
        else:
            pinned_ids = [item.track_id for item in items if item.pinned]
        excluded_set = set(exclude_track_ids or [])

        await ctx.info(
            f"Rebuilding set {set_id} with {len(pinned_ids)} pinned tracks"
            + (f", {len(excluded_set)} excluded" if excluded_set else "")
            + "..."
        )

        # When tracks are excluded we open the pool to the full library so GA
        # can find replacements; otherwise keep source_playlist_id as filter.
        playlist_id = None if excluded_set else dj_set.source_playlist_id
        # Keep the same total track count
        target_count = len(items)

        # Re-run GA with constraints
        request = SetGenerationRequest(
            playlist_id=playlist_id,
            template_name=dj_set.template_name,
            pinned_track_ids=pinned_ids if pinned_ids else None,
            exclude_track_ids=list(excluded_set) if excluded_set else None,
            track_count=target_count,
        )
        gen_result = await gen_svc.generate(set_id, request)

        avg_score = 0.0
        if gen_result.transition_scores:
            avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

        # Save to session state for workflow continuity
        await save_build_result(
            ctx, set_id=set_id, version_id=gen_result.set_version_id, quality=avg_score
        )

        return SetBuildResult(
            set_id=set_id,
            version_id=gen_result.set_version_id,
            track_count=len(gen_result.track_ids),
            total_score=gen_result.score,
            avg_transition_score=avg_score,
            energy_curve=[],
        )

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"setbuilder"},
        timeout=120,
    )
    async def score_transitions(
        set_ref: str | int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        unified_svc: UnifiedTransitionScoringService = Depends(get_unified_scoring),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        track_svc: TrackService = Depends(get_track_service),
    ) -> list[TransitionScoreResult]:
        """Score every adjacent transition in a set version.

        Returns a list of TransitionScoreResult for each pair of
        consecutive tracks in the set.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            version_id: Set version whose items to score.
        """
        set_id = resolve_local_id(set_ref, "set")
        # Validate set exists
        try:
            await set_svc.get(set_id)
        except NotFoundError:
            return []

        # Get ordered items
        items_list = await set_svc.list_items(
            version_id,
            offset=0,
            limit=500,
        )
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        results = await score_consecutive_transitions(items, unified_svc, track_svc, features_svc)

        await ctx.report_progress(progress=len(items) - 1, total=max(len(items) - 1, 1))
        return results

    @mcp.tool(tags={"setbuilder"}, annotations={"readOnlyHint": True})
    async def score_track_pairs(
        track_ids: list[int],
        ctx: Context,
        unified_svc: UnifiedTransitionScoringService = Depends(get_unified_scoring),
        track_svc: TrackService = Depends(get_track_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> list[TransitionScoreResult]:
        """Score transitions between consecutive track pairs.

        Does NOT require a set — works on any ordered list of track IDs.
        Useful for pre-analysis before build_set.

        Args:
            track_ids: Ordered list of track IDs to score consecutively.
        """
        items = [types.SimpleNamespace(track_id=tid) for tid in track_ids]
        return await score_consecutive_transitions(items, unified_svc, track_svc, features_svc)
