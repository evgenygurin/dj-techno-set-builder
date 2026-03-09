"""Dependency injection providers for MCP tools.

Uses FastMCP's Depends() for automatic DI chain resolution.
Session is created once per-request and shared across all services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music import YandexMusicClient as YMApiClient
from app.config import settings
from app.database import session_factory
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.repositories.sections import SectionsRepository
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.repositories.tracks import TrackRepository
from app.repositories.transitions import TransitionRepository
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService
from app.services.track_analysis import TrackAnalysisService
from app.services.tracks import TrackService
from app.services.transitions import TransitionService
from app.services.yandex_music_client import YandexMusicClient as YMDownloadClient


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide an async DB session scoped to a single MCP tool call.

    Commits on success, rolls back on exception.  Without this,
    repository ``flush()`` writes are lost when the session closes.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_track_service(
    session: AsyncSession = Depends(get_session),
) -> TrackService:
    """Build a TrackService with all required repositories."""
    return TrackService(TrackRepository(session))


def get_playlist_service(
    session: AsyncSession = Depends(get_session),
) -> DjPlaylistService:
    """Build a DjPlaylistService with playlist and item repositories."""
    return DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )


def get_features_service(
    session: AsyncSession = Depends(get_session),
) -> AudioFeaturesService:
    """Build an AudioFeaturesService with features and track repositories."""
    return AudioFeaturesService(
        AudioFeaturesRepository(session),
        TrackRepository(session),
    )


def get_analysis_service(
    session: AsyncSession = Depends(get_session),
) -> TrackAnalysisService:
    """Build a TrackAnalysisService with track, features, and sections repos."""
    return TrackAnalysisService(
        TrackRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
    )


def get_set_service(
    session: AsyncSession = Depends(get_session),
) -> DjSetService:
    """Build a DjSetService with set, version, and item repositories."""
    return DjSetService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
    )


def get_set_generation_service(
    session: AsyncSession = Depends(get_session),
) -> SetGenerationService:
    """Build a SetGenerationService with all required repositories."""
    return SetGenerationService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
        DjPlaylistItemRepository(session),
    )


def get_transition_service(
    session: AsyncSession = Depends(get_session),
) -> TransitionService:
    """Build a TransitionService with a transition repository."""
    return TransitionService(TransitionRepository(session))


def get_ym_client() -> YMApiClient:
    """Build a YandexMusicClient API client from application settings."""
    return YMApiClient(
        token=settings.yandex_music_token,
        base_url=settings.yandex_music_base_url,
    )


def get_ym_download_client() -> YMDownloadClient:
    """Build a YandexMusicClient download client from application settings."""
    return YMDownloadClient(
        token=settings.yandex_music_token,
        user_id=settings.yandex_music_user_id,
    )


# --- Phase 3: Platform registry + sync ---

from app.mcp.platforms.factory import create_platform_registry  # noqa: E402
from app.mcp.platforms.registry import PlatformRegistry  # noqa: E402
from app.mcp.sync.engine import SyncEngine  # noqa: E402
from app.mcp.sync.track_mapper import DbTrackMapper  # noqa: E402

# Module-level singleton — created once, shared across all MCP tool calls.
_platform_registry: PlatformRegistry | None = None


def get_platform_registry() -> PlatformRegistry:
    """Provide the global PlatformRegistry singleton.

    Created on first call via create_platform_registry().
    """
    global _platform_registry
    if _platform_registry is None:
        _platform_registry = create_platform_registry()
    return _platform_registry


def get_sync_engine(
    session: AsyncSession = Depends(get_session),
) -> SyncEngine:
    """Build a SyncEngine with playlist service and track mapper."""
    playlist_svc = DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )
    mapper = DbTrackMapper(session)
    return SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)
