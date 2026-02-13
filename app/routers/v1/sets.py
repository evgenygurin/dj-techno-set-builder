from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.routers.v1._openapi import (
    RESPONSES_CREATE,
    RESPONSES_DELETE,
    RESPONSES_GET,
    RESPONSES_UPDATE,
)
from app.schemas.set_generation import SetGenerationRequest, SetGenerationResponse
from app.schemas.sets import (
    DjSetCreate,
    DjSetItemCreate,
    DjSetItemList,
    DjSetItemRead,
    DjSetList,
    DjSetRead,
    DjSetUpdate,
    DjSetVersionCreate,
    DjSetVersionList,
    DjSetVersionRead,
)
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService

router = APIRouter(prefix="/sets", tags=["sets"])


def _service(db: DbSession) -> DjSetService:
    return DjSetService(
        DjSetRepository(db),
        DjSetVersionRepository(db),
        DjSetItemRepository(db),
    )


# ─── Set CRUD ────────────────────────────────────────────


@router.get(
    "",
    response_model=DjSetList,
    summary="List DJ sets",
    description="Retrieve a paginated list of DJ sets. Supports text search by name.",
    response_description="Paginated list of DJ sets with total count",
    operation_id="list_sets",
)
async def list_sets(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: str | None = Query(default=None, description="Search sets by name (case-insensitive)"),
) -> DjSetList:
    return await _service(db).list(offset=offset, limit=limit, search=search)


@router.get(
    "/{set_id}",
    response_model=DjSetRead,
    summary="Get DJ set",
    description="Retrieve a single DJ set by its unique identifier.",
    response_description="The DJ set details including target BPM range and energy arc",
    responses=RESPONSES_GET,
    operation_id="get_set",
)
async def get_set(set_id: int, db: DbSession) -> DjSetRead:
    return await _service(db).get(set_id)


@router.post(
    "",
    response_model=DjSetRead,
    status_code=201,
    summary="Create DJ set",
    description=(
        "Create a new DJ set with target parameters (duration, BPM range, energy arc). "
        "Versions and track items are added separately."
    ),
    response_description="The created DJ set",
    responses=RESPONSES_CREATE,
    operation_id="create_set",
)
async def create_set(data: DjSetCreate, db: DbSession) -> DjSetRead:
    result = await _service(db).create(data)
    await db.commit()
    return result


@router.patch(
    "/{set_id}",
    response_model=DjSetRead,
    summary="Update DJ set",
    description="Partially update an existing DJ set. Only provided fields are modified.",
    response_description="The updated DJ set",
    responses=RESPONSES_UPDATE,
    operation_id="update_set",
)
async def update_set(set_id: int, data: DjSetUpdate, db: DbSession) -> DjSetRead:
    result = await _service(db).update(set_id, data)
    await db.commit()
    return result


@router.delete(
    "/{set_id}",
    status_code=204,
    summary="Delete DJ set",
    description="Permanently delete a DJ set and all its versions, items, and feedback.",
    responses=RESPONSES_DELETE,
    operation_id="delete_set",
)
async def delete_set(set_id: int, db: DbSession) -> None:
    await _service(db).delete(set_id)
    await db.commit()


# ─── Generation ─────────────────────────────────────────


def _generation_service(db: DbSession) -> SetGenerationService:
    return SetGenerationService(
        DjSetRepository(db),
        DjSetVersionRepository(db),
        DjSetItemRepository(db),
        AudioFeaturesRepository(db),
    )


@router.post(
    "/{set_id}/generate",
    response_model=SetGenerationResponse,
    status_code=201,
    summary="Generate set tracklist via GA",
    description=(
        "Run a genetic algorithm to find an optimal track ordering for the set. "
        "Creates a new DjSetVersion with the resulting tracklist."
    ),
    response_description="The generated set version with fitness details",
    responses=RESPONSES_CREATE,
    operation_id="generate_set",
)
async def generate_set(
    set_id: int,
    data: SetGenerationRequest,
    db: DbSession,
) -> SetGenerationResponse:
    result = await _generation_service(db).generate(set_id, data)
    await db.commit()
    return result


# ─── Set Versions ────────────────────────────────────────


@router.get(
    "/{set_id}/versions",
    response_model=DjSetVersionList,
    summary="List set versions",
    description="Retrieve all versions of a DJ set. Each version is a snapshot of the tracklist.",
    response_description="Paginated list of set versions with total count",
    responses=RESPONSES_GET,
    operation_id="list_set_versions",
)
async def list_set_versions(
    set_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> DjSetVersionList:
    return await _service(db).list_versions(set_id, offset=offset, limit=limit)


@router.post(
    "/{set_id}/versions",
    response_model=DjSetVersionRead,
    status_code=201,
    summary="Create set version",
    description="Create a new version (snapshot) for a DJ set.",
    response_description="The created set version",
    responses=RESPONSES_CREATE,
    operation_id="create_set_version",
)
async def create_set_version(
    set_id: int, data: DjSetVersionCreate, db: DbSession
) -> DjSetVersionRead:
    result = await _service(db).create_version(set_id, data)
    await db.commit()
    return result


# ─── Set Version Items ───────────────────────────────────


@router.get(
    "/{set_id}/versions/{set_version_id}/items",
    response_model=DjSetItemList,
    summary="List set items",
    description="Retrieve the ordered tracklist for a specific set version.",
    response_description="Paginated list of set items with total count",
    responses=RESPONSES_GET,
    operation_id="list_set_items",
)
async def list_set_items(
    set_id: int,
    set_version_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> DjSetItemList:
    return await _service(db).list_items(set_version_id, offset=offset, limit=limit)


@router.post(
    "/{set_id}/versions/{set_version_id}/items",
    response_model=DjSetItemRead,
    status_code=201,
    summary="Add item to set version",
    description="Add a track to a set version at the specified sort index.",
    response_description="The created set item",
    responses=RESPONSES_CREATE,
    operation_id="add_set_item",
)
async def add_set_item(
    set_id: int,
    set_version_id: int,
    data: DjSetItemCreate,
    db: DbSession,
) -> DjSetItemRead:
    result = await _service(db).add_item(set_version_id, data)
    await db.commit()
    return result
