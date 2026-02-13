from fastapi import APIRouter

from app.dependencies import DbSession
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.runs import FeatureRunRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    BatchAnalysisRequest,
    BatchAnalysisResponse,
)
from app.services.analysis import AnalysisOrchestrator

router = APIRouter(prefix="/tracks", tags=["analysis"])


def _service(db: DbSession) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        track_repo=TrackRepository(db),
        features_repo=AudioFeaturesRepository(db),
        sections_repo=SectionsRepository(db),
        run_repo=FeatureRunRepository(db),
    )


@router.post(
    "/{track_id}/analyze",
    response_model=AnalysisResponse,
    status_code=201,
    summary="Analyze track audio",
    description=(
        "Extract audio features from a track's audio file. Creates a feature extraction "
        "run, extracts BPM/key/loudness/spectral/energy features, and persists results. "
        "Set full_analysis=true for Phase 2 features (beats, sections)."
    ),
    response_description="Analysis result with run ID and extracted features summary",
    responses=RESPONSES_GET,
    operation_id="analyze_track",
)
async def analyze_track(
    track_id: int,
    data: AnalysisRequest,
    db: DbSession,
) -> AnalysisResponse:
    result = await _service(db).analyze(track_id, data)
    await db.commit()
    return result


@router.post(
    "/batch-analyze",
    response_model=BatchAnalysisResponse,
    summary="Batch analyze tracks",
    description="Analyze multiple tracks sequentially. Skips tracks without audio files.",
    response_description="Summary of batch analysis results",
    operation_id="batch_analyze_tracks",
)
async def batch_analyze(
    data: BatchAnalysisRequest,
    db: DbSession,
) -> BatchAnalysisResponse:
    import logging
    from pathlib import Path

    logger = logging.getLogger(__name__)
    svc = _service(db)
    completed = 0
    failed = 0
    skipped = 0
    errors: list[str] = []

    for tid in data.track_ids:
        # Find audio file: {NNN}_{title}.mp3
        audio_dir = Path(data.audio_dir)
        candidates = list(audio_dir.glob(f"{tid:03d}_*.mp3"))
        if not candidates:
            candidates = list(audio_dir.glob(f"{tid}_*.mp3"))
        if not candidates:
            skipped += 1
            errors.append(f"Track {tid}: no audio file found")
            continue

        req = AnalysisRequest(
            audio_path=str(candidates[0]),
            full_analysis=data.full_analysis,
        )
        try:
            resp = await svc.analyze(tid, req)
            if resp.status != "completed":
                failed += 1
                errors.append(f"Track {tid}: analysis returned status={resp.status}")
                await db.rollback()
                continue
            # Commit per-track so progress is never lost
            await db.commit()
            completed += 1
        except Exception as e:
            failed += 1
            errors.append(f"Track {tid}: {e}")
            logger.warning("Batch analysis failed for track %d: %s", tid, e)
            await db.rollback()

    return BatchAnalysisResponse(
        total=len(data.track_ids),
        completed=completed,
        failed=failed,
        skipped=skipped,
        errors=errors,
    )
