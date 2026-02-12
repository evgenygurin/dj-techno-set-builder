from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class ArtistCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=300)
    name_sort: str | None = Field(default=None, max_length=300)


class ArtistUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    name_sort: str | None = None


class ArtistRead(BaseSchema):
    artist_id: int
    name: str
    name_sort: str | None
    created_at: datetime
    updated_at: datetime


class ArtistList(BaseSchema):
    items: list[ArtistRead]
    total: int
