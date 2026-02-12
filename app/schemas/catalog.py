"""Pydantic DTOs for core catalog entities."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.common.dto import BaseDTO
from app.schemas.common import PositiveInt


class TrackDTO(BaseDTO):
    title: str = Field(min_length=1)
    title_sort: str | None = None
    duration_ms: PositiveInt
    status: Literal[0, 1] = 0


class TrackArtistDTO(BaseDTO):
    track_id: int
    artist_id: int
    role: Literal[0, 1, 2]


class ReleaseDTO(BaseDTO):
    title: str = Field(min_length=1)
    label_id: int | None = None
    release_date: date | None = None
    release_date_precision: Literal["year", "month", "day"] | None = None
