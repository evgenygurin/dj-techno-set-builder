"""Yandex Music API client.

High-level methods: search, fetch, playlist CRUD, download.
Delegates all HTTP to YandexMusicHTTP.
"""

from __future__ import annotations

import hashlib
import json as _json
import xml.etree.ElementTree as ET
from typing import Any, cast

from app.clients.yandex_music.http import YandexMusicHTTP

_SIGN_SALT = "XGRlBW9FXlekgbPrRHuSiA"


class YandexMusicClient:
    """Async client for Yandex Music REST API.

    Provides search, batch fetch, playlist CRUD, similar tracks, and download.
    """

    def __init__(self, http: YandexMusicHTTP, *, user_id: str = "") -> None:
        self._http = http
        self._user_id = user_id

    # --- Search ---

    async def search_tracks(self, query: str, *, page: int = 0) -> list[dict[str, Any]]:
        """Search YM for tracks. Returns list of raw track dicts."""
        data = await self._http.get("/search", text=query, type="track", page=page)
        tracks = data.get("result", {}).get("tracks", {}).get("results", [])
        return cast(list[dict[str, Any]], tracks)

    # --- Track metadata ---

    async def fetch_tracks(self, track_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Batch fetch tracks by IDs. Returns dict keyed by track ID."""
        data = await self._http.post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return {str(t["id"]): t for t in data.get("result", [])}

    async def fetch_tracks_metadata(self, track_ids: list[str]) -> list[dict[str, Any]]:
        """Batch fetch track metadata by IDs. Returns list."""
        data = await self._http.post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return cast(list[dict[str, Any]], data.get("result", []))

    async def get_similar_tracks(self, track_id: str) -> list[dict[str, Any]]:
        """Fetch similar tracks for a given track ID."""
        data = await self._http.get(f"/tracks/{track_id}/similar")
        return cast(list[dict[str, Any]], data.get("result", {}).get("similarTracks", []))

    # --- Playlists ---

    async def fetch_playlist_tracks(self, user_id: str, kind: str) -> list[dict[str, Any]]:
        """Fetch all tracks from a YM playlist."""
        data = await self._http.get(f"/users/{user_id}/playlists/{kind}")
        return cast(list[dict[str, Any]], data.get("result", {}).get("tracks", []))

    async def fetch_user_playlists(self, user_id: str) -> list[dict[str, Any]]:
        """List all playlists for a user."""
        data = await self._http.get(f"/users/{user_id}/playlists/list")
        return cast(list[dict[str, Any]], data.get("result", []))

    async def create_playlist(self, user_id: int, title: str, visibility: str = "private") -> int:
        """Create a new YM playlist. Returns playlist kind (numeric ID)."""
        data = await self._http.post_form(
            f"/users/{user_id}/playlists/create",
            {"title": title, "visibility": visibility},
        )
        return int(data["result"]["kind"])

    async def add_tracks_to_playlist(
        self, user_id: int, kind: int, tracks: list[dict[str, str]], revision: int = 1
    ) -> None:
        """Add tracks to a YM playlist via diff insert operation."""
        diff = [{"op": "insert", "at": 0, "tracks": tracks}]
        await self._http.post_form(
            f"/users/{user_id}/playlists/{kind}/change",
            {"diff": _json.dumps(diff, ensure_ascii=False), "revision": str(revision)},
        )

    async def delete_playlist(self, user_id: int, kind: int) -> None:
        """Delete a YM playlist."""
        await self._http.post_form(f"/users/{user_id}/playlists/{kind}/delete", {})

    # --- Download (3-step signed URL) ---

    async def resolve_download_url(self, track_id: str, *, prefer_bitrate: int = 320) -> str:
        """Resolve a direct download URL for a track.

        1. GET /tracks/{id}/download-info → pick best bitrate
        2. GET downloadInfoUrl → XML with (host, path, ts, s)
        3. Build signed URL: https://{host}/get-mp3/{sign}/{ts}{path}
        """
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

    async def download_track(self, track_id: str, dest_path: str, *, prefer_bitrate: int = 320) -> int:
        """Download track to file. Returns file size in bytes."""
        url = await self.resolve_download_url(track_id, prefer_bitrate=prefer_bitrate)
        return await self._http.stream_download(url, dest_path)

    # --- Lifecycle ---

    async def close(self) -> None:
        await self._http.close()
