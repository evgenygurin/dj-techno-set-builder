from datetime import datetime

from app.schemas.base import BaseSchema


class SectionRead(BaseSchema):
    section_id: int
    track_id: int
    run_id: int
    start_ms: int
    end_ms: int
    section_type: int
    section_duration_ms: int
    section_energy_mean: float | None = None
    section_energy_max: float | None = None
    section_energy_slope: float | None = None
    section_centroid_hz: float | None = None
    section_flux: float | None = None
    section_onset_rate: float | None = None
    section_pulse_clarity: float | None = None
    boundary_confidence: float | None = None
    created_at: datetime


class SectionList(BaseSchema):
    items: list[SectionRead]
    total: int
