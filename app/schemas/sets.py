"""Pydantic DTOs for generated DJ sets."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.common.dto import BaseDTO
from app.schemas.common import NonNegativeInt, PositiveInt, UnitFloat


class DjSetDTO(BaseDTO):
    name: str = Field(min_length=1)
    description: str | None = None
    target_duration_ms: PositiveInt | None = None
    target_bpm_min: float | None = None
    target_bpm_max: float | None = None
    target_energy_arc: Any | None = None


class DjSetVersionDTO(BaseDTO):
    set_id: int
    version_label: str | None = None
    generator_run: Any | None = None
    score: UnitFloat | None = None


class DjSetItemDTO(BaseDTO):
    set_version_id: int
    sort_index: NonNegativeInt
    track_id: int
    transition_id: int | None = None
    in_section_id: int | None = None
    out_section_id: int | None = None
    mix_in_ms: NonNegativeInt | None = None
    mix_out_ms: NonNegativeInt | None = None
    planned_eq: Any | None = None
    notes: str | None = None


class DjSetFeedbackDTO(BaseDTO):
    set_version_id: int
    set_item_id: int | None = None
    rating: int = Field(ge=-1, le=5)
    feedback_type: Literal["manual", "live_crowd", "a_b_test"] = "manual"
    tags: list[str] | None = None
    notes: str | None = None
