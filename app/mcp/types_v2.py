"""Response models for MCP tools redesign (Phase 1).

Three response levels:
- Summary (~150 bytes/entity) — for lists, search results
- Detail (~300 bytes/entity) — for single entity views
- Full (~2 KB/entity) — for audio namespace, explicit requests

All tools return responses with: results + stats + pagination.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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


# --- Response Envelope ---


class PaginationInfo(BaseModel):
    """Cursor-based pagination metadata."""

    limit: int
    has_more: bool
    cursor: str | None = None


class MatchStats(BaseModel):
    """Background statistics — total counts, not data."""

    total_matches: dict[str, int] = Field(default_factory=dict)
    match_profile: dict[str, Any] = Field(default_factory=dict)


class LibraryStats(BaseModel):
    """Library-wide context."""

    total_tracks: int
    analyzed_tracks: int
    total_playlists: int
    total_sets: int


class SearchResponse(BaseModel):
    """Universal search response with categorized results + stats."""

    results: dict[str, list[Any]]
    stats: MatchStats
    library: LibraryStats
    pagination: PaginationInfo


class FindResult(BaseModel):
    """Entity resolution result."""

    exact: bool
    entities: list[Any]
    source: str
