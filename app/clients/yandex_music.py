"""Yandex Music API HTTP client."""

from __future__ import annotations

from typing import Any, cast

import httpx

_DEFAULT_BASE = "https://api.music.yandex.net:443"


class YandexMusicClient:
    """Thin async wrapper around Yandex Music REST API.

    Note: a second, extended client exists at ``app/services/yandex_music_client.py``
    with rate limiting, download support, and batch operations.
    TODO(P2-14): Consolidate both into one client with optional features.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = _DEFAULT_BASE,
        http_client: httpx.AsyncClient | Any = None,
    ) -> None:
        self._token = token
        self._base = base_url
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient | Any:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"OAuth {self._token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        client = await self._client()
        resp = await client.get(f"{self._base}{path}", headers=self._headers(), params=params)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def _post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        resp = await client.post(f"{self._base}{path}", headers=self._headers(), data=data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    # --- Public API ---

    async def search_tracks(self, query: str, *, page: int = 0) -> list[dict[str, Any]]:
        data = await self._get("/search", text=query, type="track", page=page)
        tracks = data.get("result", {}).get("tracks", {}).get("results", [])
        return cast(list[dict[str, Any]], tracks)

    async def fetch_tracks(self, track_ids: list[str]) -> dict[str, dict[str, Any]]:
        data = await self._post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return {str(t["id"]): t for t in data.get("result", [])}

    async def create_playlist(
        self,
        user_id: int,
        title: str,
        visibility: str = "private",
    ) -> int:
        """Create a new YM playlist. Returns playlist kind (numeric ID)."""
        data = await self._post_form(
            f"/users/{user_id}/playlists/create",
            {"title": title, "visibility": visibility},
        )
        return int(data["result"]["kind"])

    async def add_tracks_to_playlist(
        self,
        user_id: int,
        kind: int,
        tracks: list[dict[str, str]],
        revision: int = 1,
    ) -> None:
        """Add tracks to a YM playlist via diff insert operation."""
        import json as _json

        diff = [{"op": "insert", "at": 0, "tracks": tracks}]
        await self._post_form(
            f"/users/{user_id}/playlists/{kind}/change",
            {"diff": _json.dumps(diff, ensure_ascii=False), "revision": str(revision)},
        )

    async def fetch_playlist_tracks(
        self,
        user_id: str,
        kind: str,
    ) -> list[dict[str, Any]]:
        """Fetch all tracks from a YM playlist."""
        data = await self._get(f"/users/{user_id}/playlists/{kind}")
        return cast(list[dict[str, Any]], data.get("result", {}).get("tracks", []))

    async def get_similar_tracks(self, track_id: str) -> list[dict[str, Any]]:
        """Fetch similar tracks for a given track ID."""
        data = await self._get(f"/tracks/{track_id}/similar")
        result = data.get("result", {})
        return cast(list[dict[str, Any]], result.get("similarTracks", []))

    async def close(self) -> None:
        if self._http and hasattr(self._http, "aclose"):
            await self._http.aclose()
            self._http = None
