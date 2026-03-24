"""Yandex Music API client package.

- client.py  — YandexMusicClient (HTTP API methods)
- types.py   — ParsedYmTrack dataclass + parse_ym_track()
"""

from app.clients.http import HTTPClient
from app.clients.yandex_music.client import YandexMusicClient
from app.clients.yandex_music.types import ParsedYmTrack, parse_ym_track

__all__ = [
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
) -> object:
    """Create raw httpx.AsyncClient for FastMCP.from_openapi (requires bare httpx)."""
    import httpx

    return httpx.AsyncClient(
        base_url=base_url,
        headers=_ym_headers(token),
        timeout=timeout,
        event_hooks=event_hooks or {},
    )
