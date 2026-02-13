"""Low-level Yandex Music API client with rate limiting."""
from __future__ import annotations

import asyncio
import hashlib
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.services.base import BaseService

_YM_BASE = "https://api.music.yandex.net"
_SIGN_SALT = "XGRlBW9FXlekgbPrRHuSiA"
_REQUEST_DELAY = 0.25  # seconds between API calls


@dataclass(frozen=True, slots=True)
class ParsedYmTrack:
    """Normalized data extracted from a YM track response."""

    yandex_track_id: str
    title: str
    artists: str
    duration_ms: int | None
    yandex_album_id: str | None
    album_title: str | None
    album_type: str | None
    album_genre: str | None
    album_year: int | None
    label_name: str | None
    release_date: str | None
    cover_uri: str | None
    explicit: bool
    artist_names: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def parse_ym_track(track: dict[str, Any]) -> ParsedYmTrack:
    """Defensively parse a YM track dict. Never raises on missing fields."""
    artists = [
        a["name"] for a in track.get("artists", []) if not a.get("various", False)
    ]
    album = track.get("albums", [None])[0] if track.get("albums") else None

    labels = album.get("labels", []) if album else []
    label_name: str | None = None
    if labels:
        first_label = labels[0]
        label_name = first_label if isinstance(first_label, str) else first_label.get("name")

    release_date_raw = album.get("releaseDate", "") if album else ""
    release_date = release_date_raw[:10] if release_date_raw else None

    return ParsedYmTrack(
        yandex_track_id=str(track["id"]),
        title=track.get("title", ""),
        artists=", ".join(artists),
        duration_ms=track.get("durationMs"),
        yandex_album_id=str(album["id"]) if album else None,
        album_title=album.get("title") if album else None,
        album_type=album.get("type") if album else None,
        album_genre=album.get("genre") if album else None,
        album_year=album.get("year") if album else None,
        label_name=label_name,
        release_date=release_date,
        cover_uri=track.get("coverUri"),
        explicit=track.get("explicit", False),
        artist_names=artists,
        raw=track,
    )


class YandexMusicClient(BaseService):
    """HTTP client for Yandex Music API."""

    def __init__(self, token: str, user_id: str = "") -> None:
        super().__init__()
        self._token = token
        self._user_id = user_id
        self._http: httpx.AsyncClient | None = None
        self._last_request_at: float = 0

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"OAuth {self._token}"}

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

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # --- Search ---

    async def search_tracks(self, query: str) -> list[dict[str, Any]]:
        """Search YM for tracks. Returns list of raw track dicts."""
        url = f"{_YM_BASE}/search?text={urllib.parse.quote(query)}&type=track&page=0"
        data = await self._get_json(url)
        return data.get("result", {}).get("tracks", {}).get("results", [])  # type: ignore[no-any-return]

    # --- Playlist ---

    async def fetch_playlist_tracks(
        self, user_id: str, kind: str
    ) -> list[dict[str, Any]]:
        """Fetch all tracks from a playlist."""
        url = f"{_YM_BASE}/users/{user_id}/playlists/{kind}"
        data = await self._get_json(url)
        return data.get("result", {}).get("tracks", [])  # type: ignore[no-any-return]

    async def fetch_user_playlists(self, user_id: str) -> list[dict[str, Any]]:
        url = f"{_YM_BASE}/users/{user_id}/playlists/list"
        data = await self._get_json(url)
        return data.get("result", [])  # type: ignore[no-any-return]

    # --- Batch track metadata ---

    async def fetch_tracks_metadata(
        self, track_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Batch fetch track metadata by IDs."""
        await self._rate_limit()
        client = await self._client()
        resp = await client.post(
            f"{_YM_BASE}/tracks",
            headers=self._headers(),
            data={"track-ids": ",".join(track_ids)},
        )
        resp.raise_for_status()
        return resp.json().get("result", [])  # type: ignore[no-any-return]

    # --- Download (3-step flow) ---

    async def resolve_download_url(
        self, track_id: str, *, prefer_bitrate: int = 320
    ) -> str:
        """Resolve a direct download URL for a track.

        1. GET /tracks/{id}/download-info → pick best bitrate
        2. GET downloadInfoUrl → XML (host, path, ts, s)
        3. Build signed URL: https://{host}/get-mp3/{sign}/{ts}{path}
        """
        url = f"{_YM_BASE}/tracks/{track_id}/download-info"
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
