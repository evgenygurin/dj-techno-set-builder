from pydantic import Field

from app.schemas.base import BaseSchema


class GenreCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=200)
    parent_genre_id: int | None = None


class GenreUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_genre_id: int | None = None


class GenreRead(BaseSchema):
    genre_id: int
    name: str
    parent_genre_id: int | None


class GenreList(BaseSchema):
    items: list[GenreRead]
    total: int
