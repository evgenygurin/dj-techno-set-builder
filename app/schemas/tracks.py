from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class TrackCreate(BaseSchema):
    title: str = Field(min_length=1, max_length=500)
    title_sort: str | None = None
    duration_ms: int = Field(gt=0)


class TrackUpdate(BaseSchema):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    title_sort: str | None = None
    duration_ms: int | None = Field(default=None, gt=0)


class TrackRead(BaseSchema):
    track_id: int
    title: str
    title_sort: str | None
    duration_ms: int
    status: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TrackList(BaseSchema):
    items: list[TrackRead]
    total: int
