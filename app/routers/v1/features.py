from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.features import AudioFeaturesList, AudioFeaturesRead
from app.services.features import AudioFeaturesService

router = APIRouter(prefix="/tracks", tags=["features"])


def _service(db: DbSession) -> AudioFeaturesService:
    return AudioFeaturesService(AudioFeaturesRepository(db), TrackRepository(db))


@router.get(
    "/{track_id}/features",
    response_model=AudioFeaturesList,
    summary="List audio features for track",
    description="Retrieve all computed audio features for a track across all runs.",
    response_description="Paginated list of audio features",
    responses=RESPONSES_GET,
    operation_id="list_track_features",
)
async def list_track_features(
    track_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> AudioFeaturesList:
    return await _service(db).list_for_track(track_id, offset=offset, limit=limit)


@router.get(
    "/{track_id}/features/latest",
    response_model=AudioFeaturesRead,
    summary="Get latest audio features for track",
    description="Retrieve the most recent audio features computed for a track.",
    response_description="The latest audio features",
    responses=RESPONSES_GET,
    operation_id="get_track_features_latest",
)
async def get_track_features_latest(track_id: int, db: DbSession) -> AudioFeaturesRead:
    return await _service(db).get_latest(track_id)
