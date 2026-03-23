from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.infrastructure.repositories.keys import KeyRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.keys import KeyList, KeyRead
from app.services.keys import KeyService

router = APIRouter(prefix="/keys", tags=["keys"])


def _service(db: DbSession) -> KeyService:
    return KeyService(KeyRepository(db))


@router.get(
    "",
    response_model=KeyList,
    summary="List musical keys",
    description=(
        "Retrieve all 24 musical keys (12 pitch classes x 2 modes). "
        "Includes Camelot wheel notation for harmonic mixing."
    ),
    response_description="List of all musical keys with total count",
    operation_id="list_keys",
)
async def list_keys(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> KeyList:
    return await _service(db).list(offset=offset, limit=limit)


@router.get(
    "/{key_code}",
    response_model=KeyRead,
    summary="Get musical key",
    description=(
        "Retrieve a single musical key by its code (0-23). Key code = pitch_class * 2 + mode."
    ),
    response_description="The musical key details with Camelot notation",
    responses=RESPONSES_GET,
    operation_id="get_key",
)
async def get_key(key_code: int, db: DbSession) -> KeyRead:
    return await _service(db).get(key_code)
