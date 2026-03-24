"""Yandex Music client package.

Structure:
- client.py     — API client (search, fetch, playlist CRUD, download)
- types.py      — ParsedYmTrack dataclass + parse_ym_track()
- importer.py   — ImportYandexService (search/fetch → create all DB entities)
- downloader.py — DownloadService (resolve signed URL → download MP3)

HTTP transport is provided by app.clients.http.HTTPClient.
"""

from typing import Any

from app.clients.http import HTTPClient
from app.clients.yandex_music.client import YandexMusicClient
from app.clients.yandex_music.downloader import DownloadResult, DownloadService
from app.clients.yandex_music.importer import ImportYandexService
from app.clients.yandex_music.types import ParsedYmTrack, parse_ym_track

__all__ = [
    "DownloadResult",
    "DownloadService",
    "ImportYandexService",
    "ParsedYmTrack",
    "YandexMusicClient",
    "create_ym_client",
    "create_ym_httpx_client",
    "parse_ym_track",
]

_YM_BASE = "https://api.music.yandex.net"


def _ym_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"OAuth {token}",
        "Accept": "application/json",
    }


def create_ym_client(
    token: str,
    *,
    user_id: str = "",
    base_url: str = _YM_BASE,
) -> YandexMusicClient:
    """Create YandexMusicClient backed by HTTPClient."""
    http = HTTPClient(
        base_url=base_url,
        headers=_ym_headers(token),
        rate_limit_delay=0.25,
        max_retries=1,
    )
    return YandexMusicClient(http, user_id=user_id)


def create_ym_httpx_client(
    token: str,
    *,
    base_url: str = _YM_BASE,
    timeout: float = 30.0,
    event_hooks: dict | None = None,
) -> Any:
    """Create a raw httpx.AsyncClient for YM (for FastMCP.from_openapi).

    Same auth headers as create_ym_client, but returns bare httpx client
    because FastMCP OpenAPI integration requires it.
    """
    import httpx as _httpx

    return _httpx.AsyncClient(
        base_url=base_url,
        headers=_ym_headers(token),
        timeout=timeout,
        event_hooks=event_hooks or {},
    )
