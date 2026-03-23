"""Unified service factories — single source of truth for DI construction.

Both MCP DI (FastMCP Depends) and any future adapter call these factories.
Each factory takes an AsyncSession and returns a fully-wired service.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.clients.yandex_music import YandexMusicClient as YMApiClient
from app.infrastructure.repositories.audio.features import AudioFeaturesRepository
from app.infrastructure.repositories.audio.sections import SectionsRepository
from app.infrastructure.repositories.audio.transitions import TransitionRepository
from app.infrastructure.repositories.catalog.tracks import TrackRepository
from app.infrastructure.repositories.dj.playlists import (
    DjPlaylistItemRepository,
    DjPlaylistRepository,
)
from app.infrastructure.repositories.dj.sets import (
    DjSetItemRepository,
    DjSetRepository,
    DjSetVersionRepository,
)
from app.services.audio.analysis import TrackAnalysisService
from app.services.audio.features import AudioFeaturesService
from app.services.audio.scoring_unified import UnifiedTransitionScoringService
from app.services.audio.transitions import TransitionService
from app.services.catalog.tracks import TrackService
from app.services.dj.generation import SetGenerationService
from app.services.dj.playlists import DjPlaylistService
from app.services.dj.sets import DjSetService
from app.services.platform.yandex.client import YandexMusicClient as YMDownloadClient


def create_track_service(session: AsyncSession) -> TrackService:
    """Build a TrackService with all required repositories."""
    return TrackService(TrackRepository(session))


def create_playlist_service(session: AsyncSession) -> DjPlaylistService:
    """Build a DjPlaylistService with playlist and item repositories."""
    return DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )


def create_features_service(session: AsyncSession) -> AudioFeaturesService:
    """Build an AudioFeaturesService with features and track repositories."""
    return AudioFeaturesService(
        AudioFeaturesRepository(session),
        TrackRepository(session),
    )


def create_analysis_service(session: AsyncSession) -> TrackAnalysisService:
    """Build a TrackAnalysisService with track, features, and sections repos."""
    return TrackAnalysisService(
        TrackRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
    )


def create_set_service(session: AsyncSession) -> DjSetService:
    """Build a DjSetService with set, version, and item repositories."""
    return DjSetService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
    )


def create_set_generation_service(session: AsyncSession) -> SetGenerationService:
    """Build a SetGenerationService with all required repositories."""
    return SetGenerationService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
        DjPlaylistItemRepository(session),
    )


def create_transition_service(session: AsyncSession) -> TransitionService:
    """Build a TransitionService with a transition repository."""
    return TransitionService(TransitionRepository(session))


def create_unified_scoring(session: AsyncSession) -> UnifiedTransitionScoringService:
    """Build a UnifiedTransitionScoringService with DB session."""
    return UnifiedTransitionScoringService(session)


def create_ym_api_client() -> YMApiClient:
    """Build a YandexMusicClient API client from application settings."""
    return YMApiClient(
        token=settings.yandex_music_token,
        base_url=settings.yandex_music_base_url,
    )


def create_ym_download_client() -> YMDownloadClient:
    """Build a YandexMusicClient download client from application settings."""
    return YMDownloadClient(
        token=settings.yandex_music_token,
        user_id=settings.yandex_music_user_id,
    )
