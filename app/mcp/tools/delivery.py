"""DJ set delivery tool — thin MCP adapter delegating to DeliveryService."""

from __future__ import annotations

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.dependencies import (
    get_features_service,
    get_session,
    get_set_service,
    get_track_service,
    get_unified_scoring,
    get_ym_client,
)
from app.mcp.elicitation import resolve_conflict
from app.mcp.resolve import resolve_local_id
from app.mcp.types.workflows import DeliveryResult
from app.services.delivery import DeliveryService
from app.services.features import AudioFeaturesService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.services.yandex_music_client import YandexMusicClient

_WEAK_THRESHOLD = 0.85


def register_delivery_tools(mcp: FastMCP) -> None:
    """Register deliver_set tool on the MCP server."""

    @mcp.tool(tags={"setbuilder"}, timeout=300, annotations={"idempotentHint": True})
    async def deliver_set(
        set_ref: str | int,
        version_id: int,
        ctx: Context,
        skip_conflicts: bool = False,
        sync_to_ym: bool = False,
        ym_user_id: int | None = None,
        ym_playlist_title: str | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        unified_svc: UnifiedTransitionScoringService = Depends(get_unified_scoring),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        track_svc: TrackService = Depends(get_track_service),
        ym_client: YandexMusicClient = Depends(get_ym_client),
        session: AsyncSession = Depends(get_session),
    ) -> DeliveryResult:
        """Deliver a DJ set: score transitions, write files, optionally sync to YM.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            version_id: Set version to deliver.
            skip_conflicts: Skip hard-conflict checkpoint.
            sync_to_ym: Push set to Yandex Music as a playlist.
            ym_user_id: YM user ID (required when sync_to_ym=True).
            ym_playlist_title: YM playlist title (default: "{set_name} [set]").
        """
        set_id = resolve_local_id(set_ref, "set")
        dj_set = await set_svc.get(set_id)
        set_name = dj_set.name

        svc = DeliveryService(set_svc, unified_svc, features_svc, track_svc, session, ym_client)

        # Stage 1: Score
        await ctx.info(f"Stage 1/3 — Scoring transitions for '{set_name}'...")
        await ctx.report_progress(progress=0, total=3)

        scores = await svc.score_version(version_id)
        summary = svc.build_transition_summary(scores)

        conflicts = [s for s in scores if s.total == 0.0]
        weak = [s for s in scores if 0.0 < s.total < _WEAK_THRESHOLD]

        await ctx.info(
            f"Scored {summary.total} transitions: "
            f"{summary.hard_conflicts} hard conflicts, "
            f"{summary.weak} weak (< {_WEAK_THRESHOLD}), "
            f"avg={summary.avg_score:.3f}"
        )

        if conflicts and not skip_conflicts:
            conflict_lines = "\n".join(
                f"  • {c.from_title} → {c.to_title} (score=0.0)" for c in conflicts[:10]
            )
            decision = await resolve_conflict(
                ctx,
                f"Found {len(conflicts)} hard conflict(s):\n{conflict_lines}\n\n"
                f"Continue delivery anyway?",
                options=["continue", "abort"],
            )
            if decision == "abort" or decision is None:
                return DeliveryResult(
                    set_id=set_id,
                    version_id=version_id,
                    set_name=set_name,
                    output_dir="",
                    files_written=[],
                    transitions=summary,
                    status="aborted",
                )

        # Stage 2: Write files
        await ctx.report_progress(progress=1, total=3)
        await ctx.info("Stage 2/3 — Writing files...")

        result = await svc.write_files(set_name, version_id, scores)

        await ctx.info(
            f"Written: {', '.join(result['files_written'])} + "
            f"{result['mp3_copied']} MP3 ({result['mp3_skipped']} skipped)"
        )
        if weak:
            await ctx.info(f"Note: {len(weak)} weak transitions in cheat_sheet.txt")

        # Stage 3: YM sync
        ym_kind: int | None = None
        if sync_to_ym and ym_user_id is not None:
            await ctx.report_progress(progress=2, total=3)
            title = ym_playlist_title or f"{set_name} [set]"
            await ctx.info(f"Stage 3/3 — Creating YM playlist '{title}'...")
            try:
                ym_kind = await svc.sync_to_ym(result["tracks"], ym_user_id, title)
                await ctx.info(f"YM playlist created: kind={ym_kind}")
            except (httpx.HTTPStatusError, httpx.ConnectError, ValueError) as exc:
                await ctx.info(f"YM sync failed: {exc}. Files already written.")
        elif sync_to_ym:
            await ctx.info("Stage 3/3 — Skipped: ym_user_id not provided.")

        await ctx.report_progress(progress=3, total=3)

        return DeliveryResult(
            set_id=set_id,
            version_id=version_id,
            set_name=set_name,
            output_dir=result["output_dir"],
            files_written=result["files_written"],
            transitions=summary,
            mp3_copied=result["mp3_copied"],
            mp3_skipped=result["mp3_skipped"],
            ym_playlist_kind=ym_kind,
            status="ok",
        )
