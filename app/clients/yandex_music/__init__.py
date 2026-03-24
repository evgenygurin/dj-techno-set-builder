"""Yandex Music client package.

Structure:
- client.py     — API client (search, fetch, playlist CRUD, download)
- types.py      — ParsedYmTrack dataclass + parse_ym_track()
- importer.py   — ImportYandexService (search/fetch → create all DB entities)
- downloader.py — DownloadService (resolve signed URL → download MP3)

HTTP transport is provided by app.clients.http.HTTPClient.
"""

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
    "parse_ym_track",
]

_YM_BASE = "https://api.music.yandex.net"


def create_ym_client(
    token: str,
    *,
    user_id: str = "",
    base_url: str = _YM_BASE,
) -> YandexMusicClient:
    """Convenience factory — creates HTTPClient + YandexMusicClient."""
    http = HTTPClient(
        base_url=base_url,
        headers={
            "Authorization": f"OAuth {token}",
            "Accept": "application/json",
        },
        rate_limit_delay=0.25,
        max_retries=1,
    )
    return YandexMusicClient(http, user_id=user_id)
