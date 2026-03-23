"""Curation discovery tools — thin MCP adapters delegating to CandidateDiscoveryService."""

from __future__ import annotations

import random

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.dependencies import get_session, get_ym_client
from app.services.candidate_discovery import CandidateDiscoveryService
from app.services.yandex_music_client import YandexMusicClient


def register_curation_discovery_tools(mcp: FastMCP) -> None:
    """Register curation discovery tools on the MCP server."""

    @mcp.tool(tags={"curation", "yandex"}, timeout=120)
    async def discover_candidates(
        seed_track_id: int,
        ctx: Context,
        batch_size: int = 20,
        exclude_track_ids: list[int] | None = None,
        ym_client: YandexMusicClient = Depends(get_ym_client),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        """Discover similar techno tracks from YM for playlist expansion.

        Args:
            seed_track_id: YM track ID to find similar tracks for.
            batch_size: Max candidates to return (default 20).
            exclude_track_ids: YM track IDs to skip (already processed).
        """
        await ctx.info(f"Fetching similar tracks for seed {seed_track_id}...")
        svc = CandidateDiscoveryService(session, ym_client)

        excluded = set(exclude_track_ids or [])
        candidates = await svc.discover_from_seeds(
            [seed_track_id],
            excluded,
            batch_size=batch_size,
        )

        await ctx.report_progress(progress=1, total=1)
        return {
            "candidates": candidates,
            "total_fetched": len(candidates),
            "passed_filter": len(candidates),
        }

    @mcp.tool(tags={"curation", "yandex"}, timeout=300)
    async def expand_playlist_discover(
        playlist_id: int,
        ctx: Context,
        seed_count: int = 3,
        batch_size: int = 20,
        session: AsyncSession = Depends(get_session),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Auto-discover new techno tracks for a playlist.

        Args:
            playlist_id: Local playlist to expand.
            seed_count: How many seed tracks to use (default 3).
            batch_size: Max candidates per seed (default 20).
        """
        svc = CandidateDiscoveryService(session, ym_client)

        existing = await svc.get_existing_ym_ids()
        await ctx.info(f"Auto-excluding {len(existing)} existing tracks")

        all_seeds = await svc.get_playlist_seed_ids(playlist_id)
        if not all_seeds:
            return {"seeds_used": 0, "total_candidates": 0, "candidates": []}

        seeds = random.sample(all_seeds, min(seed_count, len(all_seeds)))
        for i, sid in enumerate(seeds):
            await ctx.report_progress(progress=i, total=seed_count)
            await ctx.info(f"Seed {i + 1}/{seed_count}: {sid}")

        candidates = await svc.discover_from_seeds(seeds, existing, batch_size=batch_size)
        await ctx.report_progress(progress=seed_count, total=seed_count)

        return {
            "seeds_used": len(seeds),
            "total_candidates": len(candidates),
            "candidates": candidates,
        }

    @mcp.tool(tags={"curation", "yandex"}, timeout=600)
    async def expand_playlist_full(
        playlist_id: int,
        ctx: Context,
        seed_count: int = 3,
        batch_size: int = 15,
        session: AsyncSession = Depends(get_session),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Discover, import, and add new techno tracks to a playlist.

        Full pipeline: discover → filter → import → add to playlist.

        Args:
            playlist_id: Local playlist to expand.
            seed_count: Number of seed tracks to use.
            batch_size: Max new tracks per seed.
        """
        svc = CandidateDiscoveryService(session, ym_client)

        # Stage 1: Discover
        await ctx.info("Stage 1/3 — discovering candidates...")
        await ctx.report_progress(progress=0, total=3)

        existing_ids = await svc.get_existing_ym_ids()
        existing_ym = await svc.get_ym_id_to_track_id()
        await ctx.info(f"Auto-excluding {len(existing_ids)} existing tracks")

        all_seeds = await svc.get_playlist_seed_ids(playlist_id)
        if not all_seeds:
            return {
                "discovered": 0,
                "imported": 0,
                "already_exists": 0,
                "added_to_playlist": 0,
                "errors": [],
            }

        seeds = random.sample(all_seeds, min(seed_count, len(all_seeds)))
        candidates = await svc.discover_from_seeds(seeds, existing_ids, batch_size=batch_size)
        discovered = len(candidates)
        await ctx.info(f"Discovered {discovered} candidates")

        if not candidates:
            return {
                "discovered": 0,
                "imported": 0,
                "already_exists": 0,
                "added_to_playlist": 0,
                "errors": [],
            }

        # Stage 2: Import
        await ctx.info("Stage 2/3 — importing tracks to DB...")
        await ctx.report_progress(progress=1, total=3)

        result = await svc.import_and_add_to_playlist(candidates, playlist_id, existing_ym)

        # Stage 3: Done
        await ctx.info("Stage 3/3 — committing...")
        await ctx.report_progress(progress=3, total=3)
        await ctx.info(
            f"Done: {result['imported']} imported, {result['already_exists']} existed, "
            f"{result['added_to_playlist']} added to playlist"
        )

        return {"discovered": discovered, **result}
