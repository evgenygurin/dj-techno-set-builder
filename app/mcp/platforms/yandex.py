"""YandexMusicAdapter — wraps YandexMusicClient to MusicPlatform protocol."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from app.clients.yandex_music import YandexMusicClient, parse_ym_track
from app.mcp.platforms.protocol import (
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)

logger = logging.getLogger(__name__)


class YandexMusicAdapter:
    """Adapter wrapping YandexMusicClient to the MusicPlatform interface."""

    def __init__(self, client: YandexMusicClient, user_id: str) -> None:
        self._client = client
        self._user_id = user_id

    @property
    def name(self) -> str:
        return "ym"

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        return frozenset({
            PlatformCapability.SEARCH,
            PlatformCapability.DOWNLOAD,
            PlatformCapability.PLAYLIST_READ,
            PlatformCapability.PLAYLIST_WRITE,
            PlatformCapability.LIKES,
        })

    async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]:
        raw_tracks = await self._client.search_tracks(query)
        return [self._to_platform_track(t) for t in raw_tracks[:limit]]

    async def get_track(self, platform_id: str) -> PlatformTrack:
        raw_list = await self._client.fetch_tracks_metadata([platform_id])
        if not raw_list:
            msg = f"YM track {platform_id} not found"
            raise ValueError(msg)
        return self._to_platform_track(raw_list[0])

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        result = await self._client.fetch_playlist(self._user_id, platform_id)
        track_ids: list[str] = []
        for item in result.get("tracks", []):
            track_data = item.get("track", item)
            track_id = track_data.get("id")
            if track_id is not None:
                track_ids.append(str(track_id))
        return PlatformPlaylist(
            platform_id=platform_id,
            name=result.get("title", ""),
            track_ids=track_ids,
            owner_id=self._user_id,
        )

    async def create_playlist(self, name: str, track_ids: list[str]) -> str:
        uid = int(self._user_id)
        kind = await self._client.create_playlist(uid, name)
        if track_ids:
            # Resolve albumIds — YM API requires non-empty albumId
            ym_tracks = await self._resolve_track_albums(track_ids)
            if ym_tracks:
                await self._client.add_tracks_to_playlist(uid, kind, ym_tracks)
        return str(kind)

    async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        uid = int(self._user_id)
        ym_tracks = await self._resolve_track_albums(track_ids)
        if ym_tracks:
            await self._client.add_tracks_to_playlist(uid, int(playlist_id), ym_tracks)

    async def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        """Remove tracks by finding their indices in the playlist."""
        uid = int(self._user_id)
        kind = int(playlist_id)
        result = await self._client.fetch_playlist(self._user_id, playlist_id)
        revision = result.get("revision", 1)
        items = result.get("tracks", [])

        remove_set = set(track_ids)
        # Delete in reverse order to keep indices stable
        for i in range(len(items) - 1, -1, -1):
            track_data = items[i].get("track", items[i])
            if str(track_data.get("id", "")) in remove_set:
                await self._client.remove_tracks_from_playlist(uid, kind, i, i + 1, revision)
                revision += 1

    async def delete_playlist(self, playlist_id: str) -> None:
        await self._client.delete_playlist(int(self._user_id), int(playlist_id))

    async def get_download_url(self, track_id: str, *, bitrate: int = 320) -> str | None:
        with contextlib.suppress(Exception):
            return await self._client.resolve_download_url(track_id, prefer_bitrate=bitrate)
        return None

    async def close(self) -> None:
        await self._client.close()

    # --- Internal ---

    async def _resolve_track_albums(self, track_ids: list[str]) -> list[dict[str, str]]:
        """Fetch albumId for each track — YM API rejects empty albumId."""
        data = await self._client.fetch_tracks(track_ids)
        result: list[dict[str, str]] = []
        for tid in track_ids:
            track = data.get(tid)
            if not track:
                continue
            albums = track.get("albums", [])
            album_id = str(albums[0]["id"]) if albums else ""
            result.append({"id": tid, "albumId": album_id})
        return result

    @staticmethod
    def _to_platform_track(raw: dict[str, Any]) -> PlatformTrack:
        parsed = parse_ym_track(raw)
        return PlatformTrack(
            platform_id=parsed.yandex_track_id,
            title=parsed.title,
            artists=parsed.artists,
            duration_ms=parsed.duration_ms,
            cover_uri=parsed.cover_uri,
            album_title=parsed.album_title,
            genre=parsed.album_genre,
        )
