"""Yandex Music API HTTP client."""

from __future__ import annotations

from typing import Any

import httpx

_DEFAULT_BASE = "https://api.music.yandex.net:443"


class YandexMusicClient:
    """Thin async wrapper around Yandex Music REST API."""

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
        return resp.json()  # type: ignore[no-any-return]

    async def _post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        resp = await client.post(f"{self._base}{path}", headers=self._headers(), data=data)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # --- Public API ---

    async def search_tracks(self, query: str, *, page: int = 0) -> list[dict[str, Any]]:
        data = await self._get("/search", text=query, type="track", page=page)
        return data.get("result", {}).get("tracks", {}).get("results", [])  # type: ignore[no-any-return]

    async def fetch_tracks(self, track_ids: list[str]) -> dict[str, dict[str, Any]]:
        data = await self._post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return {str(t["id"]): t for t in data.get("result", [])}

    async def close(self) -> None:
        if self._http and hasattr(self._http, "aclose"):
            await self._http.aclose()
            self._http = None
