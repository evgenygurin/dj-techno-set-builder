"""Yandex Music client package.

Structure:
- http.py       — low-level HTTP transport (rate limiting, auth, error handling)
- client.py     — API client (search, fetch, playlist CRUD, download)
- types.py      — ParsedYmTrack dataclass + parse_ym_track()
- importer.py   — ImportYandexService (search/fetch → create all DB entities)
- downloader.py — DownloadService (resolve signed URL → download MP3)
"""

from app.clients.yandex_music.client import YandexMusicClient
from app.clients.yandex_music.downloader import DownloadResult, DownloadService
from app.clients.yandex_music.http import YandexMusicHTTP
from app.clients.yandex_music.importer import ImportYandexService
from app.clients.yandex_music.types import ParsedYmTrack, parse_ym_track

__all__ = [
    "DownloadResult",
    "DownloadService",
    "ImportYandexService",
    "ParsedYmTrack",
    "YandexMusicClient",
    "YandexMusicHTTP",
    "create_ym_client",
    "parse_ym_track",
]


def create_ym_client(
    token: str,
    *,
    user_id: str = "",
    base_url: str = "https://api.music.yandex.net",
) -> YandexMusicClient:
    """Convenience factory — creates HTTP transport + client in one call."""
    http = YandexMusicHTTP(token=token, base_url=base_url)
    return YandexMusicClient(http, user_id=user_id)
