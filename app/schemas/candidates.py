from datetime import datetime

from app.schemas.base import BaseSchema


class CandidateRead(BaseSchema):
    from_track_id: int
    to_track_id: int
    run_id: int
    bpm_distance: float
    key_distance: float
    embedding_similarity: float | None = None
    energy_delta: float | None = None
    is_fully_scored: bool
    created_at: datetime


class CandidateList(BaseSchema):
    items: list[CandidateRead]
    total: int
