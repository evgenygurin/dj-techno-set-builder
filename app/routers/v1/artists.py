from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.artists import ArtistRepository
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.artists import ArtistCreate, ArtistList, ArtistRead, ArtistUpdate
from app.services.artists import ArtistService

router = APIRouter(prefix="/artists", tags=["artists"])


def _service(db: DbSession) -> ArtistService:
    return ArtistService(ArtistRepository(db))


@router.get(
    "",
    response_model=ArtistList,
    summary="List artists",
    description="Retrieve a paginated list of artists. Supports text search by name.",
    response_description="Paginated list of artists with total count",
    operation_id="list_artists",
)
async def list_artists(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: str | None = Query(
        default=None, description="Search artists by name (case-insensitive)"
    ),
) -> ArtistList:
    return await _service(db).list(offset=offset, limit=limit, search=search)


@router.get(
    "/{artist_id}",
    response_model=ArtistRead,
    summary="Get artist",
    description="Retrieve a single artist by their unique identifier.",
    response_description="The artist details",
    responses=RESPONSES_GET,
    operation_id="get_artist",
)
async def get_artist(artist_id: int, db: DbSession) -> ArtistRead:
    return await _service(db).get(artist_id)


@router.post(
    "",
    response_model=ArtistRead,
    status_code=201,
    summary="Create artist",
    description="Create a new artist record.",
    response_description="The created artist",
    responses=RESPONSES_CREATE,
    operation_id="create_artist",
)
async def create_artist(data: ArtistCreate, db: DbSession) -> ArtistRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{artist_id}",
    response_model=ArtistRead,
    summary="Update artist",
    description="Partially update an existing artist. Only provided fields are modified.",
    response_description="The updated artist",
    responses=RESPONSES_UPDATE,
    operation_id="update_artist",
)
async def update_artist(artist_id: int, data: ArtistUpdate, db: DbSession) -> ArtistRead:
    result = await _service(db).update(artist_id, data)
    await db.commit()
    return result


@router.delete(
    "/{artist_id}",
    status_code=204,
    summary="Delete artist",
    description="Permanently delete an artist by ID.",
    responses=RESPONSES_DELETE,
    operation_id="delete_artist",
)
async def delete_artist(artist_id: int, db: DbSession) -> None:
    await _service(db).delete(artist_id)
    await db.commit()
