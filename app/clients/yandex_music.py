"""Yandex Music API HTTP client."""

from __future__ import annotations

import asyncio
import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

_DEFAULT_BASE = "https://api.music.yandex.net:443"
_SIGN_SALT = "XGRlBW9FXlekgbPrRHuSiA"
_REQUEST_DELAY = 0.25  # seconds between API calls


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
        self._last_request_at: float = 0

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

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < _REQUEST_DELAY:
            await asyncio.sleep(_REQUEST_DELAY - elapsed)
        self._last_request_at = time.monotonic()

    async def _get_json(self, url: str) -> dict[str, Any]:
        await self._rate_limit()
        client = await self._client()
        resp = await client.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # --- Public API ---

    async def search_tracks(self, query: str, *, page: int = 0) -> list[dict[str, Any]]:
        data = await self._get("/search", text=query, type="track", page=page)
        return data.get("result", {}).get("tracks", {}).get("results", [])  # type: ignore[no-any-return]

    async def fetch_tracks(self, track_ids: list[str]) -> dict[str, dict[str, Any]]:
        data = await self._post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return {str(t["id"]): t for t in data.get("result", [])}

    async def resolve_download_url(self, track_id: str, *, prefer_bitrate: int = 320) -> str:
        """Resolve a direct download URL for a track.

        1. GET /tracks/{id}/download-info → pick best bitrate
        2. GET downloadInfoUrl → XML (host, path, ts, s)
        3. Build signed URL: https://{host}/get-mp3/{sign}/{ts}{path}
        """
        url = f"{self._base}/tracks/{track_id}/download-info"
        data = await self._get_json(url)
        infos = data.get("result", [])
        if not infos:
            msg = f"No download info for track {track_id}"
            raise ValueError(msg)

        best = max(infos, key=lambda x: x.get("bitrateInKbps", 0))
        info_url = best["downloadInfoUrl"]

        await self._rate_limit()
        client = await self._client()
        resp = await client.get(info_url)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

        host = root.findtext("host", "")
        path = root.findtext("path", "")
        ts = root.findtext("ts", "")
        s = root.findtext("s", "")

        sign = hashlib.md5((_SIGN_SALT + path[1:] + s).encode()).hexdigest()
        return f"https://{host}/get-mp3/{sign}/{ts}{path}"

    async def download_track(
        self, track_id: str, dest_path: str, *, prefer_bitrate: int = 320
    ) -> int:
        """Download track to file. Returns file size in bytes."""
        url = await self.resolve_download_url(track_id, prefer_bitrate=prefer_bitrate)
        client = await self._client()
        async with client.stream("GET", url) as stream:
            stream.raise_for_status()
            size = 0
            with open(dest_path, "wb") as f:
                async for chunk in stream.aiter_bytes(65536):
                    f.write(chunk)
                    size += len(chunk)
        return size

    async def close(self) -> None:
        if self._http and hasattr(self._http, "aclose"):
            await self._http.aclose()
            self._http = None
