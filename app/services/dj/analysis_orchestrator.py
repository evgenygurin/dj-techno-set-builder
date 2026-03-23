from app.core.errors import NotFoundError
from app.infrastructure.repositories.audio.features import AudioFeaturesRepository
from app.infrastructure.repositories.audio.runs import FeatureRunRepository
from app.infrastructure.repositories.audio.sections import SectionsRepository
from app.infrastructure.repositories.catalog.tracks import TrackRepository
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.audio.analysis import TrackAnalysisService
from app.services.base import BaseService


class AnalysisOrchestrator(BaseService):
    """Orchestrates the full analysis workflow: create run -> extract -> persist."""

    def __init__(
        self,
        track_repo: TrackRepository,
        features_repo: AudioFeaturesRepository,
        sections_repo: SectionsRepository,
        run_repo: FeatureRunRepository,
    ) -> None:
        super().__init__()
        self.track_repo = track_repo
        self.run_repo = run_repo
        self.analysis_svc = TrackAnalysisService(track_repo, features_repo, sections_repo)

    async def analyze(self, track_id: int, request: AnalysisRequest) -> AnalysisResponse:
        # Validate track exists
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)

        # Create a run
        run = await self.run_repo.create(
            pipeline_name=request.pipeline_name,
            pipeline_version=request.pipeline_version,
            parameters={"full_analysis": request.full_analysis},
            code_ref=f"{request.pipeline_name}@{request.pipeline_version}",
            status="running",
        )

        try:
            if request.full_analysis:
                features = await self.analysis_svc.analyze_track_full(
                    track_id,
                    request.audio_path,
                    run.run_id,
                )
            else:
                features = await self.analysis_svc.analyze_track(
                    track_id,
                    request.audio_path,
                    run.run_id,
                )
            await self.run_repo.mark_completed(run.run_id)

            return AnalysisResponse(
                track_id=track_id,
                run_id=run.run_id,
                status="completed",
                bpm=features.bpm.bpm,
                key_code=features.key.key_code,
            )
        except Exception:  # broad: audio pipeline can raise many error types
            self.logger.exception("Analysis failed for track %d", track_id)
            await self.run_repo.mark_failed(run.run_id)
            return AnalysisResponse(
                track_id=track_id,
                run_id=run.run_id,
                status="failed",
            )
