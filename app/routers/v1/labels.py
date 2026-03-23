from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.infrastructure.repositories.labels import LabelRepository
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.labels import LabelCreate, LabelList, LabelRead, LabelUpdate
from app.services.labels import LabelService

router = APIRouter(prefix="/labels", tags=["labels"])


def _service(db: DbSession) -> LabelService:
    return LabelService(LabelRepository(db))


@router.get(
    "",
    response_model=LabelList,
    summary="List labels",
    description="Retrieve a paginated list of record labels. Supports text search by name.",
    response_description="Paginated list of labels with total count",
    operation_id="list_labels",
)
async def list_labels(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: str | None = Query(
        default=None, description="Search labels by name (case-insensitive)"
    ),
) -> LabelList:
    return await _service(db).list(offset=offset, limit=limit, search=search)


@router.get(
    "/{label_id}",
    response_model=LabelRead,
    summary="Get label",
    description="Retrieve a single record label by its unique identifier.",
    response_description="The label details",
    responses=RESPONSES_GET,
    operation_id="get_label",
)
async def get_label(label_id: int, db: DbSession) -> LabelRead:
    return await _service(db).get(label_id)


@router.post(
    "",
    response_model=LabelRead,
    status_code=201,
    summary="Create label",
    description="Create a new record label.",
    response_description="The created label",
    responses=RESPONSES_CREATE,
    operation_id="create_label",
)
async def create_label(data: LabelCreate, db: DbSession) -> LabelRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{label_id}",
    response_model=LabelRead,
    summary="Update label",
    description="Partially update an existing record label. Only provided fields are modified.",
    response_description="The updated label",
    responses=RESPONSES_UPDATE,
    operation_id="update_label",
)
async def update_label(label_id: int, data: LabelUpdate, db: DbSession) -> LabelRead:
    result = await _service(db).update(label_id, data)
    await db.commit()
    return result


@router.delete(
    "/{label_id}",
    status_code=204,
    summary="Delete label",
    description="Permanently delete a record label by ID.",
    responses=RESPONSES_DELETE,
    operation_id="delete_label",
)
async def delete_label(label_id: int, db: DbSession) -> None:
    await _service(db).delete(label_id)
    await db.commit()
