from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.infrastructure.repositories.releases import ReleaseRepository
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.releases import ReleaseCreate, ReleaseList, ReleaseRead, ReleaseUpdate
from app.services.releases import ReleaseService

router = APIRouter(prefix="/releases", tags=["releases"])


def _service(db: DbSession) -> ReleaseService:
    return ReleaseService(ReleaseRepository(db))


@router.get(
    "",
    response_model=ReleaseList,
    summary="List releases",
    description=(
        "Retrieve a paginated list of releases. "
        "Supports text search by title and filtering by label."
    ),
    response_description="Paginated list of releases with total count",
    operation_id="list_releases",
)
async def list_releases(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: str | None = Query(
        default=None,
        description="Search releases by title (case-insensitive)",
    ),
    label_id: int | None = Query(default=None, description="Filter by label ID"),
) -> ReleaseList:
    return await _service(db).list(offset=offset, limit=limit, search=search, label_id=label_id)


@router.get(
    "/{release_id}",
    response_model=ReleaseRead,
    summary="Get release",
    description="Retrieve a single release by its unique identifier.",
    response_description="The release details",
    responses=RESPONSES_GET,
    operation_id="get_release",
)
async def get_release(release_id: int, db: DbSession) -> ReleaseRead:
    return await _service(db).get(release_id)


@router.post(
    "",
    response_model=ReleaseRead,
    status_code=201,
    summary="Create release",
    description="Create a new release. Optionally link it to a label.",
    response_description="The created release",
    responses=RESPONSES_CREATE,
    operation_id="create_release",
)
async def create_release(data: ReleaseCreate, db: DbSession) -> ReleaseRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{release_id}",
    response_model=ReleaseRead,
    summary="Update release",
    description="Partially update an existing release. Only provided fields are modified.",
    response_description="The updated release",
    responses=RESPONSES_UPDATE,
    operation_id="update_release",
)
async def update_release(release_id: int, data: ReleaseUpdate, db: DbSession) -> ReleaseRead:
    result = await _service(db).update(release_id, data)
    await db.commit()
    return result


@router.delete(
    "/{release_id}",
    status_code=204,
    summary="Delete release",
    description="Permanently delete a release by ID.",
    responses=RESPONSES_DELETE,
    operation_id="delete_release",
)
async def delete_release(release_id: int, db: DbSession) -> None:
    await _service(db).delete(release_id)
    await db.commit()
