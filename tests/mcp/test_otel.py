"""Tests for OpenTelemetry OTLP initialisation in MCP lifespan."""

from __future__ import annotations

from unittest.mock import patch

from app.config import Settings


def _make_settings(**overrides: object) -> Settings:
    """Create Settings with required fields and optional overrides."""
    defaults: dict[str, object] = {
        "_env_file": None,
        "yandex_music_token": "t",
        "yandex_music_user_id": "u",
    }
    return Settings(**(defaults | overrides))  # type: ignore[arg-type]


async def test_otel_not_initialized_without_endpoint() -> None:
    """_init_otel() should return None when otel_endpoint is None or empty."""
    from app.mcp.lifespan import _init_otel

    with patch("app.mcp.lifespan.settings", _make_settings(otel_endpoint=None)):
        result = _init_otel()

    assert result is None


async def test_otel_respects_existing_tracer_provider() -> None:
    """When otel_endpoint is disabled, the existing tracer provider must not be touched."""
    from app.mcp.lifespan import _init_otel

    # Patch the module-level settings so _init_otel sees otel_endpoint=None.
    # The existing provider (whatever OTel's global default is) must remain unchanged.
    try:
        from opentelemetry import trace

        provider_before = trace.get_tracer_provider()
    except ImportError:
        # opentelemetry is not installed — nothing to compare; pass trivially.
        provider_before = None

    with patch("app.mcp.lifespan.settings", _make_settings(otel_endpoint=None)):
        result = _init_otel()

    assert result is None

    # Verify the global provider was not changed.
    if provider_before is not None:
        from opentelemetry import trace as _trace

        assert _trace.get_tracer_provider() is provider_before
