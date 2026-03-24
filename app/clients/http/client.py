"""Base async HTTP client built on httpx.

Single reusable class for all external API integrations.
Handles: connection pooling, auth headers, rate limiting,
request/response logging, retries, error classification.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class HTTPClient:
    """Async HTTP client with built-in observability and resilience.

    Usage:
        client = HTTPClient(
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer xxx"},
            rate_limit_delay=0.25,
        )
        data = await client.get("/endpoint", param="value")
        await client.close()
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        rate_limit_delay: float = 0.0,
        max_retries: int = 0,
        retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504}),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._default_headers = headers or {}
        self._timeout = timeout
        self._rate_limit_delay = rate_limit_delay
        self._max_retries = max_retries
        self._retry_statuses = retry_statuses
        self._http: httpx.AsyncClient | None = http_client
        self._last_request_at: float = 0
        self._lock = asyncio.Lock()

    # --- Connection ---

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
            )
        return self._http

    # --- Rate limiting ---

    async def _rate_limit(self) -> None:
        if self._rate_limit_delay <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self._rate_limit_delay:
                await asyncio.sleep(self._rate_limit_delay - elapsed)
            self._last_request_at = time.monotonic()

    # --- Core request method ---

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with rate limiting, logging, and retries.

        Raises httpx.HTTPStatusError on non-retryable failures.
        """
        await self._rate_limit()
        client = await self._client()

        # Full URLs (https://...) bypass base_url — used for CDN, signed URLs, etc.
        if path.startswith(("http://", "https://")):
            url = path
        elif self._base_url:
            url = f"{self._base_url}{path}"
        else:
            url = path
        merged_headers = {**self._default_headers, **(headers or {})}

        last_exc: httpx.HTTPStatusError | None = None
        attempts = 1 + self._max_retries

        for attempt in range(attempts):
            logger.debug(
                "HTTP %s %s (attempt %d/%d)",
                method, path, attempt + 1, attempts,
            )
            try:
                resp = await client.request(
                    method, url,
                    headers=merged_headers,
                    params=params,
                    data=data,
                    json=json,
                )
                resp.raise_for_status()

                logger.debug(
                    "HTTP %s %s → %d (%d bytes)",
                    method, path, resp.status_code, len(resp.content),
                )
                return resp

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                logger.warning(
                    "HTTP %s %s → %d (attempt %d/%d)",
                    method, path, status, attempt + 1, attempts,
                )
                if status not in self._retry_statuses or attempt == attempts - 1:
                    raise
                backoff = min(2 ** attempt, 30)
                await asyncio.sleep(backoff)

            except httpx.ConnectError:
                logger.error("HTTP %s %s → connection failed", method, path)
                raise

        # Should not reach here, but satisfy type checker
        assert last_exc is not None  # noqa: S101
        raise last_exc

    # --- Convenience methods ---

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET request, return parsed JSON."""
        resp = await self.request("GET", path, params=params or None)
        return cast(dict[str, Any], resp.json())

    async def post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST form-encoded, return parsed JSON."""
        resp = await self.request("POST", path, data=data)
        return cast(dict[str, Any], resp.json())

    async def post_json(self, path: str, payload: Any) -> dict[str, Any]:
        """POST JSON body, return parsed JSON."""
        resp = await self.request("POST", path, json=payload)
        return cast(dict[str, Any], resp.json())

    async def get_raw(self, url: str) -> httpx.Response:
        """GET an arbitrary full URL (no base_url prefix). Returns raw response."""
        resp = await self.request("GET", url)
        return resp

    async def stream_download(self, url: str, dest_path: str) -> int:
        """Stream-download a file to disk. Returns size in bytes."""
        await self._rate_limit()
        client = await self._client()
        async with client.stream("GET", url) as stream:
            stream.raise_for_status()
            size = 0
            with open(dest_path, "wb") as f:
                async for chunk in stream.aiter_bytes(65536):
                    f.write(chunk)
                    size += len(chunk)
        logger.debug("Downloaded %s → %d bytes", dest_path, size)
        return size

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying connection pool."""
        if self._http:
            await self._http.aclose()
            self._http = None
