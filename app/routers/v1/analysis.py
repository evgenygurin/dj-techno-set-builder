from fastapi import APIRouter

from app.dependencies import DbSession
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.runs import FeatureRunRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis import AnalysisOrchestrator

router = APIRouter(prefix="/tracks", tags=["analysis"])


def _service(db: DbSession) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        track_repo=TrackRepository(db),
        features_repo=AudioFeaturesRepository(db),
        sections_repo=SectionsRepository(db),
        run_repo=FeatureRunRepository(db),
    )


@router.post(
    "/{track_id}/analyze",
    response_model=AnalysisResponse,
    summary="Analyze track audio",
    description=(
        "Extract audio features from a track's audio file. Creates a feature extraction "
        "run, extracts BPM/key/loudness/spectral/energy features, and persists results. "
        "Set full_analysis=true for Phase 2 features (beats, sections)."
    ),
    response_description="Analysis result with run ID and extracted features summary",
    responses=RESPONSES_GET,
    operation_id="analyze_track",
)
async def analyze_track(
    track_id: int,
    data: AnalysisRequest,
    db: DbSession,
) -> AnalysisResponse:
    result = await _service(db).analyze(track_id, data)
    await db.commit()
    return result
