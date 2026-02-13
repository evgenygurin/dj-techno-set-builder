from pydantic import Field

from app.schemas.base import BaseSchema


class AnalysisRequest(BaseSchema):
    audio_path: str
    pipeline_name: str = "essentia-v1"
    pipeline_version: str = "2.1b6"
    full_analysis: bool = False


class AnalysisResponse(BaseSchema):
    track_id: int
    run_id: int
    status: str
    bpm: float | None = None
    key_code: int | None = None
    sections_count: int = 0


class BatchAnalysisRequest(BaseSchema):
    """Batch analyze multiple tracks."""

    track_ids: list[int] = Field(min_length=1, max_length=500)
    audio_dir: str
    full_analysis: bool = False


class BatchAnalysisResponse(BaseSchema):
    """Result of batch analysis."""

    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
