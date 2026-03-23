from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.core.errors import ValidationError
from app.infrastructure.repositories.audio_features import AudioFeaturesRepository
from app.infrastructure.repositories.candidates import CandidateRepository
from app.infrastructure.repositories.transitions import TransitionRepository
from app.routers.v1._openapi import RESPONSES_DELETE, RESPONSES_GET
from app.schemas.transitions import (
    TransitionComputeRequest,
    TransitionComputeResponse,
    TransitionList,
    TransitionRead,
)
from app.services.transition_persistence import TransitionPersistenceService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.services.transitions import TransitionService

router = APIRouter(prefix="/transitions", tags=["transitions"])


def _service(db: DbSession) -> TransitionService:
    return TransitionService(TransitionRepository(db))


def _scoring_service(db: DbSession) -> TransitionPersistenceService:
    return TransitionPersistenceService(
        AudioFeaturesRepository(db),
        TransitionRepository(db),
        CandidateRepository(db),
    )


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


@router.post(
    "/compute",
    response_model=TransitionComputeResponse,
    summary="Compute transition score",
    description="Score a transition between two tracks using their audio features.",
    response_description="Computed transition score and components",
    operation_id="compute_transition",
)
async def compute_transition(
    data: TransitionComputeRequest, db: DbSession
) -> TransitionComputeResponse:
    svc = _scoring_service(db)
    try:
        result = await svc.score_pair(
            from_track_id=data.from_track_id,
            to_track_id=data.to_track_id,
            run_id=data.run_id,
            groove_sim=data.groove_sim,
            weights=data.weights,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await db.commit()
    return TransitionComputeResponse(
        transition_quality=result.transition_quality,
        bpm_distance=result.bpm_distance,
        key_distance_weighted=result.key_distance_weighted,
        energy_step=result.energy_step,
        low_conflict_score=result.low_conflict_score,
        overlap_score=result.overlap_score,
        groove_similarity=result.groove_similarity,
    )


@router.post(
    "/compute-unified",
    response_model=TransitionComputeResponse,
    summary="Compute transition score (unified path)",
    description=(
        "Score a transition using the unified TransitionScoringService. "
        "This uses the same scoring logic as the GA and MCP paths, "
        "ensuring consistent results across all entry points."
    ),
    response_description="Computed transition score using unified scoring",
    operation_id="compute_transition_unified",
)
async def compute_transition_unified(
    data: TransitionComputeRequest, db: DbSession
) -> TransitionComputeResponse:
    unified_svc = UnifiedTransitionScoringService(db)
    try:
        feat_a, feat_b = await unified_svc._load_pair(
            data.from_track_id,
            data.to_track_id,
        )
        components = await unified_svc.score_components_by_features(feat_a, feat_b)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    bpm_distance = abs(feat_a.bpm - feat_b.bpm)
    energy_step = feat_b.lufs_i - feat_a.lufs_i

    return TransitionComputeResponse(
        transition_quality=components["total"],
        bpm_distance=bpm_distance,
        key_distance_weighted=components["harmonic"],
        energy_step=energy_step,
        low_conflict_score=components["spectral"],
        overlap_score=components["spectral"],
        groove_similarity=components["groove"],
    )
