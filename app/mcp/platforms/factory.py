"""Factory for creating PlatformRegistry with configured adapters."""

from __future__ import annotations

import logging

from app.clients.yandex_music import YandexMusicClient
from app.config import settings
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.platforms.yandex import YandexMusicAdapter

logger = logging.getLogger(__name__)


def create_platform_registry() -> PlatformRegistry:
    """Create a PlatformRegistry with all configured platform adapters.

    Checks app settings for each platform's credentials.
    Only registers adapters for platforms that have valid config.
    """
    registry = PlatformRegistry()

    # Yandex Music
    if settings.yandex_music_token and settings.yandex_music_user_id:
        client = YandexMusicClient(
            token=settings.yandex_music_token,
            user_id=settings.yandex_music_user_id,
        )
        adapter = YandexMusicAdapter(
            client=client,
            user_id=settings.yandex_music_user_id,
        )
        registry.register(adapter)
        logger.info("Registered YandexMusic adapter (user=%s)", settings.yandex_music_user_id)
    else:
        logger.info("YandexMusic adapter not configured — skipping")

    return registry
