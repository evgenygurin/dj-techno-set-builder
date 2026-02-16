"""Set builder tools for DJ workflow MCP server."""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError
from app.mcp.dependencies import (
    get_features_service,
    get_set_generation_service,
    get_set_service,
)
from app.mcp.types import ExportResult, SetBuildResult, TransitionScoreResult
from app.schemas.set_generation import SetGenerationRequest
from app.schemas.sets import DjSetCreate, DjSetVersionCreate
from app.services.features import AudioFeaturesService
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.camelot import key_code_to_camelot


def register_setbuilder_tools(mcp: FastMCP) -> None:
    """Register set builder tools on the MCP server."""

    @mcp.tool(tags={"setbuilder"})
    async def build_set(
        playlist_id: int,
        set_name: str,
        ctx: Context,
        energy_arc: str = "classic",
        set_svc: DjSetService = Depends(get_set_service),
        gen_svc: SetGenerationService = Depends(get_set_generation_service),
    ) -> SetBuildResult:
        """Build a DJ set from a playlist using the genetic algorithm.

        Creates a new DjSet, then uses SetGenerationService to find the
        optimal track ordering via GA optimisation.

        Args:
            playlist_id: Source playlist containing candidate tracks.
            set_name: Name for the new DJ set.
            energy_arc: Energy arc shape — classic, progressive,
                        roller, or wave.
        """
        # 1. Create DJ set
        await ctx.report_progress(progress=0, total=100)
        dj_set = await set_svc.create(
            DjSetCreate(name=set_name),
        )

        await ctx.report_progress(progress=10, total=100)
        await ctx.info(
            f"Created set '{set_name}' (id={dj_set.set_id}), "
            f"running GA with energy_arc={energy_arc}..."
        )

        # 2. Generate optimal ordering via GA
        request = SetGenerationRequest(energy_arc_type=energy_arc)
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

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"setbuilder"},
    )
    async def score_transitions(
        set_id: int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> list[TransitionScoreResult]:
        """Score every adjacent transition in a set version.

        Returns a list of TransitionScoreResult for each pair of
        consecutive tracks in the set.

        Args:
            set_id: DJ set ID (used for validation).
            version_id: Set version whose items to score.
        """
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
                        from_title="",
                        to_title="",
                        total=0.0,
                        bpm=0.0,
                        harmonic=0.0,
                        energy=0.0,
                        spectral=0.0,
                        groove=0.0,
                    )
                )
                continue

            # Try to get features for Camelot key + transition recommendation
            from_key: str | None = None
            to_key: str | None = None
            rec_type: str | None = None
            rec_confidence: float | None = None
            rec_reason: str | None = None
            rec_alt: str | None = None

            try:
                feat_a_raw = await features_svc.get_latest(from_item.track_id)
                feat_b_raw = await features_svc.get_latest(to_item.track_id)

                with contextlib.suppress(ValueError):
                    from_key = key_code_to_camelot(feat_a_raw.key_code)
                with contextlib.suppress(ValueError):
                    to_key = key_code_to_camelot(feat_b_raw.key_code)

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
                    from_title=from_key or "",
                    to_title=to_key or "",
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

    @mcp.tool(tags={"setbuilder"})
    async def adjust_set(
        set_id: int,
        version_id: int,
        instructions: str,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> SetBuildResult:
        """Adjust a DJ set version based on natural language instructions.

        Uses ctx.sample_step() in an agentic loop so the LLM can call
        a score_pair tool to evaluate transitions before suggesting changes.
        Falls back gracefully when the MCP client does not support sampling.

        Creates a new version that copies the current track ordering and
        records the LLM suggestion in generator_run metadata.  The caller
        can then apply specific reorderings via the REST API.

        Args:
            set_id: DJ set to adjust.
            version_id: Version to base the adjustment on.
            instructions: Natural language instructions describing
                          what to change (e.g. "move the peak earlier",
                          "swap tracks 3 and 5").
        """
        # Validate set + version
        await set_svc.get(set_id)
        items_list = await set_svc.list_items(
            version_id,
            offset=0,
            limit=500,
        )
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        track_summary = ", ".join(f"#{i.sort_index}: track {i.track_id}" for i in items)

        # Define score_pair tool for LLM to evaluate transitions
        unified_svc = UnifiedTransitionScoringService(
            features_svc.features_repo.session,
        )

        async def _score_pair(
            track_a_id: int,
            track_b_id: int,
        ) -> dict[str, float]:
            """Score the transition quality between two tracks.

            Returns BPM, harmonic, energy, spectral, groove and total scores.
            """
            try:
                return await unified_svc.score_components_by_ids(
                    track_a_id,
                    track_b_id,
                )
            except (ValueError, NotFoundError):
                return {"error": 1.0, "total": 0.0}

        # Try LLM-assisted adjustment with agentic loop
        from app.mcp.types import AdjustmentPlan

        plan: AdjustmentPlan | None = None
        suggestion: str | None = None
        try:
            prompt = (
                f"Current set order: [{track_summary}]. "
                f"User instructions: {instructions}. "
                "Use the score_pair tool to evaluate transitions, "
                "then suggest improvements."
            )

            # Use sample_step for fine-grained control
            messages: str | list[str] = prompt
            max_steps = 10
            for step_num in range(max_steps):
                step = await ctx.sample_step(
                    messages=messages,
                    system_prompt=(
                        "You are a DJ assistant. Score transitions between "
                        "tracks and suggest reorderings to improve the set."
                    ),
                    tools=[_score_pair],
                    execute_tools=True,
                )

                if step.is_tool_use:
                    await ctx.report_progress(
                        progress=step_num + 1,
                        total=max_steps,
                    )
                    messages = step.history  # type: ignore[assignment]
                    continue

                # Final text response
                suggestion = step.text
                break

            # Try to parse as AdjustmentPlan
            if suggestion:
                try:
                    plan = AdjustmentPlan.model_validate_json(suggestion)
                except (ValueError, KeyError):
                    plan = None

        except (NotImplementedError, AttributeError, TypeError, ValueError):
            plan = None
            suggestion = None

        if plan:
            with contextlib.suppress(Exception):
                await ctx.info(
                    f"Adjustment plan: {plan.reasoning[:200]}\n"
                    f"Swaps: {len(plan.swap_suggestions)}, "
                    f"Reorders: {len(plan.reorder_suggestions)}"
                )
        elif suggestion:
            with contextlib.suppress(Exception):
                await ctx.info(f"Suggested changes:\n{suggestion[:500]}")

        # Create a new version with the instructions recorded
        new_version = await set_svc.create_version(
            set_id,
            DjSetVersionCreate(
                version_label=f"Adjusted: {instructions[:60]}",
                generator_run={
                    "algorithm": "manual_adjust",
                    "instructions": instructions,
                    "suggestion": suggestion,
                    "plan": plan.model_dump() if plan else None,
                },
            ),
        )

        # Copy items from original version to new version
        for item in items:
            from app.schemas.sets import DjSetItemCreate

            await set_svc.add_item(
                new_version.set_version_id,
                DjSetItemCreate(
                    track_id=item.track_id,
                    sort_index=item.sort_index,
                ),
            )

        return SetBuildResult(
            set_id=set_id,
            version_id=new_version.set_version_id,
            track_count=len(items),
            total_score=0.0,
            avg_transition_score=0.0,
            energy_curve=[],
        )

    @mcp.tool(tags={"setbuilder"})
    async def export_set_m3u(
        set_id: int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
    ) -> ExportResult:
        """Export a DJ set version as M3U8 playlist for djay Pro import.

        Generates an M3U8 file with track ordering matching the set version.

        Args:
            set_id: DJ set ID.
            version_id: Set version to export.
        """
        from app.services.set_export import export_m3u

        await set_svc.get(set_id)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        tracks = [
            {
                "title": f"Track {item.track_id}",
                "duration_s": 0,
                "path": f"track_{item.track_id}.mp3",
            }
            for item in items
        ]

        content = export_m3u(tracks)

        return ExportResult(
            set_id=set_id,
            format="m3u8",
            track_count=len(items),
            content=content,
        )

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"setbuilder"},
    )
    async def export_set_json(
        set_id: int,
        version_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        features_svc: AudioFeaturesService = Depends(get_features_service),
    ) -> ExportResult:
        """Export a DJ set version as JSON transition guide.

        Includes track order, per-transition scores, recommended transition
        types, and set quality metrics. A DJ cheat sheet.

        Args:
            set_id: DJ set ID.
            version_id: Set version to export.
        """
        from typing import Any

        from app.services.set_export import export_json_guide
        from app.services.transition_type import recommend_transition
        from app.utils.audio.camelot import camelot_distance
        from app.utils.audio.feature_conversion import orm_features_to_track_features

        await set_svc.get(set_id)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        unified_svc = UnifiedTransitionScoringService(
            features_svc.features_repo.session,
        )

        tracks_data: list[dict[str, Any]] = []
        for item in items:
            tracks_data.append(
                {
                    "title": f"Track {item.track_id}",
                    "path": f"track_{item.track_id}.mp3",
                }
            )

        transitions_data: list[dict[str, Any]] = []
        for i in range(len(items) - 1):
            from_item = items[i]
            to_item = items[i + 1]

            trans: dict[str, Any] = {
                "score": 0.0,
                "bpm_delta": 0.0,
                "energy_delta": 0.0,
                "camelot": "",
                "recommendation": None,
            }

            try:
                components = await unified_svc.score_components_by_ids(
                    from_item.track_id,
                    to_item.track_id,
                )
                trans["score"] = components["total"]
            except ValueError:
                pass

            try:
                feat_a_obj = await features_svc.get_latest(from_item.track_id)
                feat_b_obj = await features_svc.get_latest(to_item.track_id)
                tf_a = orm_features_to_track_features(feat_a_obj)  # type: ignore[arg-type]
                tf_b = orm_features_to_track_features(feat_b_obj)  # type: ignore[arg-type]

                trans["bpm_delta"] = round(abs(tf_a.bpm - tf_b.bpm), 1)
                trans["energy_delta"] = round(abs(tf_a.energy_lufs - tf_b.energy_lufs), 1)

                cam_dist = camelot_distance(tf_a.key_code, tf_b.key_code)
                cam_a = key_code_to_camelot(tf_a.key_code)
                cam_b = key_code_to_camelot(tf_b.key_code)
                trans["camelot"] = f"{cam_a} -> {cam_b}"

                rec = recommend_transition(tf_a, tf_b, camelot_compatible=cam_dist <= 1)
                trans["recommendation"] = rec
            except (NotFoundError, ValueError):
                pass

            transitions_data.append(trans)

        quality = 0.0
        if transitions_data:
            quality = sum(t["score"] for t in transitions_data) / len(transitions_data)

        content = export_json_guide(
            set_name=f"Set {set_id}",
            energy_arc="classic",
            quality_score=round(quality, 3),
            tracks=tracks_data,
            transitions=transitions_data,
        )

        return ExportResult(
            set_id=set_id,
            format="json",
            track_count=len(items),
            content=content,
        )
