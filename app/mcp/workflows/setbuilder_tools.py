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
)
from app.mcp.resolve import resolve_local_id
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

    @mcp.tool(tags={"setbuilder"})
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
        return SetBuildResult(
            set_id=dj_set.set_id,
            version_id=gen_result.set_version_id,
            track_count=len(gen_result.track_ids),
            total_score=gen_result.score,
            avg_transition_score=avg_score,
            energy_curve=[],
        )

    @mcp.tool(tags={"setbuilder"})
    async def rebuild_set(
        set_ref: str | int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        gen_svc: SetGenerationService = Depends(get_set_generation_service),
    ) -> SetBuildResult:
        """Rebuild a set respecting pinned tracks and excluding rejected ones.

        Reads pinned flags from the latest version's items. Creates a new
        version with re-optimized track ordering via GA.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
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

        pinned_ids = [item.track_id for item in items if item.pinned]

        await ctx.info(f"Rebuilding set {set_id} with {len(pinned_ids)} pinned tracks...")

        # Re-run GA with constraints
        request = SetGenerationRequest(
            playlist_id=dj_set.source_playlist_id,
            template_name=dj_set.template_name,
            pinned_track_ids=pinned_ids if pinned_ids else None,
        )
        gen_result = await gen_svc.generate(set_id, request)

        avg_score = 0.0
        if gen_result.transition_scores:
            avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

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
    )
    async def score_transitions(
        set_ref: str | int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
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

        if len(items) < 2:
            return []

        # Build track title lookup
        title_map: dict[int, str] = {}
        for item in items:
            try:
                track = await track_svc.get(item.track_id)
                title_map[item.track_id] = track.title
            except NotFoundError:
                title_map[item.track_id] = f"Track {item.track_id}"

        # Use unified scoring service (same path as GA and API)
        unified_svc = UnifiedTransitionScoringService(
            features_svc.features_repo.session,
        )

        # Score consecutive pairs
        results: list[TransitionScoreResult] = []
        pairs_total = len(items) - 1
        for i in range(pairs_total):
            await ctx.report_progress(progress=i, total=pairs_total)
            from_item = items[i]
            to_item = items[i + 1]

            try:
                components = await unified_svc.score_components_by_ids(
                    from_item.track_id,
                    to_item.track_id,
                )
            except ValueError:
                results.append(
                    TransitionScoreResult(
                        from_track_id=from_item.track_id,
                        to_track_id=to_item.track_id,
                        from_title=title_map.get(
                            from_item.track_id, f"Track {from_item.track_id}"
                        ),
                        to_title=title_map.get(to_item.track_id, f"Track {to_item.track_id}"),
                        total=0.0,
                        bpm=0.0,
                        harmonic=0.0,
                        energy=0.0,
                        spectral=0.0,
                        groove=0.0,
                    )
                )
                continue

            # Try to get features for transition recommendation
            rec_type: str | None = None
            rec_confidence: float | None = None
            rec_reason: str | None = None
            rec_alt: str | None = None

            try:
                feat_a_raw = await features_svc.get_latest(from_item.track_id)
                feat_b_raw = await features_svc.get_latest(to_item.track_id)

                # Phase 3: Transition type recommendation
                from app.services.transition_type import recommend_transition
                from app.utils.audio.camelot import camelot_distance
                from app.utils.audio.feature_conversion import (
                    orm_features_to_track_features,
                )

                tf_a = orm_features_to_track_features(feat_a_raw)  # type: ignore[arg-type]
                tf_b = orm_features_to_track_features(feat_b_raw)  # type: ignore[arg-type]
                cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)

                rec = recommend_transition(tf_a, tf_b, camelot_compatible=cam_dist <= 1)
                rec_type = str(rec.transition_type)
                rec_confidence = rec.confidence
                rec_reason = rec.reason
                rec_alt = str(rec.alt_type) if rec.alt_type else None
            except (NotFoundError, ValueError):
                pass

            results.append(
                TransitionScoreResult(
                    from_track_id=from_item.track_id,
                    to_track_id=to_item.track_id,
                    from_title=title_map.get(from_item.track_id, f"Track {from_item.track_id}"),
                    to_title=title_map.get(to_item.track_id, f"Track {to_item.track_id}"),
                    total=components["total"],
                    bpm=components["bpm"],
                    harmonic=components["harmonic"],
                    energy=components["energy"],
                    spectral=components["spectral"],
                    groove=components["groove"],
                    structure=components.get("structure", 0.5),
                    recommended_type=rec_type,
                    type_confidence=rec_confidence,
                    reason=rec_reason,
                    alt_type=rec_alt,
                )
            )

        await ctx.report_progress(progress=pairs_total, total=pairs_total)
        return results
