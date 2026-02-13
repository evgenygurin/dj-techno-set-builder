from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class FeatureRunCreate(BaseSchema):
    pipeline_name: str = Field(min_length=1, max_length=200)
    pipeline_version: str = Field(min_length=1, max_length=50)
    parameters: dict[str, Any] | None = None
    code_ref: str | None = Field(default=None, max_length=200)


class FeatureRunRead(BaseSchema):
    run_id: int
    pipeline_name: str
    pipeline_version: str
    parameters: dict[str, Any] | None
    code_ref: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class FeatureRunList(BaseSchema):
    items: list[FeatureRunRead]
    total: int


class TransitionRunCreate(BaseSchema):
    pipeline_name: str = Field(min_length=1, max_length=200)
    pipeline_version: str = Field(min_length=1, max_length=50)
    weights: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None


class TransitionRunRead(BaseSchema):
    run_id: int
    pipeline_name: str
    pipeline_version: str
    weights: dict[str, Any] | None
    constraints: dict[str, Any] | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class TransitionRunList(BaseSchema):
    items: list[TransitionRunRead]
    total: int
