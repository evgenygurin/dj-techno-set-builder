"""Service for discovering and importing techno track candidates from Yandex Music.

Extracted from app/mcp/tools/curation_discovery.py to separate business logic
from MCP adapter concerns. Eliminates direct ORM usage in the adapter layer.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.dj import DjPlaylistItem
from app.models.ingestion import ProviderTrackId
from app.models.metadata_yandex import YandexMetadata
from app.services.base import BaseService
from app.services.yandex_music_client import YandexMusicClient, parse_ym_track

logger = logging.getLogger(__name__)

_YM_PROVIDER_ID = 4

# Metadata pre-filter constants
_BAD_VERSION_WORDS = frozenset(
    {"radio", "edit", "short", "remix", "live", "acoustic", "instrumental"}
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


def filter_candidate(track_data: dict[str, Any], excluded: set[int]) -> dict[str, object] | None:
    """Apply techno criteria to a single YM track. Returns candidate dict or None."""
    ym_id = str(track_data.get("id", ""))
    if not ym_id:
        return None
    try:
        ym_id_int = int(ym_id)
    except (ValueError, TypeError):
        return None
    if ym_id_int in excluded:
        return None

    title = track_data.get("title", "")
    duration = track_data.get("durationMs", 0) or 0

    if duration < _MIN_DURATION_MS:
        return None
    if not _is_techno(track_data):
        return None
    if _has_bad_version(title):
        return None

    artists = ", ".join(a.get("name", "") for a in track_data.get("artists", []))
    albums: list[dict[str, Any]] = track_data.get("albums", [])
    album_id = str(albums[0]["id"]) if albums else ""

    return {
        "ym_track_id": ym_id,
        "ym_id_int": ym_id_int,
        "album_id": album_id,
        "title": title,
        "artists": artists,
        "duration_ms": duration,
        "genre": albums[0].get("genre", "") if albums else "",
    }


class CandidateDiscoveryService(BaseService):
    """Discover, filter, and import techno tracks from Yandex Music."""

    def __init__(self, session: AsyncSession, ym_client: YandexMusicClient) -> None:
        super().__init__()
        self.session = session
        self.ym = ym_client

    async def get_existing_ym_ids(self) -> set[int]:
        """Get all YM track IDs already in the database."""
        stmt = select(ProviderTrackId.provider_track_id).where(
            ProviderTrackId.provider_id == _YM_PROVIDER_ID,
        )
        rows = await self.session.execute(stmt)
        return {int(r[0]) for r in rows}

    async def get_ym_id_to_track_id(self) -> dict[int, int]:
        """Get mapping of ym_id -> track_id for existing tracks."""
        stmt = select(
            ProviderTrackId.provider_track_id,
            ProviderTrackId.track_id,
        ).where(ProviderTrackId.provider_id == _YM_PROVIDER_ID)
        rows = await self.session.execute(stmt)
        return {int(r[0]): r[1] for r in rows}

    async def get_playlist_seed_ids(self, playlist_id: int) -> list[int]:
        """Get YM track IDs from a playlist for use as seeds."""
        stmt = (
            select(ProviderTrackId.provider_track_id)
            .join(DjPlaylistItem, ProviderTrackId.track_id == DjPlaylistItem.track_id)
            .where(
                DjPlaylistItem.playlist_id == playlist_id,
                ProviderTrackId.provider_id == _YM_PROVIDER_ID,
            )
        )
        rows = (await self.session.execute(stmt)).fetchall()
        return [int(r[0]) for r in rows]

    async def discover_from_seeds(
        self,
        seed_ids: list[int],
        excluded: set[int],
        batch_size: int = 20,
    ) -> list[dict[str, object]]:
        """Discover candidates from multiple seeds with dedup and filtering."""
        all_candidates: list[dict[str, object]] = []
        seen = set(excluded)

        for seed_id in seed_ids:
            try:
                similar = await self.ym.get_similar_tracks(str(seed_id))
            except (httpx.HTTPError, TimeoutError, ValueError):
                logger.exception("Seed %s failed", seed_id)
                continue

            for track_data in similar:
                candidate = filter_candidate(track_data, seen)
                if candidate is None:
                    continue
                all_candidates.append(candidate)
                seen.add(candidate["ym_id_int"])  # type: ignore[arg-type]
                if len(all_candidates) >= batch_size * len(seed_ids):
                    break

        return all_candidates

    async def import_and_add_to_playlist(
        self,
        candidates: list[dict[str, Any]],
        playlist_id: int,
        existing_ym: dict[int, int],
    ) -> dict[str, Any]:
        """Import new tracks to DB and add to playlist.

        Returns dict with imported, already_exists, added_to_playlist, errors.
        """
        # Get current max sort_index
        max_idx_stmt = select(func.max(DjPlaylistItem.sort_index)).where(
            DjPlaylistItem.playlist_id == playlist_id,
        )
        max_idx_row = await self.session.execute(max_idx_stmt)
        next_idx = (max_idx_row.scalar() or 0) + 1

        # Get track_ids already in playlist
        pl_stmt = select(DjPlaylistItem.track_id).where(
            DjPlaylistItem.playlist_id == playlist_id,
        )
        pl_rows = await self.session.execute(pl_stmt)
        playlist_track_ids: set[int] = {r[0] for r in pl_rows}

        imported = 0
        already_exists = 0
        added_to_playlist = 0
        errors: list[str] = []
        existing_ym_ids = set(existing_ym.keys())

        # Batch fetch full metadata from YM
        ym_ids_to_fetch = [c["ym_track_id"] for c in candidates]
        full_metadata: dict[str, dict[str, Any]] = {}

        for batch_start in range(0, len(ym_ids_to_fetch), 50):
            batch = ym_ids_to_fetch[batch_start : batch_start + 50]
            try:
                result = await self.ym.fetch_tracks(batch)
                full_metadata.update(result)
            except (httpx.HTTPError, TimeoutError, ValueError):
                logger.exception("Metadata fetch failed batch %d", batch_start)
                errors.append(f"Metadata fetch failed for batch {batch_start}")
            await asyncio.sleep(1.5)

        for candidate in candidates:
            ym_id = candidate["ym_track_id"]
            ym_id_int = candidate["ym_id_int"]

            try:
                if ym_id_int in existing_ym_ids:
                    already_exists += 1
                    track_id = existing_ym.get(ym_id_int)
                    if track_id and track_id not in playlist_track_ids:
                        self.session.add(
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

                raw_track = full_metadata.get(ym_id)
                parsed = parse_ym_track(raw_track) if raw_track else None

                title = parsed.title if parsed else candidate["title"]
                duration_ms = (
                    parsed.duration_ms
                    if parsed and parsed.duration_ms
                    else candidate["duration_ms"]
                )
                track = Track(title=title, duration_ms=duration_ms or 0, status=0)
                self.session.add(track)
                await self.session.flush()

                self.session.add(
                    ProviderTrackId(
                        track_id=track.track_id,
                        provider_id=_YM_PROVIDER_ID,
                        provider_track_id=ym_id,
                    )
                )

                if parsed:
                    self.session.add(
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
                    self.session.add(
                        YandexMetadata(
                            track_id=track.track_id,
                            yandex_track_id=ym_id,
                            yandex_album_id=candidate.get("album_id"),
                            duration_ms=candidate["duration_ms"],
                        )
                    )

                await self.session.flush()
                imported += 1

                if track.track_id not in playlist_track_ids:
                    self.session.add(
                        DjPlaylistItem(
                            playlist_id=playlist_id,
                            track_id=track.track_id,
                            sort_index=next_idx,
                        )
                    )
                    next_idx += 1
                    added_to_playlist += 1
                    playlist_track_ids.add(track.track_id)

            except Exception as exc:
                logger.exception("Failed to import track %s", ym_id)
                errors.append(f"Track {ym_id}: {exc}")

        await self.session.flush()

        return {
            "imported": imported,
            "already_exists": already_exists,
            "added_to_playlist": added_to_playlist,
            "errors": errors,
        }
