"""Pydantic DTOs for DJ entities."""

from __future__ import annotations

from pydantic import Field, model_validator

from app.common.dto import BaseDTO
from app.schemas.common import (
    BpmFloat,
    ColorRGB,
    CueKind,
    HotcueIndex,
    NonNegativeInt,
    SourceApp,
    TargetApp,
)


class DjBeatgridDTO(BaseDTO):
    track_id: int
    source_app: SourceApp
    bpm: BpmFloat
    first_downbeat_ms: NonNegativeInt
    grid_offset_ms: int | None = None
    grid_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_variable_tempo: bool = False
    is_canonical: bool = False


class DjBeatgridChangePointDTO(BaseDTO):
    beatgrid_id: int
    position_ms: NonNegativeInt
    bpm: BpmFloat


class DjCuePointDTO(BaseDTO):
    track_id: int
    position_ms: NonNegativeInt
    cue_kind: CueKind
    hotcue_index: HotcueIndex | None = None
    label: str | None = None
    color_rgb: ColorRGB | None = None
    is_quantized: bool | None = None
    source_app: SourceApp | None = None


class DjSavedLoopDTO(BaseDTO):
    track_id: int
    in_ms: NonNegativeInt
    out_ms: NonNegativeInt
    length_ms: NonNegativeInt
    hotcue_index: HotcueIndex | None = None
    label: str | None = None
    is_active_on_load: bool | None = None
    color_rgb: ColorRGB | None = None
    source_app: SourceApp | None = None

    @model_validator(mode="after")
    def validate_loop_bounds(self) -> DjSavedLoopDTO:
        if self.out_ms <= self.in_ms:
            raise ValueError("out_ms must be greater than in_ms")
        if self.length_ms != self.out_ms - self.in_ms:
            raise ValueError("length_ms must equal out_ms - in_ms")
        return self


class DjPlaylistItemDTO(BaseDTO):
    playlist_id: int
    track_id: int
    sort_index: NonNegativeInt


class DjAppExportDTO(BaseDTO):
    target_app: TargetApp
    export_format: str = Field(min_length=1)
    playlist_id: int | None = None
    storage_uri: str | None = None
    file_size: int | None = Field(default=None, gt=0)
