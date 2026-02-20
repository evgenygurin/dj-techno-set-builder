"""Tests for MCP observability middleware stack."""

from __future__ import annotations

from fastmcp import FastMCP

from app.config import Settings


def _make_settings(**overrides: object) -> Settings:
    """Create Settings with required fields and optional overrides."""
    defaults = {
        "_env_file": None,
        "yandex_music_token": "t",
        "yandex_music_user_id": "u",
    }
    return Settings(**(defaults | overrides))  # type: ignore[arg-type]


async def test_apply_observability_adds_middleware():
    """apply_observability should add 5 middleware to gateway (caching disabled)."""
    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    before = len(mcp.middleware)
    apply_observability(mcp, _make_settings())
    # 5 middleware (caching disabled): ErrorHandling, Logging, Timing, Retry, Ping
    assert len(mcp.middleware) - before == 5


async def test_apply_observability_correct_order():
    """Middleware order: ErrorHandling, StructuredLogging, DetailedTiming, Retry, Ping."""
    from fastmcp.server.middleware.error_handling import (
        ErrorHandlingMiddleware,
        RetryMiddleware,
    )
    from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
    from fastmcp.server.middleware.ping import PingMiddleware
    from fastmcp.server.middleware.timing import DetailedTimingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings())

    expected_order = [
        ErrorHandlingMiddleware,
        StructuredLoggingMiddleware,
        DetailedTimingMiddleware,
        RetryMiddleware,
        PingMiddleware,
    ]
    added = mcp.middleware[offset:]
    for i, (mw, expected_cls) in enumerate(zip(added, expected_order, strict=True)):
        assert isinstance(mw, expected_cls), (
            f"Middleware #{i}: expected {expected_cls.__name__}, got {type(mw).__name__}"
        )


async def test_apply_observability_respects_debug_settings():
    """Debug mode enables tracebacks and payload logging."""
    from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
    from fastmcp.server.middleware.logging import StructuredLoggingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings(debug=True, mcp_log_payloads=True))

    err_mw = mcp.middleware[offset + 0]
    assert isinstance(err_mw, ErrorHandlingMiddleware)
    assert err_mw.include_traceback is True

    log_mw = mcp.middleware[offset + 1]
    assert isinstance(log_mw, StructuredLoggingMiddleware)
    assert log_mw.include_payloads is True


async def test_apply_observability_retry_config():
    """Retry middleware respects settings."""
    from fastmcp.server.middleware.error_handling import RetryMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings(mcp_retry_max=5, mcp_retry_backoff=2.0))

    retry_mw = mcp.middleware[offset + 3]  # index 3 (caching removed, was 4)
    assert isinstance(retry_mw, RetryMiddleware)
    assert retry_mw.max_retries == 5
    assert retry_mw.base_delay == 2.0


async def test_apply_observability_no_sentry_callback_without_dsn():
    """Without sentry_dsn, error_callback should be None."""
    from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings(sentry_dsn=""))

    err_mw = mcp.middleware[offset + 0]
    assert isinstance(err_mw, ErrorHandlingMiddleware)
    assert err_mw.error_callback is None


async def test_apply_observability_sentry_callback_with_dsn():
    """With sentry_dsn set, error_callback should be the Sentry forwarder."""
    from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(
        mcp, _make_settings(sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0")
    )

    err_mw = mcp.middleware[offset + 0]
    assert isinstance(err_mw, ErrorHandlingMiddleware)
    assert err_mw.error_callback is not None


async def test_apply_observability_ping_interval():
    """Ping interval should be converted from seconds to milliseconds."""
    from fastmcp.server.middleware.ping import PingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings(mcp_ping_interval=45))

    ping_mw = mcp.middleware[offset + 4]  # index 4 (caching removed, was 5)
    assert isinstance(ping_mw, PingMiddleware)
    assert ping_mw.interval_ms == 45_000
