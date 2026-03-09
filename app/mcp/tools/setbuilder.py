"""Set builder tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import (
    get_features_service,
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
from app.schemas.sets import DjSetCreate
from app.services.features import AudioFeaturesService
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService


def register_setbuilder_tools(mcp: FastMCP) -> None:
    """Register set builder tools on the MCP server."""

    @mcp.tool(tags={"setbuilder"}, timeout=300)
    async def build_set(
        playlist_ref: str | int,
        set_name: str,
        ctx: Context,
        template: str | None = None,
        energy_arc: str = "classic",
        exclude_track_ids: list[int] | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        gen_svc: SetGenerationService = Depends(get_set_generation_service),
    ) -> SetBuildResult:
        """Build a DJ set from a playlist using template + genetic algorithm.

        If template is provided, GA selects and orders tracks to fit
        template slots (mood, energy, BPM). Without template, GA orders
        all playlist tracks optimizing transitions only.

        Args:
            playlist_ref: Source playlist ref (int, "42", or "local:42").
            set_name: Name for the new DJ set.
            template: Template name (classic_60, peak_hour_60, etc.) or None.
            energy_arc: Energy arc shape — classic, progressive,
                        roller, or wave.
            exclude_track_ids: Track IDs to exclude from selection.
        """
        playlist_id = resolve_local_id(playlist_ref, "playlist")
        # 1. Create DJ set
        await ctx.report_progress(progress=0, total=100)
        dj_set = await set_svc.create(
            DjSetCreate(name=set_name),
        )

        await ctx.report_progress(progress=10, total=100)
        tmpl_info = f", template={template}" if template else ""
        await ctx.info(
            f"Created set '{set_name}' (id={dj_set.set_id}), "
            f"running GA with energy_arc={energy_arc}{tmpl_info}..."
        )

        # 2. Generate optimal ordering via GA
        request = SetGenerationRequest(
            energy_arc_type=energy_arc,
            playlist_id=playlist_id,
            template_name=template,
            exclude_track_ids=exclude_track_ids,
        )
        gen_result = await gen_svc.generate(dj_set.set_id, request)
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
        )

    @mcp.tool(tags={"setbuilder"}, timeout=300)
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
        await set_svc.get(set_id)

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
