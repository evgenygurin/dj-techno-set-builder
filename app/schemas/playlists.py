from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class DjPlaylistCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=500)
    parent_playlist_id: int | None = None
    source_app: int | None = Field(default=None, ge=1, le=5)
    source_of_truth: str = Field(
        default="local",
        pattern=r"^(local|ym|spotify|beatport|soundcloud)$",
    )
    platform_ids: dict[str, str] | None = None


class DjPlaylistUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    parent_playlist_id: int | None = None
    source_app: int | None = Field(default=None, ge=1, le=5)
    source_of_truth: str | None = Field(
        default=None,
        pattern=r"^(local|ym|spotify|beatport|soundcloud)$",
    )
    platform_ids: dict[str, str] | None = None


class DjPlaylistRead(BaseSchema):
    playlist_id: int
    name: str
    parent_playlist_id: int | None
    source_app: int | None
    source_of_truth: str
    platform_ids: dict[str, str] | None
    created_at: datetime


class DjPlaylistList(BaseSchema):
    items: list[DjPlaylistRead]
    total: int


# --- Playlist Item schemas ---


class DjPlaylistItemCreate(BaseSchema):
    track_id: int
    sort_index: int = Field(ge=0)


class DjPlaylistItemRead(BaseSchema):
    playlist_item_id: int
    playlist_id: int
    track_id: int
    sort_index: int
    added_at: datetime | None


class DjPlaylistItemList(BaseSchema):
    items: list[DjPlaylistItemRead]
    total: int
