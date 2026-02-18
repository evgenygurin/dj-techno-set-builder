"""Schemas for set curation."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


class CurateRequest(BaseSchema):
    playlist_id: int
    template: str = Field(default="classic_60", description="Template name")
    target_count: int | None = Field(default=None, description="Override track count")
    exclude_track_ids: list[int] = Field(default_factory=list)


class CurateCandidate(BaseSchema):
    track_id: int
    title: str
    artist: str
    mood: str
    slot_score: float
    bpm: float
    lufs_i: float
    key: str | None = None


class CurateResult(BaseSchema):
    template: str
    target_count: int
    candidates: list[CurateCandidate]
    mood_distribution: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
