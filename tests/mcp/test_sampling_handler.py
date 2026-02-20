"""Tests for sampling handler configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.config import Settings


def test_sampling_settings_defaults():
    """Sampling settings have sensible defaults."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        s = Settings(_env_file=None, database_url="sqlite+aiosqlite:///test.db")
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
        mock_settings.mcp_max_response_size = 500_000

        from app.mcp.gateway import create_dj_mcp

        gateway = create_dj_mcp()
        # When no API key, no sampling handler should be set
        assert gateway.sampling_handler is None
