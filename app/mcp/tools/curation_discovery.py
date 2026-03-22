"""Curation discovery tools — find and filter techno candidates from YM."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music import YandexMusicClient
from app.mcp.dependencies import get_session, get_ym_client
from app.models.dj import DjPlaylistItem
from app.models.ingestion import ProviderTrackId

logger = logging.getLogger(__name__)

# Metadata pre-filter constants
_BAD_VERSION_WORDS = frozenset(
    {
        "radio",
        "edit",
        "short",
        "remix",
        "live",
        "acoustic",
        "instrumental",
    }
)
_MIN_DURATION_MS = 255_000  # 4:15


def _is_techno(track_data: dict[str, Any]) -> bool:
    """Check if track has techno-related genre in any album."""
    for album in track_data.get("albums", []):
        genre = (album.get("genre") or "").lower()
        if "techno" in genre or "electronic" in genre:
            return True
    return False


def _has_bad_version(title: str) -> bool:
    """Check if title contains remix/edit/live markers."""
    words = set(title.lower().split())
    paren = re.findall(r"\(([^)]+)\)", title.lower())
    for p in paren:
        words.update(p.split())
    return bool(words & _BAD_VERSION_WORDS)


def register_curation_discovery_tools(mcp: FastMCP) -> None:
    """Register curation discovery tools on the MCP server."""

    @mcp.tool(tags={"curation", "yandex"}, timeout=120)
    async def discover_candidates(
        seed_track_id: int,
        ctx: Context,
        batch_size: int = 20,
        exclude_track_ids: list[int] | None = None,
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Discover similar techno tracks from YM for playlist expansion.

        Uses YM's similar tracks API, then filters by:
        - Genre contains "techno" or "electronic"
        - Duration >= 4:15
        - No remixes/edits/live versions
        - Not in exclude list

        Args:
            seed_track_id: YM track ID to find similar tracks for.
            batch_size: Max candidates to return (default 20).
            exclude_track_ids: YM track IDs to skip (already processed).
        """
        await ctx.info(f"Fetching similar tracks for seed {seed_track_id}...")

        try:
            similar = await ym_client.get_similar_tracks(str(seed_track_id))
        except Exception:
            logger.exception("Failed to get similar tracks for %s", seed_track_id)
            return {
                "candidates": [],
                "total_fetched": 0,
                "passed_filter": 0,
            }

        await ctx.info(f"Got {len(similar)} similar tracks, filtering...")

        excluded = set(exclude_track_ids or [])
        candidates: list[dict[str, object]] = []

        for track_data in similar:
            ym_id = str(track_data.get("id", ""))
            if not ym_id:
                continue
            try:
                ym_id_int = int(ym_id)
            except (ValueError, TypeError):
                continue
            if ym_id_int in excluded:
                continue

            title = track_data.get("title", "")
            duration = track_data.get("durationMs", 0) or 0

            # Metadata filters
            if duration < _MIN_DURATION_MS:
                continue
            if not _is_techno(track_data):
                continue
            if _has_bad_version(title):
                continue

            artists = ", ".join(a.get("name", "") for a in track_data.get("artists", []))
            albums: list[dict[str, Any]] = track_data.get("albums", [])
            album_id = str(albums[0]["id"]) if albums else ""

            candidates.append(
                {
                    "ym_track_id": ym_id,
                    "album_id": album_id,
                    "title": title,
                    "artists": artists,
                    "duration_ms": duration,
                    "genre": albums[0].get("genre", "") if albums else "",
                }
            )

            if len(candidates) >= batch_size:
                break

        await ctx.report_progress(progress=1, total=1)

        return {
            "candidates": candidates,
            "total_fetched": len(similar),
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

        Picks the best seed tracks from the playlist, finds similar
        tracks via YM API, auto-excludes tracks already in the DB.
        No ad-hoc code needed — one call does everything.

        Args:
            playlist_id: Local playlist to expand.
            seed_count: How many seed tracks to use (default 3).
            batch_size: Max candidates per seed (default 20).
        """
        # 1. Get all existing YM IDs to auto-exclude
        stmt = select(ProviderTrackId.provider_track_id).where(
            ProviderTrackId.provider_id == 4,
        )
        rows = await session.execute(stmt)
        existing_ym = {int(r[0]) for r in rows}
        await ctx.info(f"Auto-excluding {len(existing_ym)} existing tracks")

        # 2. Pick seed tracks from playlist
        seed_stmt = (
            select(ProviderTrackId.provider_track_id)
            .join(
                DjPlaylistItem,
                ProviderTrackId.track_id == DjPlaylistItem.track_id,
            )
            .where(
                DjPlaylistItem.playlist_id == playlist_id,
                ProviderTrackId.provider_id == 4,
            )
        )
        seed_rows = (await session.execute(seed_stmt)).fetchall()

        if not seed_rows:
            return {
                "seeds_used": 0,
                "total_candidates": 0,
                "candidates": [],
            }

        # Pick random seeds from playlist
        import random

        all_seeds = [int(r[0]) for r in seed_rows]
        seeds = random.sample(all_seeds, min(seed_count, len(all_seeds)))

        # 3. Discover from each seed
        all_candidates: list[dict[str, object]] = []
        seen_ids: set[int] = set(existing_ym)

        for i, seed_id in enumerate(seeds):
            await ctx.report_progress(progress=i, total=seed_count)
            await ctx.info(f"Seed {i + 1}/{seed_count}: {seed_id}")

            try:
                similar = await ym_client.get_similar_tracks(str(seed_id))
            except Exception:
                logger.exception("Seed %s failed", seed_id)
                continue

            for track_data in similar:
                ym_id = str(track_data.get("id", ""))
                if not ym_id:
                    continue
                try:
                    ym_id_int = int(ym_id)
                except (ValueError, TypeError):
                    continue
                if ym_id_int in seen_ids:
                    continue

                title = track_data.get("title", "")
                duration = track_data.get("durationMs", 0) or 0

                if duration < _MIN_DURATION_MS:
                    continue
                if not _is_techno(track_data):
                    continue
                if _has_bad_version(title):
                    continue

                artists = ", ".join(a.get("name", "") for a in track_data.get("artists", []))
                albums: list[dict[str, Any]] = track_data.get("albums", [])
                album_id = str(albums[0]["id"]) if albums else ""

                all_candidates.append(
                    {
                        "ym_track_id": ym_id,
                        "album_id": album_id,
                        "title": title,
                        "artists": artists,
                        "duration_ms": duration,
                    }
                )
                seen_ids.add(ym_id_int)

                if len(all_candidates) >= batch_size * seed_count:
                    break

        await ctx.report_progress(progress=seed_count, total=seed_count)

        return {
            "seeds_used": len(seeds),
            "total_candidates": len(all_candidates),
            "candidates": all_candidates,
        }
