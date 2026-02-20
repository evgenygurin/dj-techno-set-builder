"""Tests for Settings defaults and env override."""

import pytest

from app.config import Settings


def test_yandex_settings_have_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("YANDEX_MUSIC_TOKEN", raising=False)
    monkeypatch.delenv("YANDEX_MUSIC_USER_ID", raising=False)
    s = Settings(database_url="sqlite+aiosqlite:///test.db", _env_file=None)
    assert s.yandex_music_token == ""
    assert s.yandex_music_user_id == ""


def test_sentry_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("SENTRY_SEND_PII", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.sentry_dsn == ""
    assert s.sentry_traces_sample_rate == 1.0
    assert s.sentry_send_pii is True
    assert s.environment == "development"


def test_otel_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OTEL_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.otel_endpoint is None
    assert s.otel_service_name == "dj-set-builder-mcp"


def test_mcp_observability_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MCP_CACHE_DIR", raising=False)
    monkeypatch.delenv("MCP_CACHE_TTL_TOOLS", raising=False)
    monkeypatch.delenv("MCP_CACHE_TTL_RESOURCES", raising=False)
    monkeypatch.delenv("MCP_RETRY_MAX", raising=False)
    monkeypatch.delenv("MCP_RETRY_BACKOFF", raising=False)
    monkeypatch.delenv("MCP_PING_INTERVAL", raising=False)
    monkeypatch.delenv("MCP_LOG_PAYLOADS", raising=False)
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.mcp_cache_dir == "./cache/mcp"
    assert s.mcp_cache_ttl_tools == 60
    assert s.mcp_cache_ttl_resources == 300
    assert s.mcp_retry_max == 3
    assert s.mcp_retry_backoff == 1.0
    assert s.mcp_ping_interval == 30
    assert s.mcp_log_payloads is False
