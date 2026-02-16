"""Response filters for Yandex Music API.

Strip noise from API responses to reduce LLM context usage.
The YM API wraps every response in ``{invocationInfo, result}``:

- ``invocationInfo`` is server telemetry (req-id, hostname, exec-duration) — pure noise
- ``result`` contains the actual data but with many unused fields per object

This module provides an httpx response event hook that cleans responses
before FastMCP returns them to the LLM.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Field whitelists ──────────────────────────────────────────────────────────

_TRACK_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "title",
        "artists",
        "albums",
        "durationMs",
    }
)

_ALBUM_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "title",
        "genre",
        "year",
        "releaseDate",
        "labels",
        "trackCount",
    }
)

_ARTIST_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "name",
    }
)

_PLAYLIST_FIELDS: frozenset[str] = frozenset(
    {
        "uid",
        "kind",
        "title",
        "description",
        "visibility",
        "trackCount",
        "durationMs",
        "revision",
        "owner",
        "tags",
        "tracks",
        "created",
        "modified",
        "playlistUuid",
    }
)

# Search categories worth keeping (videos, podcasts, etc. stripped)
_SEARCH_KEEP_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "best",
        "tracks",
        "artists",
        "albums",
    }
)


# ── Object cleaners ──────────────────────────────────────────────────────────


def _is_playlist_like(obj: Any) -> bool:
    """Heuristic: dict looks like a YM Playlist (has kind + uid)."""
    return isinstance(obj, dict) and "kind" in obj and "uid" in obj


def _is_track_like(obj: Any) -> bool:
    """Heuristic: dict looks like a YM Track (has title + durationMs, but NOT a playlist)."""
    return (
        isinstance(obj, dict)
        and "durationMs" in obj
        and "title" in obj
        and "kind" not in obj  # Playlists also have title+durationMs
    )


def clean_artist(artist: dict[str, Any]) -> dict[str, Any]:
    """Keep only id and name from Artist."""
    return {k: v for k, v in artist.items() if k in _ARTIST_FIELDS}


def clean_album(album: dict[str, Any]) -> dict[str, Any]:
    """Keep only DJ-relevant fields from Album."""
    return {k: v for k, v in album.items() if k in _ALBUM_FIELDS}


def clean_playlist(playlist: dict[str, Any]) -> dict[str, Any]:
    """Keep only DJ-relevant fields from Playlist."""
    return {k: v for k, v in playlist.items() if k in _PLAYLIST_FIELDS}


def clean_track(track: dict[str, Any]) -> dict[str, Any]:
    """Clean a Track: keep DJ-relevant fields, clean nested artists/albums."""
    cleaned: dict[str, Any] = {k: v for k, v in track.items() if k in _TRACK_FIELDS}

    # Clean nested artists → keep only id + name
    if artists := cleaned.get("artists"):
        cleaned["artists"] = [clean_artist(a) for a in artists if isinstance(a, dict)]

    # Clean nested albums → keep first only, strip cover/availability/etc.
    if albums := cleaned.get("albums"):
        cleaned["albums"] = [clean_album(a) for a in albums[:1] if isinstance(a, dict)]

    return cleaned


def _clean_object_list(items: list[Any]) -> list[Any]:
    """Clean all track-like or playlist-like objects in a list."""
    result = []
    for it in items:
        if _is_playlist_like(it):
            result.append(clean_playlist(it))
        elif _is_track_like(it):
            result.append(clean_track(it))
        else:
            result.append(it)
    return result


# ── Response-level cleaners ──────────────────────────────────────────────────


def _clean_search_result(result: dict[str, Any]) -> dict[str, Any]:
    """Clean search response: strip low-value categories, clean tracks."""
    cleaned = {k: v for k, v in result.items() if k in _SEARCH_KEEP_KEYS}

    # Clean track results
    tracks_block = cleaned.get("tracks")
    if isinstance(tracks_block, dict) and "results" in tracks_block:
        tracks_block["results"] = _clean_object_list(tracks_block["results"])

    # Clean artist results
    artists_block = cleaned.get("artists")
    if isinstance(artists_block, dict) and "results" in artists_block:
        artists_block["results"] = [
            clean_artist(a) if isinstance(a, dict) else a for a in artists_block["results"]
        ]

    # Clean album results
    albums_block = cleaned.get("albums")
    if isinstance(albums_block, dict) and "results" in albums_block:
        albums_block["results"] = [
            clean_album(a) if isinstance(a, dict) else a for a in albums_block["results"]
        ]

    # Clean best result
    best = cleaned.get("best")
    if isinstance(best, dict) and isinstance(best.get("result"), dict):
        if best.get("type") == "track" and _is_track_like(best["result"]):
            best["result"] = clean_track(best["result"])
        elif best.get("type") == "artist":
            best["result"] = clean_artist(best["result"])
        elif best.get("type") == "album":
            best["result"] = clean_album(best["result"])

    return cleaned


def clean_response_body(body: dict[str, Any]) -> dict[str, Any]:
    """Strip invocationInfo, clean known response shapes.

    Handles all known YM API response structures:

    - Search: ``{result: {tracks: {results: [Track]}, ...}}``
    - Track list: ``{result: [Track]}``
    - Artist tracks: ``{result: {tracks: [Track], pager: {}}}``
    - Playlist: ``{result: {tracks: [{id, track: Track}], ...}}``
    - Album with tracks: ``{result: {volumes: [[Track]]}}``
    - Similar tracks: ``{result: {similarTracks: [Track]}}``
    - Artist brief: ``{result: {artist: {}, popularTracks: [Track]}}``
    """
    # Step 1: always strip invocationInfo
    body.pop("invocationInfo", None)

    result = body.get("result")
    if result is None:
        return body

    # Direct list of tracks (e.g. getTracks)
    if isinstance(result, list):
        body["result"] = _clean_object_list(result)
        return body

    if not isinstance(result, dict):
        return body

    # ── Search response ──
    if "searchRequestId" in result or (
        isinstance(result.get("tracks"), dict) and "results" in result.get("tracks", {})
    ):
        body["result"] = _clean_search_result(result)
        return body

    # ── Tracks list in result (artist tracks, recommendations, etc.) ──
    tracks = result.get("tracks")
    if isinstance(tracks, list) and tracks:
        first = tracks[0]
        if isinstance(first, dict):
            if "track" in first:
                # Playlist format: [{id, track: Track, timestamp}]
                for item in tracks:
                    t = item.get("track")
                    if isinstance(t, dict) and _is_track_like(t):
                        item["track"] = clean_track(t)
                    # Strip playlist-item noise (playCount, recent, etc.)
                    for k in list(item.keys()):
                        if k not in ("id", "track", "timestamp"):
                            del item[k]
            elif _is_track_like(first):
                result["tracks"] = _clean_object_list(tracks)

    # ── Album with tracks (volumes: [[Track]]) ──
    volumes = result.get("volumes")
    if isinstance(volumes, list):
        result["volumes"] = [
            _clean_object_list(vol) if isinstance(vol, list) else vol for vol in volumes
        ]

    # ── Similar tracks ──
    similar = result.get("similarTracks")
    if isinstance(similar, list):
        result["similarTracks"] = _clean_object_list(similar)

    # ── Artist brief info: popularTracks ──
    popular = result.get("popularTracks")
    if isinstance(popular, list):
        result["popularTracks"] = _clean_object_list(popular)

    # ── Artist brief info: clean the artist object itself ──
    artist_obj = result.get("artist")
    if isinstance(artist_obj, dict) and "name" in artist_obj:
        result["artist"] = clean_artist(artist_obj)

    # ── Playlist-level cleaning: strip cover, og, colors, etc. ──
    if "kind" in result and "uid" in result:
        body["result"] = {k: v for k, v in result.items() if k in _PLAYLIST_FIELDS}
        return body

    body["result"] = result
    return body


# ── httpx event hook ──────────────────────────────────────────────────────────


async def clean_ym_response(response: httpx.Response) -> None:
    """httpx response event hook — strip noise from YM API responses.

    Runs after the response is received but before FastMCP processes it.
    Only cleans successful JSON responses; errors pass through unchanged.
    """
    if response.status_code >= 400:
        return

    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return

    await response.aread()

    try:
        body = json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(body, dict):
        return

    cleaned = clean_response_body(body)
    new_content = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode()

    response._content = new_content
    response.headers["content-length"] = str(len(new_content))
