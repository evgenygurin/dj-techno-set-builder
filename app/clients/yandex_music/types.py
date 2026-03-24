"""Data types for Yandex Music API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
