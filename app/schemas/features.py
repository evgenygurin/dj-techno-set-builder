"""Pydantic DTOs for DSP/ML features and transitions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.common.dto import BaseDTO
from app.schemas.common import (
    BpmFloat,
    KeyCode,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    UnitFloat,
)


class AudioAssetDTO(BaseDTO):
    track_id: int
    asset_type: Literal[0, 1, 2, 3, 4, 5]
    storage_uri: str = Field(min_length=1)
    format: str = Field(min_length=1)
    sample_rate: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    duration_ms: PositiveInt | None = None
    file_size: int | None = Field(default=None, gt=0)
    source_run_id: int | None = None


class FeatureExtractionRunDTO(BaseDTO):
    pipeline_name: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    parameters: Any | None = None
    code_ref: str | None = None
    status: Literal["running", "completed", "failed"] = "running"


class TransitionRunDTO(BaseDTO):
    pipeline_name: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    weights: Any | None = None
    constraints: Any | None = None
    status: Literal["running", "completed", "failed"] = "running"


class KeyDTO(BaseDTO):
    key_code: KeyCode
    pitch_class: int = Field(ge=0, le=11)
    mode: Literal[0, 1]
    name: str = Field(min_length=1)
    camelot: str | None = None

    @model_validator(mode="after")
    def validate_key_mapping(self) -> KeyDTO:
        if self.key_code != self.pitch_class * 2 + self.mode:
            raise ValueError("key_code must equal pitch_class * 2 + mode")
        return self


class TrackAudioFeatureComputedDTO(BaseDTO):
    track_id: int
    run_id: int
    bpm: BpmFloat
    tempo_confidence: UnitFloat
    bpm_stability: UnitFloat
    key_code: KeyCode
    key_confidence: UnitFloat
    transition_quality: UnitFloat | None = None
    computed_from_asset_type: Literal[0, 1, 2, 3, 4, 5] | None = None


class TrackSectionDTO(BaseDTO):
    track_id: int
    run_id: int
    range_ms: Any
    section_type: int = Field(ge=0, le=11)
    section_duration_ms: PositiveInt


class TransitionCandidateDTO(BaseDTO):
    from_track_id: int
    to_track_id: int
    run_id: int
    bpm_distance: NonNegativeFloat
    key_distance: NonNegativeFloat
    embedding_similarity: float | None = None
    energy_delta: float | None = None
    is_fully_scored: bool = False

    @model_validator(mode="after")
    def validate_direction(self) -> TransitionCandidateDTO:
        if self.from_track_id == self.to_track_id:
            raise ValueError("from_track_id and to_track_id must be different")
        return self


class TransitionDTO(BaseDTO):
    run_id: int
    from_track_id: int
    to_track_id: int
    from_section_id: int | None = None
    to_section_id: int | None = None
    overlap_ms: NonNegativeInt
    bpm_distance: NonNegativeFloat
    energy_step: float
    transition_quality: UnitFloat

    @model_validator(mode="after")
    def validate_direction(self) -> TransitionDTO:
        if self.from_track_id == self.to_track_id:
            raise ValueError("from_track_id and to_track_id must be different")
        return self
