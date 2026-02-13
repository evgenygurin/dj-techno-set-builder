from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.runs import FeatureRunRepository, TransitionRunRepository
from app.routers.v1._openapi import RESPONSES_CREATE, RESPONSES_GET
from app.schemas.runs import (
    FeatureRunCreate,
    FeatureRunList,
    FeatureRunRead,
    TransitionRunCreate,
    TransitionRunList,
    TransitionRunRead,
)
from app.services.runs import FeatureRunService, TransitionRunService

router = APIRouter(prefix="/runs", tags=["runs"])


def _feature_svc(db: DbSession) -> FeatureRunService:
    return FeatureRunService(FeatureRunRepository(db))


def _transition_svc(db: DbSession) -> TransitionRunService:
    return TransitionRunService(TransitionRunRepository(db))


# -- Feature extraction runs --


@router.post(
    "/features",
    response_model=FeatureRunRead,
    status_code=201,
    summary="Create feature extraction run",
    description="Start a new feature extraction run to group analysis results.",
    response_description="The created run",
    responses=RESPONSES_CREATE,
    operation_id="create_feature_run",
)
async def create_feature_run(data: FeatureRunCreate, db: DbSession) -> FeatureRunRead:
    result = await _feature_svc(db).create(data)
    await db.commit()
    return result


@router.get(
    "/features",
    response_model=FeatureRunList,
    summary="List feature extraction runs",
    description="Retrieve a paginated list of feature extraction runs.",
    response_description="Paginated list of runs",
    operation_id="list_feature_runs",
)
async def list_feature_runs(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> FeatureRunList:
    return await _feature_svc(db).list(offset=offset, limit=limit)


@router.get(
    "/features/{run_id}",
    response_model=FeatureRunRead,
    summary="Get feature extraction run",
    description="Retrieve a single feature extraction run by ID.",
    response_description="The run details",
    responses=RESPONSES_GET,
    operation_id="get_feature_run",
)
async def get_feature_run(run_id: int, db: DbSession) -> FeatureRunRead:
    return await _feature_svc(db).get(run_id)


# -- Transition runs --


@router.post(
    "/transitions",
    response_model=TransitionRunRead,
    status_code=201,
    summary="Create transition run",
    description="Start a new transition scoring run with given weights and constraints.",
    response_description="The created run",
    responses=RESPONSES_CREATE,
    operation_id="create_transition_run",
)
async def create_transition_run(data: TransitionRunCreate, db: DbSession) -> TransitionRunRead:
    result = await _transition_svc(db).create(data)
    await db.commit()
    return result


@router.get(
    "/transitions",
    response_model=TransitionRunList,
    summary="List transition runs",
    description="Retrieve a paginated list of transition scoring runs.",
    response_description="Paginated list of runs",
    operation_id="list_transition_runs",
)
async def list_transition_runs(
    db: DbSession,
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> TransitionRunList:
    return await _transition_svc(db).list(offset=offset, limit=limit)


@router.get(
    "/transitions/{run_id}",
    response_model=TransitionRunRead,
    summary="Get transition run",
    description="Retrieve a single transition scoring run by ID.",
    response_description="The run details",
    responses=RESPONSES_GET,
    operation_id="get_transition_run",
)
async def get_transition_run(run_id: int, db: DbSession) -> TransitionRunRead:
    return await _transition_svc(db).get(run_id)
