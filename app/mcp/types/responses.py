"""Response envelopes for MCP tools.

All tools return responses with: results + stats + pagination.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ActionResponse",
    "EntityDetailResponse",
    "EntityListResponse",
    "FindResult",
    "LibraryStats",
    "MatchStats",
    "PaginationInfo",
    "SearchResponse",
]


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


# --- Phase 2: Response Envelopes for CRUD ---


class EntityListResponse(BaseModel):
    """Standard response for list/search operations."""

    results: list[Any]
    total: int
    library: LibraryStats
    pagination: PaginationInfo


class EntityDetailResponse(BaseModel):
    """Standard response for single-entity operations."""

    result: dict[str, Any]
    library: LibraryStats


class ActionResponse(BaseModel):
    """Standard response for create/update/delete actions."""

    success: bool
    message: str
    result: dict[str, Any] | None = None
    library: LibraryStats
