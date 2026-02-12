from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.genres import GenreRepository
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.genres import GenreCreate, GenreList, GenreRead, GenreUpdate
from app.services.genres import GenreService

router = APIRouter(prefix="/genres", tags=["genres"])


def _service(db: DbSession) -> GenreService:
    return GenreService(GenreRepository(db))


@router.get(
    "",
    response_model=GenreList,
    summary="List genres",
    description=(
        "Retrieve a paginated list of genres. "
        "Genres support a parent hierarchy via `parent_genre_id`."
    ),
    response_description="Paginated list of genres with total count",
    operation_id="list_genres",
)
async def list_genres(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> GenreList:
    return await _service(db).list(offset=offset, limit=limit)


@router.get(
    "/{genre_id}",
    response_model=GenreRead,
    summary="Get genre",
    description="Retrieve a single genre by its unique identifier.",
    response_description="The genre details",
    responses=RESPONSES_GET,
    operation_id="get_genre",
)
async def get_genre(genre_id: int, db: DbSession) -> GenreRead:
    return await _service(db).get(genre_id)


@router.post(
    "",
    response_model=GenreRead,
    status_code=201,
    summary="Create genre",
    description="Create a new genre. Optionally set `parent_genre_id` for hierarchy.",
    response_description="The created genre",
    responses=RESPONSES_CREATE,
    operation_id="create_genre",
)
async def create_genre(data: GenreCreate, db: DbSession) -> GenreRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{genre_id}",
    response_model=GenreRead,
    summary="Update genre",
    description="Partially update an existing genre. Only provided fields are modified.",
    response_description="The updated genre",
    responses=RESPONSES_UPDATE,
    operation_id="update_genre",
)
async def update_genre(genre_id: int, data: GenreUpdate, db: DbSession) -> GenreRead:
    result = await _service(db).update(genre_id, data)
    await db.commit()
    return result


@router.delete(
    "/{genre_id}",
    status_code=204,
    summary="Delete genre",
    description="Permanently delete a genre by ID.",
    responses=RESPONSES_DELETE,
    operation_id="delete_genre",
)
async def delete_genre(genre_id: int, db: DbSession) -> None:
    await _service(db).delete(genre_id)
    await db.commit()
