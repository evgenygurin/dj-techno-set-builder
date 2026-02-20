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
