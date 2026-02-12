from datetime import datetime

from app.schemas.base import BaseSchema


class TransitionRead(BaseSchema):
    transition_id: int
    run_id: int
    from_track_id: int
    to_track_id: int
    from_section_id: int | None
    to_section_id: int | None
    overlap_ms: int
    bpm_distance: float
    energy_step: float
    centroid_gap_hz: float | None
    low_conflict_score: float | None
    overlap_score: float | None
    groove_similarity: float | None
    key_distance_weighted: float | None
    transition_quality: float
    computed_at: datetime


class TransitionList(BaseSchema):
    items: list[TransitionRead]
    total: int
