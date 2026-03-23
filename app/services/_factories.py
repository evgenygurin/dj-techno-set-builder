"""Unified service construction factories.

Single source of truth for building services from a DB session.
Called by both FastAPI DI (app/routers/) and FastMCP DI (app/mcp/dependencies.py).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.repositories.runs import FeatureRunRepository
from app.repositories.sections import SectionsRepository
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.repositories.tracks import TrackRepository
from app.repositories.transitions import TransitionRepository

# Imported here to avoid circular imports from analysis module
from app.services.analysis import AnalysisOrchestrator
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService
from app.services.track_analysis import TrackAnalysisService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.services.transitions import TransitionService


def build_track_service(session: AsyncSession) -> TrackService:
    return TrackService(TrackRepository(session))


def build_playlist_service(session: AsyncSession) -> DjPlaylistService:
    return DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )


def build_features_service(session: AsyncSession) -> AudioFeaturesService:
    return AudioFeaturesService(
        AudioFeaturesRepository(session),
        TrackRepository(session),
    )


def build_analysis_service(session: AsyncSession) -> TrackAnalysisService:
    return TrackAnalysisService(
        TrackRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
    )


def build_set_service(session: AsyncSession) -> DjSetService:
    return DjSetService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
    )


def build_generation_service(session: AsyncSession) -> SetGenerationService:
    return SetGenerationService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
        DjPlaylistItemRepository(session),
    )


def build_transition_service(session: AsyncSession) -> TransitionService:
    return TransitionService(TransitionRepository(session))


def build_unified_scoring(session: AsyncSession) -> UnifiedTransitionScoringService:
    return UnifiedTransitionScoringService(session)


def build_analysis_orchestrator(session: AsyncSession) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        track_repo=TrackRepository(session),
        features_repo=AudioFeaturesRepository(session),
        sections_repo=SectionsRepository(session),
        run_repo=FeatureRunRepository(session),
    )
