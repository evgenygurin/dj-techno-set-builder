from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.tracks import TrackRepository
from app.schemas.tracks import TrackCreate, TrackList, TrackRead, TrackUpdate
from app.services.tracks import TrackService

router = APIRouter(prefix="/tracks", tags=["tracks"])


def _service(db: DbSession) -> TrackService:
    return TrackService(TrackRepository(db))


@router.get("", response_model=TrackList)
async def list_tracks(
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = None,
) -> TrackList:
    return await _service(db).list(offset=offset, limit=limit, search=search)


@router.get("/{track_id}", response_model=TrackRead)
async def get_track(track_id: int, db: DbSession) -> TrackRead:
    return await _service(db).get(track_id)


@router.post("", response_model=TrackRead, status_code=201)
async def create_track(data: TrackCreate, db: DbSession) -> TrackRead:
    svc = _service(db)
    result = await svc.create(data)
    await db.commit()
    return result


@router.patch("/{track_id}", response_model=TrackRead)
async def update_track(track_id: int, data: TrackUpdate, db: DbSession) -> TrackRead:
    svc = _service(db)
    result = await svc.update(track_id, data)
    await db.commit()
    return result


@router.delete("/{track_id}", status_code=204)
async def delete_track(track_id: int, db: DbSession) -> None:
    svc = _service(db)
    await svc.delete(track_id)
    await db.commit()
