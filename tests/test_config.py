"""Tests for Settings defaults and env override."""

from app.config import Settings


def test_yandex_settings_have_defaults():
    s = Settings(database_url="sqlite+aiosqlite:///test.db", _env_file=None)
    assert s.yandex_music_token == ""
    assert s.yandex_music_user_id == ""


def test_sentry_defaults():
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.sentry_dsn == ""
    assert s.sentry_traces_sample_rate == 1.0
    assert s.sentry_send_pii is True
    assert s.environment == "development"


def test_otel_defaults():
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.otel_endpoint == ""
    assert s.otel_service_name == "dj-set-builder-mcp"


def test_mcp_observability_defaults():
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
