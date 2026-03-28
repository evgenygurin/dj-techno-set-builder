"""Pydantic response types for Yandex Music MCP tools.

Each tool uses a parameterized consolidation pattern (multiple actions),
so response models use optional fields — only the fields relevant to
the current action are populated.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = [
    "YmAlbumsResult",
    "YmArtistsResult",
    "YmLikesResult",
    "YmPlaylistsResult",
    "YmSearchResult",
    "YmTracksResult",
]


class YmSearchResult(BaseModel):
    """Response from ym_search tool.

    For type='genre': only ``genres`` is populated.
    For search types: the full search result dict from YM API.
    """

    genres: list[dict[str, Any]] | None = None
    # Raw YM search result — keys depend on search type
    # (e.g. tracks.results, albums.results, etc.)
    search: dict[str, Any] | None = None


class YmTracksResult(BaseModel):
    """Response from ym_tracks tool.

    Populated fields depend on action:
    - fetch: ``tracks_by_id``
    - metadata: ``tracks``
    - similar: ``similar_tracks``
    - supplement: ``supplement``
    - download_url: ``url``
    - download: ``size_bytes`` + ``dest_path``
    """

    tracks_by_id: dict[str, dict[str, Any]] | None = None
    tracks: list[dict[str, Any]] | None = None
    similar_tracks: list[dict[str, Any]] | None = None
    supplement: dict[str, Any] | None = None
    url: str | None = None
    size_bytes: int | None = None
    dest_path: str | None = None


class YmAlbumsResult(BaseModel):
    """Response from ym_albums tool.

    - get/with_tracks: ``album``
    - batch: ``albums``
    """

    album: dict[str, Any] | None = None
    albums: list[dict[str, Any]] | None = None


class YmArtistsResult(BaseModel):
    """Response from ym_artists tool.

    All actions return a list of tracks or albums.
    """

    tracks: list[dict[str, Any]] | None = None
    albums: list[dict[str, Any]] | None = None


class YmPlaylistsResult(BaseModel):
    """Response from ym_playlists tool.

    Populated fields depend on action:
    - get: ``playlist``
    - tracks: ``tracks``
    - list/batch: ``playlists``
    - recommendations: ``tracks``
    - create: ``kind``
    - rename/visibility/add_tracks/remove_tracks/delete: ``status``
    """

    playlist: dict[str, Any] | None = None
    playlists: list[dict[str, Any]] | None = None
    tracks: list[dict[str, Any]] | None = None
    kind: int | None = None
    status: str | None = None


class YmLikesResult(BaseModel):
    """Response from ym_likes tool.

    - liked/disliked: ``track_ids``
    - like/unlike: ``status``
    """

    track_ids: list[str] | None = None
    status: str | None = None
