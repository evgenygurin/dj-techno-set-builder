"""Tests for PlatformRegistry DI integration."""

from __future__ import annotations

from unittest.mock import patch

from app.mcp.platforms.protocol import PlatformCapability


class TestRegistryFactory:
    def test_create_registry_with_ym(self) -> None:
        """Registry includes YM adapter when token is configured."""
        from app.mcp.platforms.factory import create_platform_registry

        with patch("app.mcp.platforms.factory.settings") as mock_settings:
            mock_settings.yandex_music_token = "test_token"
            mock_settings.yandex_music_user_id = "250905515"

            registry = create_platform_registry()

        assert registry.is_connected("ym")
        assert registry.has_capability("ym", PlatformCapability.SEARCH)

    def test_create_registry_without_ym(self) -> None:
        """Registry is empty when no token configured."""
        from app.mcp.platforms.factory import create_platform_registry

        with patch("app.mcp.platforms.factory.settings") as mock_settings:
            mock_settings.yandex_music_token = ""
            mock_settings.yandex_music_user_id = ""

            registry = create_platform_registry()

        assert not registry.is_connected("ym")
        assert registry.list_connected() == []

    def test_create_registry_ym_no_user_id(self) -> None:
        """YM adapter not registered when user_id is missing."""
        from app.mcp.platforms.factory import create_platform_registry

        with patch("app.mcp.platforms.factory.settings") as mock_settings:
            mock_settings.yandex_music_token = "test_token"
            mock_settings.yandex_music_user_id = ""

            registry = create_platform_registry()

        assert not registry.is_connected("ym")
