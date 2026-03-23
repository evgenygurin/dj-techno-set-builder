"""YandexMusicAdapter — wraps YandexMusicClient to MusicPlatform protocol."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from app.infrastructure.clients.yandex_music import YandexMusicClient as YMApiClient
from app.mcp.platforms.protocol import (
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.services.yandex_music_client import YandexMusicClient, parse_ym_track

logger = logging.getLogger(__name__)


class YandexMusicAdapter:
    """Adapter wrapping YandexMusicClient to the MusicPlatform interface.

    Converts raw YM API responses to PlatformTrack/PlatformPlaylist.
    When api_client (thin HTTP client) is provided, playlist write
    operations are supported via diff-based YM API.
    """

    def __init__(
        self,
        client: YandexMusicClient,
        user_id: str,
        api_client: YMApiClient | None = None,
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._api_client = api_client

    @property
    def name(self) -> str:
        return "ym"

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        caps = {
            PlatformCapability.SEARCH,
            PlatformCapability.DOWNLOAD,
            PlatformCapability.PLAYLIST_READ,
            PlatformCapability.LIKES,
        }
        if self._api_client is not None:
            caps.add(PlatformCapability.PLAYLIST_WRITE)
        return frozenset(caps)

    async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]:
        """Search YM for tracks."""
        raw_tracks = await self._client.search_tracks(query)
        return [self._to_platform_track(t) for t in raw_tracks[:limit]]

    async def get_track(self, platform_id: str) -> PlatformTrack:
        """Fetch a single track by YM track ID."""
        raw_list = await self._client.fetch_tracks_metadata([platform_id])
        if not raw_list:
            msg = f"YM track {platform_id} not found"
            raise ValueError(msg)
        return self._to_platform_track(raw_list[0])

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        """Fetch playlist tracks by playlist kind (ID)."""
        raw_items = await self._client.fetch_playlist_tracks(self._user_id, platform_id)
        track_ids: list[str] = []
        for item in raw_items:
            track_data = item.get("track", item)
            track_id = track_data.get("id")
            if track_id is not None:
                track_ids.append(str(track_id))
        return PlatformPlaylist(
            platform_id=platform_id,
            name="",  # YM fetch_playlist_tracks doesn't return playlist name
            track_ids=track_ids,
            owner_id=self._user_id,
        )

    async def create_playlist(self, name: str, track_ids: list[str]) -> str:
        """Create a YM playlist and optionally populate with tracks.

        Returns the playlist kind (numeric ID) as string.
        """
        if self._api_client is None:
            raise NotImplementedError("API client not configured for write operations")
        uid = int(self._user_id)
        kind = await self._api_client.create_playlist(uid, name)
        if track_ids:
            ym_tracks = [{"id": tid, "albumId": ""} for tid in track_ids]
            await self._api_client.add_tracks_to_playlist(uid, kind, ym_tracks)
        return str(kind)

    async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        """Add tracks to an existing YM playlist via diff insert."""
        if self._api_client is None:
            raise NotImplementedError("API client not configured for write operations")
        uid = int(self._user_id)
        ym_tracks = [{"id": tid, "albumId": ""} for tid in track_ids]
        await self._api_client.add_tracks_to_playlist(uid, int(playlist_id), ym_tracks)

    async def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        """Not yet supported — requires revision tracking and index-based deletion."""
        raise NotImplementedError("YM playlist track removal not yet implemented")

    async def delete_playlist(self, playlist_id: str) -> None:
        """Not yet supported."""
        raise NotImplementedError("YM playlist deletion not yet implemented")

    async def get_download_url(self, track_id: str, *, bitrate: int = 320) -> str | None:
        """Resolve a direct download URL for a YM track."""
        with contextlib.suppress(Exception):
            return await self._client.resolve_download_url(track_id, prefer_bitrate=bitrate)
        return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    @staticmethod
    def _to_platform_track(raw: dict[str, Any]) -> PlatformTrack:
        """Convert raw YM track dict to PlatformTrack."""
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
