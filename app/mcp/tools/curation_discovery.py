"""Curation discovery tools — find and filter techno candidates from YM."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music import YandexMusicClient
from app.mcp.dependencies import get_session, get_ym_client
from app.models.catalog import Track
from app.models.dj import DjPlaylistItem
from app.models.ingestion import ProviderTrackId
from app.models.metadata_yandex import YandexMetadata
from app.clients.yandex_music import parse_ym_track

logger = logging.getLogger(__name__)

_YM_PROVIDER_ID = 4  # providers.provider_id for Yandex Music

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
        except (httpx.HTTPError, TimeoutError, ValueError):
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
            ProviderTrackId.provider_id == _YM_PROVIDER_ID,
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
                ProviderTrackId.provider_id == _YM_PROVIDER_ID,
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
            except (httpx.HTTPError, TimeoutError, ValueError):
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

        Full pipeline in one call:
        1. Pick random seeds from playlist
        2. Discover similar tracks via YM API
        3. Filter by techno criteria (genre, duration, no remixes)
        4. Import new tracks to local DB (Track + provider mapping + YM metadata)
        5. Add imported tracks to the playlist

        Args:
            playlist_id: Local playlist to expand.
            seed_count: Number of seed tracks to use.
            batch_size: Max new tracks per seed.
        """
        # --- Stage 1: Discover candidates ---
        await ctx.info("Stage 1/3 — discovering candidates...")
        await ctx.report_progress(progress=0, total=3)

        # Get all existing YM IDs to auto-exclude
        stmt = select(ProviderTrackId.provider_track_id).where(
            ProviderTrackId.provider_id == _YM_PROVIDER_ID,
        )
        rows = await session.execute(stmt)
        existing_ym: dict[int, int] = {}  # ym_id -> track_id (filled later)
        existing_ym_ids: set[int] = set()
        for r in rows:
            existing_ym_ids.add(int(r[0]))

        # Build lookup: ym_id -> track_id for existing tracks
        if existing_ym_ids:
            lookup_stmt = select(
                ProviderTrackId.provider_track_id,
                ProviderTrackId.track_id,
            ).where(ProviderTrackId.provider_id == _YM_PROVIDER_ID)
            lookup_rows = await session.execute(lookup_stmt)
            existing_ym = {int(r[0]): r[1] for r in lookup_rows}

        await ctx.info(f"Auto-excluding {len(existing_ym_ids)} existing tracks")

        # Pick seed tracks from playlist
        seed_stmt = (
            select(ProviderTrackId.provider_track_id)
            .join(
                DjPlaylistItem,
                ProviderTrackId.track_id == DjPlaylistItem.track_id,
            )
            .where(
                DjPlaylistItem.playlist_id == playlist_id,
                ProviderTrackId.provider_id == _YM_PROVIDER_ID,
            )
        )
        seed_rows = (await session.execute(seed_stmt)).fetchall()

        if not seed_rows:
            return {
                "discovered": 0,
                "imported": 0,
                "already_exists": 0,
                "added_to_playlist": 0,
                "errors": [],
            }

        all_seeds = [int(r[0]) for r in seed_rows]
        seeds = random.sample(all_seeds, min(seed_count, len(all_seeds)))

        # Discover from each seed
        candidates: list[dict[str, Any]] = []
        seen_ids: set[int] = set(existing_ym_ids)

        for i, seed_id in enumerate(seeds):
            await ctx.info(f"Seed {i + 1}/{seed_count}: {seed_id}")

            try:
                similar = await ym_client.get_similar_tracks(str(seed_id))
            except (httpx.HTTPError, TimeoutError, ValueError):
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

                albums: list[dict[str, Any]] = track_data.get("albums", [])
                album_id = str(albums[0]["id"]) if albums else ""

                candidates.append(
                    {
                        "ym_track_id": ym_id,
                        "ym_id_int": ym_id_int,
                        "album_id": album_id,
                        "title": title,
                        "duration_ms": duration,
                    }
                )
                seen_ids.add(ym_id_int)

                if len(candidates) >= batch_size * seed_count:
                    break

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

        # --- Stage 2: Import to DB ---
        await ctx.info("Stage 2/3 — importing tracks to DB...")
        await ctx.report_progress(progress=1, total=3)

        # Get current max sort_index for playlist
        max_idx_stmt = select(func.max(DjPlaylistItem.sort_index)).where(
            DjPlaylistItem.playlist_id == playlist_id,
        )
        max_idx_row = await session.execute(max_idx_stmt)
        next_idx = (max_idx_row.scalar() or 0) + 1

        # Get track_ids already in this playlist
        pl_stmt = select(DjPlaylistItem.track_id).where(
            DjPlaylistItem.playlist_id == playlist_id,
        )
        pl_rows = await session.execute(pl_stmt)
        playlist_track_ids: set[int] = {r[0] for r in pl_rows}

        imported = 0
        already_exists = 0
        added_to_playlist = 0
        errors: list[str] = []

        # Batch fetch full metadata from YM
        ym_ids_to_fetch = [c["ym_track_id"] for c in candidates]
        full_metadata: dict[str, dict[str, Any]] = {}

        for batch_start in range(0, len(ym_ids_to_fetch), 50):
            batch = ym_ids_to_fetch[batch_start : batch_start + 50]
            try:
                result = await ym_client.fetch_tracks(batch)
                full_metadata.update(result)
            except (httpx.HTTPError, TimeoutError, ValueError):
                logger.exception(
                    "Failed to fetch metadata batch %d-%d",
                    batch_start,
                    batch_start + len(batch),
                )
                errors.append(
                    f"Metadata fetch failed for batch {batch_start}-{batch_start + len(batch)}"
                )
            await asyncio.sleep(1.5)

        for candidate in candidates:
            ym_id = candidate["ym_track_id"]
            ym_id_int = candidate["ym_id_int"]

            try:
                if ym_id_int in existing_ym_ids:
                    # Track exists in DB — just add to playlist if needed
                    already_exists += 1
                    track_id = existing_ym.get(ym_id_int)
                    if track_id and track_id not in playlist_track_ids:
                        session.add(
                            DjPlaylistItem(
                                playlist_id=playlist_id,
                                track_id=track_id,
                                sort_index=next_idx,
                            )
                        )
                        next_idx += 1
                        added_to_playlist += 1
                        playlist_track_ids.add(track_id)
                    continue

                # Parse full metadata if available, fall back to candidate
                raw_track = full_metadata.get(ym_id)
                parsed = parse_ym_track(raw_track) if raw_track else None

                # Create Track
                title = parsed.title if parsed else candidate["title"]
                duration_ms = (
                    parsed.duration_ms
                    if parsed and parsed.duration_ms
                    else candidate["duration_ms"]
                )
                track = Track(
                    title=title,
                    duration_ms=duration_ms or 0,
                    status=0,
                )
                session.add(track)
                await session.flush()

                # Create ProviderTrackId
                session.add(
                    ProviderTrackId(
                        track_id=track.track_id,
                        provider_id=_YM_PROVIDER_ID,
                        provider_track_id=ym_id,
                    )
                )

                # Create YandexMetadata
                if parsed:
                    session.add(
                        YandexMetadata(
                            track_id=track.track_id,
                            yandex_track_id=parsed.yandex_track_id,
                            yandex_album_id=parsed.yandex_album_id,
                            album_title=parsed.album_title,
                            album_type=parsed.album_type,
                            album_genre=parsed.album_genre,
                            album_year=parsed.album_year,
                            label_name=parsed.label_name,
                            release_date=parsed.release_date,
                            duration_ms=parsed.duration_ms,
                            cover_uri=parsed.cover_uri,
                            explicit=parsed.explicit,
                        )
                    )
                else:
                    session.add(
                        YandexMetadata(
                            track_id=track.track_id,
                            yandex_track_id=ym_id,
                            yandex_album_id=candidate.get("album_id"),
                            duration_ms=candidate["duration_ms"],
                        )
                    )

                await session.flush()
                imported += 1

                # Add to playlist
                if track.track_id not in playlist_track_ids:
                    session.add(
                        DjPlaylistItem(
                            playlist_id=playlist_id,
                            track_id=track.track_id,
                            sort_index=next_idx,
                        )
                    )
                    next_idx += 1
                    added_to_playlist += 1
                    playlist_track_ids.add(track.track_id)

            except Exception as exc:  # broad: skip failed track, process rest
                logger.exception("Failed to import track %s", ym_id)
                errors.append(f"Track {ym_id}: {exc}")

        # --- Stage 3: Commit ---
        await ctx.info("Stage 3/3 — committing...")
        await ctx.report_progress(progress=2, total=3)

        # Session commit handled by get_session context manager
        await session.flush()

        await ctx.report_progress(progress=3, total=3)
        await ctx.info(
            f"Done: {imported} imported, {already_exists} existed, "
            f"{added_to_playlist} added to playlist"
        )

        return {
            "discovered": discovered,
            "imported": imported,
            "already_exists": already_exists,
            "added_to_playlist": added_to_playlist,
            "errors": errors,
        }
