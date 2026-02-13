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
