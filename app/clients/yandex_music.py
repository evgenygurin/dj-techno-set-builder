"""Yandex Music API HTTP client.

Single unified client with rate limiting, search, batch fetch,
playlist CRUD, download (3-step signed URL), and similar tracks.
"""

from __future__ import annotations

import asyncio
import hashlib
import json as _json
import logging
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

_YM_BASE = "https://api.music.yandex.net"
_SIGN_SALT = "XGRlBW9FXlekgbPrRHuSiA"
_REQUEST_DELAY = 0.25  # seconds between API calls

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parsed track DTO
# ---------------------------------------------------------------------------


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
    artists = [a["name"] for a in track.get("artists", []) if not a.get("various", False)]
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


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------


class YandexMusicClient:
    """Async HTTP client for Yandex Music REST API.

    Features:
    - Rate limiting (configurable delay between requests)
    - Search, batch track fetch, similar tracks
    - Playlist CRUD (create, add tracks, delete, fetch)
    - Download with 3-step signed URL resolution
    """

    def __init__(
        self,
        token: str,
        *,
        user_id: str = "",
        base_url: str = _YM_BASE,
        request_delay: float = _REQUEST_DELAY,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._user_id = user_id
        self._base = base_url
        self._request_delay = request_delay
        self._http: httpx.AsyncClient | None = http_client
        self._last_request_at: float = 0
        self._rate_limit_lock = asyncio.Lock()

    # --- Internal HTTP helpers ---

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"OAuth {self._token}",
            "Accept": "application/json",
        }

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between requests (async-safe)."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self._request_delay:
                await asyncio.sleep(self._request_delay - elapsed)
            self._last_request_at = time.monotonic()

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        await self._rate_limit()
        client = await self._client()
        resp = await client.get(f"{self._base}{path}", headers=self._headers(), params=params)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def _post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        await self._rate_limit()
        client = await self._client()
        resp = await client.post(f"{self._base}{path}", headers=self._headers(), data=data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    # --- Search ---

    async def search_tracks(self, query: str, *, page: int = 0) -> list[dict[str, Any]]:
        """Search YM for tracks. Returns list of raw track dicts."""
        data = await self._get("/search", text=query, type="track", page=page)
        tracks = data.get("result", {}).get("tracks", {}).get("results", [])
        return cast(list[dict[str, Any]], tracks)

    # --- Track metadata ---

    async def fetch_tracks(self, track_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Batch fetch tracks by IDs. Returns dict keyed by track ID."""
        data = await self._post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return {str(t["id"]): t for t in data.get("result", [])}

    async def fetch_tracks_metadata(self, track_ids: list[str]) -> list[dict[str, Any]]:
        """Batch fetch track metadata by IDs. Returns list."""
        data = await self._post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return cast(list[dict[str, Any]], data.get("result", []))

    async def get_similar_tracks(self, track_id: str) -> list[dict[str, Any]]:
        """Fetch similar tracks for a given track ID."""
        data = await self._get(f"/tracks/{track_id}/similar")
        result = data.get("result", {})
        return cast(list[dict[str, Any]], result.get("similarTracks", []))

    # --- Playlists ---

    async def fetch_playlist_tracks(
        self, user_id: str, kind: str
    ) -> list[dict[str, Any]]:
        """Fetch all tracks from a YM playlist."""
        data = await self._get(f"/users/{user_id}/playlists/{kind}")
        return cast(list[dict[str, Any]], data.get("result", {}).get("tracks", []))

    async def fetch_user_playlists(self, user_id: str) -> list[dict[str, Any]]:
        """List all playlists for a user."""
        data = await self._get(f"/users/{user_id}/playlists/list")
        return cast(list[dict[str, Any]], data.get("result", []))

    async def create_playlist(
        self, user_id: int, title: str, visibility: str = "private"
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
        diff = [{"op": "insert", "at": 0, "tracks": tracks}]
        await self._post_form(
            f"/users/{user_id}/playlists/{kind}/change",
            {"diff": _json.dumps(diff, ensure_ascii=False), "revision": str(revision)},
        )

    async def delete_playlist(self, user_id: int, kind: int) -> None:
        """Delete a YM playlist."""
        await self._post_form(f"/users/{user_id}/playlists/{kind}/delete", {})

    # --- Download (3-step signed URL) ---

    async def resolve_download_url(self, track_id: str, *, prefer_bitrate: int = 320) -> str:
        """Resolve a direct download URL for a track.

        1. GET /tracks/{id}/download-info → pick best bitrate
        2. GET downloadInfoUrl → XML (host, path, ts, s)
        3. Build signed URL: https://{host}/get-mp3/{sign}/{ts}{path}
        """
        data = await self._get(f"/tracks/{track_id}/download-info")
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

        sign = hashlib.md5((_SIGN_SALT + path[1:] + s).encode()).hexdigest()  # noqa: S324
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

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._http:
            await self._http.aclose()
            self._http = None
