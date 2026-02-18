from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class DjSetCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    target_duration_ms: int | None = Field(default=None, gt=0)
    target_bpm_min: float | None = Field(default=None, ge=20, le=300)
    target_bpm_max: float | None = Field(default=None, ge=20, le=300)
    target_energy_arc: dict[str, Any] | None = Field(
        default=None, examples=[{"intro": 0.3, "build": 0.6, "peak": 1.0, "outro": 0.4}]
    )
    # Unified set builder fields
    ym_playlist_id: int | None = None
    template_name: str | None = Field(default=None, max_length=50)
    source_playlist_id: int | None = None


class DjSetUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    target_duration_ms: int | None = Field(default=None, gt=0)
    target_bpm_min: float | None = Field(default=None, ge=20, le=300)
    target_bpm_max: float | None = Field(default=None, ge=20, le=300)
    target_energy_arc: dict[str, Any] | None = Field(
        default=None, examples=[{"intro": 0.3, "build": 0.6, "peak": 1.0, "outro": 0.4}]
    )


class DjSetRead(BaseSchema):
    set_id: int
    name: str
    description: str | None
    target_duration_ms: int | None
    target_bpm_min: float | None
    target_bpm_max: float | None
    target_energy_arc: dict[str, Any] | None = Field(
        default=None, examples=[{"intro": 0.3, "build": 0.6, "peak": 1.0, "outro": 0.4}]
    )
    ym_playlist_id: int | None = None
    template_name: str | None = None
    source_playlist_id: int | None = None
    created_at: datetime
    updated_at: datetime


class DjSetList(BaseSchema):
    items: list[DjSetRead]
    total: int


# --- Set Version schemas ---


class DjSetVersionCreate(BaseSchema):
    version_label: str | None = Field(default=None, max_length=100)
    generator_run: dict[str, Any] | None = Field(
        default=None, examples=[{"algorithm": "greedy", "seed": 42, "iterations": 1000}]
    )
    score: float | None = None


class DjSetVersionRead(BaseSchema):
    set_version_id: int
    set_id: int
    version_label: str | None
    generator_run: dict[str, Any] | None = Field(
        default=None, examples=[{"algorithm": "greedy", "seed": 42, "iterations": 1000}]
    )
    score: float | None
    created_at: datetime


class DjSetVersionList(BaseSchema):
    items: list[DjSetVersionRead]
    total: int


# --- Set Item schemas ---


class DjSetItemCreate(BaseSchema):
    sort_index: int = Field(ge=0)
    track_id: int
    transition_id: int | None = None
    mix_in_ms: int | None = Field(default=None, ge=0)
    mix_out_ms: int | None = Field(default=None, ge=0)
    pinned: bool = False
    planned_eq: dict[str, Any] | None = Field(
        default=None, examples=[{"low": -3.0, "mid": 0.0, "high": 1.5}]
    )
    notes: str | None = None


class DjSetItemRead(BaseSchema):
    set_item_id: int
    set_version_id: int
    sort_index: int
    track_id: int
    transition_id: int | None
    in_section_id: int | None
    out_section_id: int | None
    mix_in_ms: int | None
    mix_out_ms: int | None
    planned_eq: dict[str, Any] | None = Field(
        default=None, examples=[{"low": -3.0, "mid": 0.0, "high": 1.5}]
    )
    notes: str | None
    pinned: bool = False
    created_at: datetime


class DjSetItemList(BaseSchema):
    items: list[DjSetItemRead]
    total: int
