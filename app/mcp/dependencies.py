"""Dependency injection providers for MCP tools.

Uses FastMCP's Depends() for automatic DI chain resolution.
Delegates to services/_factories.py for actual construction.
Session is created once per-request and shared across all services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import session_factory
from app.mcp.platforms.factory import create_platform_registry
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.sync.engine import SyncEngine
from app.mcp.sync.track_mapper import DbTrackMapper
from app.services._factories import (
    create_analysis_service,
    create_features_service,
    create_playlist_service,
    create_set_generation_service,
    create_set_service,
    create_track_service,
    create_transition_service,
    create_unified_scoring,
    create_ym_api_client,
    create_ym_download_client,
)
from app.services.features import AudioFeaturesService
from app.services.playlists import DjPlaylistService
from app.services.set_generation import SetGenerationService
from app.services.sets import DjSetService
from app.services.track_analysis import TrackAnalysisService
from app.services.tracks import TrackService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.services.transitions import TransitionService
from app.services.yandex_music_client import YandexMusicClient as YMDownloadClient

# Re-export for backward compatibility
from app.infrastructure.clients.yandex_music import YandexMusicClient as YMApiClient  # noqa: F401


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide an async DB session scoped to a single MCP tool call.

    Commits on success, rolls back on exception.
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
    return create_track_service(session)


def get_playlist_service(
    session: AsyncSession = Depends(get_session),
) -> DjPlaylistService:
    return create_playlist_service(session)


def get_features_service(
    session: AsyncSession = Depends(get_session),
) -> AudioFeaturesService:
    return create_features_service(session)


def get_analysis_service(
    session: AsyncSession = Depends(get_session),
) -> TrackAnalysisService:
    return create_analysis_service(session)


def get_set_service(
    session: AsyncSession = Depends(get_session),
) -> DjSetService:
    return create_set_service(session)


def get_set_generation_service(
    session: AsyncSession = Depends(get_session),
) -> SetGenerationService:
    return create_set_generation_service(session)


def get_transition_service(
    session: AsyncSession = Depends(get_session),
) -> TransitionService:
    return create_transition_service(session)


def get_unified_scoring(
    session: AsyncSession = Depends(get_session),
) -> UnifiedTransitionScoringService:
    return create_unified_scoring(session)


def get_ym_client() -> YMApiClient:
    return create_ym_api_client()


def get_ym_download_client() -> YMDownloadClient:
    return create_ym_download_client()


# --- Platform registry + sync ---

_platform_registry: PlatformRegistry | None = None


def get_platform_registry() -> PlatformRegistry:
    """Provide the global PlatformRegistry singleton."""
    global _platform_registry  # noqa: PLW0603
    if _platform_registry is None:
        _platform_registry = create_platform_registry()
    return _platform_registry


def get_sync_engine(
    session: AsyncSession = Depends(get_session),
) -> SyncEngine:
    """Build a SyncEngine with playlist service and track mapper."""
    playlist_svc = create_playlist_service(session)
    mapper = DbTrackMapper(session)
    return SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)
