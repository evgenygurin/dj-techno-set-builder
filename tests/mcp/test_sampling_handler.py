"""Tests for sampling handler configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import Settings


def test_sampling_settings_defaults(monkeypatch: pytest.MonkeyPatch):
    """Sampling settings have sensible defaults."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SAMPLING_MODEL", raising=False)
    monkeypatch.delenv("SAMPLING_MAX_TOKENS", raising=False)
    s = Settings(database_url="sqlite+aiosqlite:///test.db", _env_file=None)
    assert s.anthropic_api_key == ""
    assert s.sampling_model == "claude-sonnet-4-5-20250929"
    assert s.sampling_max_tokens == 1024


def test_gateway_no_handler_when_no_key():
    """Gateway doesn't set sampling_handler when api key is empty."""
    with patch("app.mcp.gateway.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        mock_settings.mcp_page_size = 50
        mock_settings.sampling_model = "claude-sonnet-4-5-20250929"
        mock_settings.debug = False
        mock_settings.sentry_dsn = ""
        mock_settings.mcp_log_payloads = False
        mock_settings.mcp_cache_dir = "./cache/mcp"
        mock_settings.mcp_cache_ttl_tools = 60
        mock_settings.mcp_cache_ttl_resources = 300
        mock_settings.mcp_retry_max = 3
        mock_settings.mcp_retry_backoff = 1.0
        mock_settings.mcp_ping_interval = 30

        from app.mcp.gateway import create_dj_mcp

        gateway = create_dj_mcp()
        # When no API key, no sampling handler should be set
        assert gateway.sampling_handler is None
