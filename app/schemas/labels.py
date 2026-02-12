from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class LabelCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=300)
    name_sort: str | None = Field(default=None, max_length=300)


class LabelUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    name_sort: str | None = None


class LabelRead(BaseSchema):
    label_id: int
    name: str
    name_sort: str | None
    created_at: datetime
    updated_at: datetime


class LabelList(BaseSchema):
    items: list[LabelRead]
    total: int
