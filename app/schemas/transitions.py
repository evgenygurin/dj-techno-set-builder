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


class TransitionComputeRequest(BaseSchema):
    from_track_id: int
    to_track_id: int
    run_id: int
    groove_sim: float = 0.5
    weights: dict[str, float] | None = None


class TransitionComputeResponse(BaseSchema):
    transition_quality: float
    bpm_distance: float
    key_distance_weighted: float
    energy_step: float
    low_conflict_score: float
    overlap_score: float
    groove_similarity: float
