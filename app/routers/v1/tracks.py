from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.tracks import TrackCreate, TrackList, TrackRead, TrackUpdate
from app.services.tracks import TrackService

router = APIRouter(prefix="/tracks", tags=["tracks"])


def _service(db: DbSession) -> TrackService:
    from app.services._factories import build_track_service

    return build_track_service(db)


@router.get(
    "",
    response_model=TrackList,
    summary="List tracks",
    description="Retrieve a paginated list of tracks. Supports text search by title.",
    response_description="Paginated list of tracks with total count",
    operation_id="list_tracks",
)
async def list_tracks(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: str | None = Query(
        default=None,
        description="Search tracks by title (case-insensitive)",
    ),
) -> TrackList:
    return await _service(db).list(offset=offset, limit=limit, search=search)


@router.get(
    "/{track_id}",
    response_model=TrackRead,
    summary="Get track",
    description="Retrieve a single track by its unique identifier.",
    response_description="The track details",
    responses=RESPONSES_GET,
    operation_id="get_track",
)
async def get_track(track_id: int, db: DbSession) -> TrackRead:
    return await _service(db).get(track_id)


@router.post(
    "",
    response_model=TrackRead,
    status_code=201,
    summary="Create track",
    description="Create a new track record with title and duration.",
    response_description="The created track",
    responses=RESPONSES_CREATE,
    operation_id="create_track",
)
async def create_track(data: TrackCreate, db: DbSession) -> TrackRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{track_id}",
    response_model=TrackRead,
    summary="Update track",
    description="Partially update an existing track. Only provided fields are modified.",
    response_description="The updated track",
    responses=RESPONSES_UPDATE,
    operation_id="update_track",
)
async def update_track(track_id: int, data: TrackUpdate, db: DbSession) -> TrackRead:
    result = await _service(db).update(track_id, data)
    await db.commit()
    return result


@router.delete(
    "/{track_id}",
    status_code=204,
    summary="Delete track",
    description="Permanently delete a track by ID. Cascades to related resources.",
    responses=RESPONSES_DELETE,
    operation_id="delete_track",
)
async def delete_track(track_id: int, db: DbSession) -> None:
    await _service(db).delete(track_id)
    await db.commit()
