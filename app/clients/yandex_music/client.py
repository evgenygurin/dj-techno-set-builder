"""Yandex Music API client.

Full coverage of YM REST API. Each public method is decorated with
@tool() from fastmcp.tools so it can be registered as an MCP tool
via mcp.add_tool(client.method) — self is hidden automatically.

Uses app.clients.http.HTTPClient for all HTTP operations.
"""

from __future__ import annotations

import hashlib
import json as _json
import xml.etree.ElementTree as ET
from typing import Any, cast

from fastmcp.tools import tool

from app.clients.http import HTTPClient

_SIGN_SALT = "XGRlBW9FXlekgbPrRHuSiA"
_RO = {"readOnlyHint": True}


class YandexMusicClient:
    """Async client for Yandex Music REST API."""

    def __init__(self, http: HTTPClient, *, user_id: str = "") -> None:
        self._http = http
        self._user_id = user_id

    # ── Search ────────────────────────────────────────────

    @tool(tags={"ym", "search"}, annotations=_RO)
    async def search(
        self,
        query: str,
        *,
        type: str = "track",
        page: int = 0,
        nocorrect: bool = False,
    ) -> dict[str, Any]:
        """Universal YM search. Returns full result dict.

        Args:
            query: Search text.
            type: One of 'track', 'album', 'artist', 'playlist', 'all'.
            page: Page number (0-based, 20 results per page).
            nocorrect: If True, disable YM's auto-correction of typos.
        """
        data = await self._http.get(
            "/search", text=query, type=type, page=page, nocorrect=nocorrect
        )
        return cast(dict[str, Any], data.get("result", {}))

    @tool(tags={"ym", "search"}, annotations=_RO)
    async def search_tracks(
        self, query: str, *, page: int = 0, nocorrect: bool = False
    ) -> list[dict[str, Any]]:
        """Search tracks by text query."""
        result = await self.search(query, type="track", page=page, nocorrect=nocorrect)
        return cast(list[dict[str, Any]], result.get("tracks", {}).get("results", []))

    # ── Tracks ────────────────────────────────────────────

    @tool(tags={"ym", "track"}, annotations=_RO)
    async def fetch_tracks(
        self, track_ids: list[str], *, with_positions: bool = False
    ) -> dict[str, dict[str, Any]]:
        """Batch fetch tracks by IDs. Returns dict keyed by track ID."""
        form: dict[str, Any] = {"track-ids": ",".join(track_ids)}
        if with_positions:
            form["with-positions"] = "true"
        data = await self._http.post_form("/tracks", form)
        return {str(t["id"]): t for t in data.get("result", [])}

    @tool(tags={"ym", "track"}, annotations=_RO)
    async def fetch_tracks_metadata(
        self, track_ids: list[str], *, with_positions: bool = False
    ) -> list[dict[str, Any]]:
        """Batch fetch track metadata. Returns list."""
        form: dict[str, Any] = {"track-ids": ",".join(track_ids)}
        if with_positions:
            form["with-positions"] = "true"
        data = await self._http.post_form("/tracks", form)
        return cast(list[dict[str, Any]], data.get("result", []))

    @tool(tags={"ym", "track"}, annotations=_RO)
    async def get_similar_tracks(self, track_id: str) -> list[dict[str, Any]]:
        """Fetch similar tracks for a given track ID."""
        data = await self._http.get(f"/tracks/{track_id}/similar")
        return cast(list[dict[str, Any]], data.get("result", {}).get("similarTracks", []))

    @tool(tags={"ym", "track"}, annotations=_RO)
    async def get_track_supplement(self, track_id: str) -> dict[str, Any]:
        """Fetch track supplement (lyrics availability, videos, etc.)."""
        data = await self._http.get(f"/tracks/{track_id}/supplement")
        return cast(dict[str, Any], data.get("result", {}))

    # ── Albums ────────────────────────────────────────────

    @tool(tags={"ym", "album"}, annotations=_RO)
    async def get_album(self, album_id: int) -> dict[str, Any]:
        """Fetch album metadata by ID."""
        data = await self._http.get(f"/albums/{album_id}")
        return cast(dict[str, Any], data.get("result", {}))

    @tool(tags={"ym", "album"}, annotations=_RO)
    async def get_album_with_tracks(self, album_id: int) -> dict[str, Any]:
        """Fetch album with full track listing."""
        data = await self._http.get(f"/albums/{album_id}/with-tracks")
        return cast(dict[str, Any], data.get("result", {}))

    @tool(tags={"ym", "album"}, annotations=_RO)
    async def fetch_albums(self, album_ids: list[int]) -> list[dict[str, Any]]:
        """Batch fetch albums by IDs."""
        data = await self._http.post_form(
            "/albums", {"album-ids": ",".join(str(a) for a in album_ids)}
        )
        return cast(list[dict[str, Any]], data.get("result", []))

    # ── Artists ───────────────────────────────────────────

    @tool(tags={"ym", "artist"}, annotations=_RO)
    async def get_artist_tracks(
        self, artist_id: int, *, page: int = 0, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """Fetch tracks by artist ID with pagination."""
        data = await self._http.get(
            f"/artists/{artist_id}/tracks", page=page, **{"page-size": page_size}
        )
        return cast(list[dict[str, Any]], data.get("result", {}).get("tracks", []))

    @tool(tags={"ym", "artist"}, annotations=_RO)
    async def get_artist_albums(
        self, artist_id: int, *, page: int = 0, page_size: int = 20, sort_by: str = "year"
    ) -> list[dict[str, Any]]:
        """Fetch albums by artist ID with pagination."""
        data = await self._http.get(
            f"/artists/{artist_id}/direct-albums",
            page=page,
            **{"page-size": page_size, "sort-by": sort_by},
        )
        return cast(list[dict[str, Any]], data.get("result", {}).get("albums", []))

    @tool(tags={"ym", "artist"}, annotations=_RO)
    async def get_popular_tracks(self, artist_id: int) -> list[dict[str, Any]]:
        """Fetch popular tracks for an artist (sorted by rating)."""
        data = await self._http.get(f"/artists/{artist_id}/track-ids-by-rating")
        return cast(list[dict[str, Any]], data.get("result", {}).get("tracks", []))

    # ── Genres ────────────────────────────────────────────

    @tool(tags={"ym", "genre"}, annotations=_RO)
    async def get_genres(self) -> list[dict[str, Any]]:
        """Fetch all YM music genres."""
        data = await self._http.get("/genres")
        return cast(list[dict[str, Any]], data.get("result", []))

    # ── Playlists ─────────────────────────────────────────

    @tool(tags={"ym", "playlist"}, annotations=_RO)
    async def fetch_playlist(self, user_id: str, kind: str) -> dict[str, Any]:
        """Fetch full playlist object (metadata + tracks)."""
        data = await self._http.get(f"/users/{user_id}/playlists/{kind}")
        return cast(dict[str, Any], data.get("result", {}))

    @tool(tags={"ym", "playlist"}, annotations=_RO)
    async def fetch_playlist_tracks(self, user_id: str, kind: str) -> list[dict[str, Any]]:
        """Fetch all tracks from a playlist."""
        result = await self.fetch_playlist(user_id, kind)
        return cast(list[dict[str, Any]], result.get("tracks", []))

    @tool(tags={"ym", "playlist"}, annotations=_RO)
    async def fetch_user_playlists(self, user_id: str) -> list[dict[str, Any]]:
        """List all playlists for a user."""
        data = await self._http.get(f"/users/{user_id}/playlists/list")
        return cast(list[dict[str, Any]], data.get("result", []))

    @tool(tags={"ym", "playlist"}, annotations=_RO)
    async def fetch_playlists_by_ids(self, playlist_ids: list[str]) -> list[dict[str, Any]]:
        """Batch fetch playlists by 'uid:kind' pairs."""
        data = await self._http.post_form(
            "/playlists/list", {"playlistIds": _json.dumps(playlist_ids)}
        )
        return cast(list[dict[str, Any]], data.get("result", []))

    @tool(tags={"ym", "playlist"}, annotations=_RO)
    async def get_playlist_recommendations(
        self, user_id: int, kind: int
    ) -> list[dict[str, Any]]:
        """Fetch recommended tracks for a playlist."""
        data = await self._http.get(f"/users/{user_id}/playlists/{kind}/recommendations")
        return cast(list[dict[str, Any]], data.get("result", {}).get("tracks", []))

    @tool(tags={"ym", "playlist"})
    async def create_playlist(
        self, user_id: int, title: str, visibility: str = "private"
    ) -> int:
        """Create a new YM playlist. Returns playlist kind (numeric ID)."""
        data = await self._http.post_form(
            f"/users/{user_id}/playlists/create",
            {"title": title, "visibility": visibility},
        )
        return int(data["result"]["kind"])

    @tool(tags={"ym", "playlist"})
    async def rename_playlist(self, user_id: int, kind: int, new_name: str) -> None:
        """Rename an existing playlist."""
        await self._http.post_form(
            f"/users/{user_id}/playlists/{kind}/name",
            {"value": new_name},
        )

    @tool(tags={"ym", "playlist"})
    async def set_playlist_visibility(
        self, user_id: int, kind: int, visibility: str
    ) -> None:
        """Set playlist visibility ('public' or 'private')."""
        await self._http.post_form(
            f"/users/{user_id}/playlists/{kind}/visibility",
            {"value": visibility},
        )

    @tool(tags={"ym", "playlist"})
    async def add_tracks_to_playlist(
        self, user_id: int, kind: int, tracks: list[dict[str, str]], revision: int = 1
    ) -> None:
        """Add tracks via diff insert. Each track needs 'id' and 'albumId'."""
        diff = [{"op": "insert", "at": 0, "tracks": tracks}]
        await self._http.post_form(
            f"/users/{user_id}/playlists/{kind}/change",
            {"diff": _json.dumps(diff, ensure_ascii=False), "revision": str(revision)},
        )

    @tool(tags={"ym", "playlist"})
    async def remove_tracks_from_playlist(
        self, user_id: int, kind: int, from_idx: int, to_idx: int, revision: int
    ) -> None:
        """Remove tracks by index range (from inclusive, to exclusive)."""
        diff = [{"op": "delete", "from": from_idx, "to": to_idx}]
        await self._http.post_form(
            f"/users/{user_id}/playlists/{kind}/change",
            {"diff": _json.dumps(diff, ensure_ascii=False), "revision": str(revision)},
        )

    @tool(tags={"ym", "playlist"})
    async def delete_playlist(self, user_id: int, kind: int) -> None:
        """Delete a YM playlist."""
        await self._http.post_form(f"/users/{user_id}/playlists/{kind}/delete", {})

    # ── Likes ─────────────────────────────────────────────

    @tool(tags={"ym", "likes"}, annotations=_RO)
    async def get_liked_track_ids(self, user_id: int) -> list[str]:
        """Fetch IDs of liked tracks."""
        data = await self._http.get(f"/users/{user_id}/likes/tracks")
        library = data.get("result", {}).get("library", {})
        tracks = library.get("tracks", [])
        return [str(t.get("id", t)) for t in tracks]

    @tool(tags={"ym", "likes"})
    async def like_tracks(self, user_id: int, track_ids: list[str]) -> None:
        """Add tracks to likes."""
        await self._http.post_form(
            f"/users/{user_id}/likes/tracks/add-multiple",
            {"track-ids": ",".join(track_ids)},
        )

    @tool(tags={"ym", "likes"})
    async def unlike_tracks(self, user_id: int, track_ids: list[str]) -> None:
        """Remove tracks from likes."""
        await self._http.post_form(
            f"/users/{user_id}/likes/tracks/remove",
            {"track-ids": ",".join(track_ids)},
        )

    @tool(tags={"ym", "likes"}, annotations=_RO)
    async def get_disliked_track_ids(self, user_id: int) -> list[str]:
        """Fetch IDs of disliked tracks."""
        data = await self._http.get(f"/users/{user_id}/dislikes/tracks")
        library = data.get("result", {}).get("library", {})
        tracks = library.get("tracks", [])
        return [str(t.get("id", t)) for t in tracks]

    # ── Download ──────────────────────────────────────────

    @tool(tags={"ym", "download"}, annotations=_RO)
    async def resolve_download_url(
        self, track_id: str, *, prefer_bitrate: int = 320
    ) -> str:
        """Resolve direct download URL via 3-step signed flow."""
        data = await self._http.get(f"/tracks/{track_id}/download-info")
        infos = data.get("result", [])
        if not infos:
            msg = f"No download info for track {track_id}"
            raise ValueError(msg)

        best = max(infos, key=lambda x: x.get("bitrateInKbps", 0))
        resp = await self._http.get_raw(best["downloadInfoUrl"])
        root = ET.fromstring(resp.text)

        host = root.findtext("host", "")
        path = root.findtext("path", "")
        ts = root.findtext("ts", "")
        s = root.findtext("s", "")

        sign = hashlib.md5((_SIGN_SALT + path[1:] + s).encode()).hexdigest()  # noqa: S324
        return f"https://{host}/get-mp3/{sign}/{ts}{path}"

    @tool(tags={"ym", "download"})
    async def download_track(
        self, track_id: str, dest_path: str, *, prefer_bitrate: int = 320
    ) -> int:
        """Download track MP3 to file. Returns size in bytes."""
        url = await self.resolve_download_url(track_id, prefer_bitrate=prefer_bitrate)
        return await self._http.stream_download(url, dest_path)

    # ── Lifecycle ─────────────────────────────────────────

    async def close(self) -> None:
        await self._http.close()
