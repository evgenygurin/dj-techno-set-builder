"""Entity summaries and details for MCP responses.

Level 1 (Summary, ~150 bytes) — for lists, search results.
Level 2 (Detail, ~300 bytes) — for single entity views.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "ArtistSummary",
    "PlaylistDetail",
    "PlaylistSummary",
    "SetDetail",
    "SetSummary",
    "TrackDetail",
    "TrackSummary",
]

# --- Entity Summaries (Level 1: ~150 bytes each) ---


class TrackSummary(BaseModel):
    """Minimal track info for lists and search results."""

    ref: str
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
    energy_lufs: float | None = None
    duration_ms: int | None = None
    mood: str | None = None
    match_score: float | None = Field(None, ge=0, le=1)


class PlaylistSummary(BaseModel):
    """Minimal playlist info."""

    ref: str
    name: str
    track_count: int = 0
    analyzed_count: int | None = None
    match_score: float | None = Field(None, ge=0, le=1)


class SetSummary(BaseModel):
    """Minimal set info."""

    ref: str
    name: str
    version_count: int = 0
    track_count: int = 0
    avg_score: float | None = None
    match_score: float | None = Field(None, ge=0, le=1)


class ArtistSummary(BaseModel):
    """Minimal artist info."""

    ref: str
    name: str
    tracks_in_db: int = 0
    match_score: float | None = Field(None, ge=0, le=1)


# --- Entity Details (Level 2: ~300 bytes each) ---


class TrackDetail(TrackSummary):
    """Extended track info — single entity view."""

    has_features: bool = False
    genres: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    albums: list[str] = Field(default_factory=list)
    sections_count: int = 0
    platform_ids: dict[str, str] = Field(default_factory=dict)


class PlaylistDetail(PlaylistSummary):
    """Extended playlist info — single entity view."""

    analyzed_count: int = 0  # type: ignore[assignment]
    bpm_range: tuple[float, float] | None = None
    keys: list[str] = Field(default_factory=list)
    avg_energy: float | None = None
    duration_minutes: float = 0.0


class SetDetail(SetSummary):
    """Extended set info — single entity view."""

    description: str | None = None
    template_name: str | None = None
    target_bpm_min: float | None = None
    target_bpm_max: float | None = None
    latest_version_id: int | None = None
    latest_score: float | None = None
