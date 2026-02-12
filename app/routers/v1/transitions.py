from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.transitions import TransitionRepository
from app.routers.v1._openapi import RESPONSES_DELETE, RESPONSES_GET
from app.schemas.transitions import TransitionList, TransitionRead
from app.services.transitions import TransitionService

router = APIRouter(prefix="/transitions", tags=["transitions"])


def _service(db: DbSession) -> TransitionService:
    return TransitionService(TransitionRepository(db))


@router.get(
    "",
    response_model=TransitionList,
    summary="List transitions",
    description=(
        "Retrieve computed transitions between tracks. "
        "Filter by a specific track or minimum quality score."
    ),
    response_description="Paginated list of transitions with total count",
    operation_id="list_transitions",
)
async def list_transitions(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    track_id: int | None = Query(
        default=None, description="Filter transitions involving this track (from or to)"
    ),
    min_quality: float | None = Query(
        default=None, ge=0, le=1, description="Minimum transition quality score (0-1)"
    ),
) -> TransitionList:
    return await _service(db).list(
        offset=offset, limit=limit, track_id=track_id, min_quality=min_quality
    )


@router.get(
    "/{transition_id}",
    response_model=TransitionRead,
    summary="Get transition",
    description=(
        "Retrieve a single computed transition by ID. "
        "Includes scoring components: BPM distance, energy step, groove similarity, etc."
    ),
    response_description="The transition details with all scoring components",
    responses=RESPONSES_GET,
    operation_id="get_transition",
)
async def get_transition(transition_id: int, db: DbSession) -> TransitionRead:
    return await _service(db).get(transition_id)


@router.delete(
    "/{transition_id}",
    status_code=204,
    summary="Delete transition",
    description="Permanently delete a computed transition by ID.",
    responses=RESPONSES_DELETE,
    operation_id="delete_transition",
)
async def delete_transition(transition_id: int, db: DbSession) -> None:
    await _service(db).delete(transition_id)
    await db.commit()
