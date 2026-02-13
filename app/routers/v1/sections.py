from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.sections import SectionList
from app.services.sections import SectionsService

router = APIRouter(prefix="/tracks", tags=["sections"])


def _service(db: DbSession) -> SectionsService:
    return SectionsService(SectionsRepository(db), TrackRepository(db))


@router.get(
    "/{track_id}/sections",
    response_model=SectionList,
    summary="List sections for track",
    description="Retrieve structural sections detected for a track.",
    response_description="Paginated list of sections",
    responses=RESPONSES_GET,
    operation_id="list_track_sections",
)
async def list_track_sections(
    track_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> SectionList:
    return await _service(db).list_for_track(track_id, offset=offset, limit=limit)
