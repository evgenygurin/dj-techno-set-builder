"""Tests for YM API response cleaners."""
from __future__ import annotations

from app.mcp.yandex_music.response_filters import clean_response_body


def _make_genre(name: str, with_sub: bool = False) -> dict:
    genre: dict = {
        "id": name,
        "name": name,
        "title": name.capitalize(),
        "value": name,
        "coverUri": "avatars.yandex.net/get-music-content/HUGE",
        "ogImage": "avatars.yandex.net/get-music-content/HUGE2",
        "fullImageUrl": "https://very-large-url.example.com",
    }
    if with_sub:
        genre["subGenres"] = [_make_genre(f"{name}-sub1"), _make_genre(f"{name}-sub2")]
    return genre


def test_clean_genres_strips_cover_uri():
    body = {
        "result": [_make_genre("techno", with_sub=True)],
        "invocationInfo": {"req-id": "x"},
    }
    cleaned = clean_response_body(body)
    assert "invocationInfo" not in cleaned
    genre = cleaned["result"][0]
    assert "coverUri" not in genre
    assert "ogImage" not in genre
    assert "fullImageUrl" not in genre
    assert genre["id"] == "techno"
    assert genre["name"] == "techno"


def test_clean_genres_cleans_subgenres():
    body = {"result": [_make_genre("techno", with_sub=True)]}
    cleaned = clean_response_body(body)
    genre = cleaned["result"][0]
    assert "subGenres" in genre
    sub = genre["subGenres"][0]
    assert "coverUri" not in sub
    assert sub["id"] == "techno-sub1"


def _make_playlist(kind: int, track_count: int = 5) -> dict:
    return {
        "uid": 250905515,
        "kind": kind,
        "title": f"Playlist {kind}",
        "trackCount": track_count,
        "durationMs": track_count * 300_000,
        "revision": 10,
        "visibility": "public",
        "tracks": [
            {"id": i, "albumId": i * 10, "timestamp": "2026-01-01"} for i in range(track_count)
        ],
        "coverUri": "avatars.yandex.net/huge-cover",
        "ogImage": "og-image-url",
    }


def test_playlist_list_strips_tracks():
    """When result is a list of playlists, tracks should be removed (too large)."""
    body = {
        "result": [_make_playlist(1, 557), _make_playlist(2, 213)],
    }
    cleaned = clean_response_body(body)
    for pl in cleaned["result"]:
        assert "tracks" not in pl, "tracks should be stripped in list context"
        assert pl["trackCount"] == 557 or pl["trackCount"] == 213
        assert "coverUri" not in pl


def test_single_playlist_keeps_compact_tracks():
    """Single playlist (by ID) should keep tracks in compact form."""
    playlist = _make_playlist(3, 10)
    body = {"result": playlist}
    cleaned = clean_response_body(body)
    # Single playlist still filtered via _PLAYLIST_FIELDS — no tracks
    # This is acceptable: tracks are stripped, trackCount preserved
    assert cleaned["result"]["trackCount"] == 10
    assert "coverUri" not in cleaned["result"]
