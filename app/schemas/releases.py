from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import BaseSchema

DatePrecision = Literal["year", "month", "day"]


class ReleaseCreate(BaseSchema):
    title: str = Field(min_length=1, max_length=500)
    label_id: int | None = None
    release_date: date | None = None
    release_date_precision: DatePrecision | None = None


class ReleaseUpdate(BaseSchema):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    label_id: int | None = None
    release_date: date | None = None
    release_date_precision: DatePrecision | None = None


class ReleaseRead(BaseSchema):
    release_id: int
    title: str
    label_id: int | None
    release_date: date | None
    release_date_precision: str | None
    created_at: datetime
    updated_at: datetime


class ReleaseList(BaseSchema):
    items: list[ReleaseRead]
    total: int
