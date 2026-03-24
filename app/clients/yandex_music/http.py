"""Low-level HTTP service for Yandex Music API.

Encapsulates: connection management, auth headers, rate limiting,
error handling, retries. All YM-specific HTTP goes through here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, cast

import httpx

_YM_BASE = "https://api.music.yandex.net"
_REQUEST_DELAY = 0.25  # seconds between API calls

logger = logging.getLogger(__name__)


class YandexMusicHTTP:
    """Async HTTP transport for Yandex Music API.

    Handles auth, rate limiting, retries, and error wrapping.
    All methods return parsed JSON dicts.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = _YM_BASE,
        request_delay: float = _REQUEST_DELAY,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base = base_url
        self._request_delay = request_delay
        self._http: httpx.AsyncClient | None = http_client
        self._last_request_at: float = 0
        self._rate_limit_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"OAuth {self._token}",
            "Accept": "application/json",
        }

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between requests (async-safe)."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self._request_delay:
                await asyncio.sleep(self._request_delay - elapsed)
            self._last_request_at = time.monotonic()

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET request with auth, rate limiting, and error handling."""
        await self._rate_limit()
        client = await self._client()
        resp = await client.get(f"{self._base}{path}", headers=self._headers(), params=params)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST form-encoded request with auth and rate limiting."""
        await self._rate_limit()
        client = await self._client()
        resp = await client.post(f"{self._base}{path}", headers=self._headers(), data=data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_raw(self, url: str) -> httpx.Response:
        """GET an arbitrary URL (for download info XML, signed URLs)."""
        await self._rate_limit()
        client = await self._client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp

    async def stream_download(self, url: str, dest_path: str) -> int:
        """Stream-download a file. Returns size in bytes."""
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
        """Close the underlying HTTP connection pool."""
        if self._http:
            await self._http.aclose()
            self._http = None
