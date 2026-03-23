"""ORM-to-Response converters.

Pure mapping functions — no DB access, no side effects.
Callers fetch data from DB first, then call these to convert.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from app.domain.audio.camelot import key_code_to_camelot
from app.mcp.types import (
    ArtistSummary,
    PlaylistSummary,
    SetSummary,
    TrackDetail,
    TrackSummary,
)

if TYPE_CHECKING:
    from app.core.models.catalog import Artist, Track
    from app.core.models.dj import DjPlaylist
    from app.core.models.features import TrackAudioFeaturesComputed
    from app.core.models.sets import DjSet


def track_to_summary(
    track: Track,
    artists_map: dict[int, list[str]],
    features: TrackAudioFeaturesComputed | None = None,
) -> TrackSummary:
    """Convert Track ORM → TrackSummary (Level 1, ~150 bytes)."""
    artist_str = ", ".join(artists_map.get(track.track_id, [])) or "Unknown"

    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None

    if features is not None:
        bpm = features.bpm
        energy_lufs = features.lufs_i
        with contextlib.suppress(ValueError):
            key = key_code_to_camelot(features.key_code)

    return TrackSummary(
        ref=f"local:{track.track_id}",
        title=track.title,
        artist=artist_str,
        bpm=bpm,
        key=key,
        energy_lufs=energy_lufs,
        duration_ms=track.duration_ms,
    )


def track_to_detail(
    track: Track,
    artists_map: dict[int, list[str]],
    features: TrackAudioFeaturesComputed | None = None,
    genres: list[str] | None = None,
    labels: list[str] | None = None,
    albums: list[str] | None = None,
    platform_ids: dict[str, str] | None = None,
    sections_count: int = 0,
) -> TrackDetail:
    """Convert Track ORM → TrackDetail (Level 2, ~300 bytes)."""
    summary = track_to_summary(track, artists_map, features)

    return TrackDetail(
        **summary.model_dump(),
        has_features=features is not None,
        genres=genres or [],
        labels=labels or [],
        albums=albums or [],
        platform_ids=platform_ids or {},
        sections_count=sections_count,
    )


def playlist_to_summary(
    playlist: DjPlaylist,
    item_count: int = 0,
    analyzed_count: int | None = None,
) -> PlaylistSummary:
    """Convert DjPlaylist ORM → PlaylistSummary."""
    return PlaylistSummary(
        ref=f"local:{playlist.playlist_id}",
        name=playlist.name,
        track_count=item_count,
        analyzed_count=analyzed_count,
    )


def set_to_summary(
    set_: DjSet,
    version_count: int = 0,
    track_count: int = 0,
    avg_score: float | None = None,
) -> SetSummary:
    """Convert DjSet ORM → SetSummary."""
    return SetSummary(
        ref=f"local:{set_.set_id}",
        name=set_.name,
        version_count=version_count,
        track_count=track_count,
        avg_score=avg_score,
    )


def artist_to_summary(
    artist: Artist,
    tracks_in_db: int = 0,
) -> ArtistSummary:
    """Convert Artist ORM → ArtistSummary."""
    return ArtistSummary(
        ref=f"local:{artist.artist_id}",
        name=artist.name,
        tracks_in_db=tracks_in_db,
    )
