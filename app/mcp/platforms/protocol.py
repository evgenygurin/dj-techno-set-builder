"""MusicPlatform protocol — common interface for all music platforms."""

from __future__ import annotations

from enum import Enum, auto
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class PlatformCapability(Enum):
    """Capabilities a platform adapter may support."""

    SEARCH = auto()
    DOWNLOAD = auto()
    PLAYLIST_READ = auto()
    PLAYLIST_WRITE = auto()
    LIKES = auto()


class PlatformTrack(BaseModel):
    """Minimal track representation from a platform."""

    platform_id: str
    title: str
    artists: str
    duration_ms: int | None = None
    cover_uri: str | None = None
    album_title: str | None = None
    genre: str | None = None


class PlatformPlaylist(BaseModel):
    """Minimal playlist representation from a platform."""

    platform_id: str
    name: str
    track_ids: list[str]
    owner_id: str | None = None
    track_count: int | None = None


@runtime_checkable
class MusicPlatform(Protocol):
    """Common interface for all music platform adapters.

    Every adapter exposes a standard set of operations.
    Capabilities indicate which operations are actually supported.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[PlatformCapability]: ...

    async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]: ...

    async def get_track(self, platform_id: str) -> PlatformTrack: ...

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist: ...

    async def create_playlist(self, name: str, track_ids: list[str]) -> str: ...

    async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None: ...

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None: ...

    async def delete_playlist(self, playlist_id: str) -> None: ...

    async def get_download_url(self, track_id: str, *, bitrate: int = 320) -> str | None: ...

    async def close(self) -> None: ...
