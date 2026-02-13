"""Yandex Music search & enrichment request/response schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


class YmSearchRequest(BaseSchema):
    """Search Yandex Music for a track."""

    query: str = Field(min_length=1, max_length=400)
    page: int = Field(default=0, ge=0)


class YmSearchResult(BaseSchema):
    """A single search result from Yandex Music."""

    yandex_track_id: str
    title: str
    artists: list[str]
    album_title: str | None = None
    genre: str | None = None
    label: str | None = None
    duration_ms: int | None = None
    year: int | None = None
    release_date: str | None = None
    cover_uri: str | None = None


class YmSearchResponse(BaseSchema):
    """Search results from Yandex Music."""

    results: list[YmSearchResult]
    total: int = 0
    page: int = 0


class YmEnrichRequest(BaseSchema):
    """Link and enrich a track from Yandex Music data."""

    yandex_track_id: str


class YmEnrichResponse(BaseSchema):
    """Result of enriching a single track."""

    track_id: int
    yandex_track_id: str
    genre: str | None = None
    artists: list[str] = Field(default_factory=list)
    label: str | None = None
    release_title: str | None = None
    already_linked: bool = False


class YmBatchEnrichRequest(BaseSchema):
    """Batch enrich tracks by auto-searching Yandex Music."""

    track_ids: list[int] = Field(min_length=1, max_length=500)


class YmBatchEnrichResponse(BaseSchema):
    """Result of batch enrichment."""

    total: int
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
