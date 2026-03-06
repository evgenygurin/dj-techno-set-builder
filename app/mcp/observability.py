"""Centralized MCP observability: middleware, logging, telemetry.

This module applies all middleware to the FastMCP gateway in the correct order.
The order matters: ErrorHandling -> StructuredLogging -> DetailedTiming ->
ResponseCaching -> Retry -> Ping.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from fastmcp.server.middleware.error_handling import (
    ErrorHandlingMiddleware,
    RetryMiddleware,
)
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.ping import PingMiddleware
from fastmcp.server.middleware.timing import DetailedTimingMiddleware

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.server.middleware import MiddlewareContext

    from app.config import Settings

logger = logging.getLogger(__name__)


def _sentry_error_callback(
    error: Exception,
    context: MiddlewareContext,
) -> None:
    """Forward unhandled MCP errors to Sentry."""
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(error)
    except ImportError:
        logger.warning("sentry_sdk not available, skipping error capture")

    logger.error(
        "MCP tool error captured by Sentry",
        extra={
            "method": context.method,
            "error_type": type(error).__name__,
        },
    )


def apply_observability(mcp: FastMCP, settings: Settings) -> None:
    """Apply the full middleware stack to a FastMCP server.

    Middleware order (first added = outermost):
    1. ErrorHandling -- catches all errors, forwards to Sentry
    2. StructuredLogging -- JSON logs for each request/response
    3. DetailedTiming -- per-operation timing breakdown
    4. ResponseCaching -- DiskStore-backed cache with TTL
    5. Retry -- exponential backoff for transient errors
    6. Ping -- keepalive for HTTP/SSE connections
    """
    # 1. Error handling (outermost -- catches errors from all inner middleware)
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=settings.debug,
            error_callback=_sentry_error_callback if settings.sentry_dsn else None,
        )
    )

    # 2. Structured logging (JSON)
    mcp.add_middleware(
        StructuredLoggingMiddleware(
            include_payloads=settings.mcp_log_payloads,
        )
    )

    # 3. Detailed timing
    mcp.add_middleware(DetailedTimingMiddleware())

    # 4. Response caching — DISABLED: stale DiskStore cache can hide newly
    #    registered tools (list_tools returns cached snapshot). Re-enable
    #    once we add cache invalidation on tool registration.
    # cache_store = DiskStore(directory=settings.mcp_cache_dir)
    # mcp.add_middleware(
    #     ResponseCachingMiddleware(
    #         cache_storage=cache_store,
    #         call_tool_settings=CallToolSettings(
    #             ttl=settings.mcp_cache_ttl_tools,
    #         ),
    #         read_resource_settings=ReadResourceSettings(
    #             ttl=settings.mcp_cache_ttl_resources,
    #         ),
    #     )
    # )

    # 5. Retry (transient errors only)
    mcp.add_middleware(
        RetryMiddleware(
            max_retries=settings.mcp_retry_max,
            base_delay=settings.mcp_retry_backoff,
            retry_exceptions=(
                ConnectionError,
                TimeoutError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ),
        )
    )

    # 6. Ping (keepalive for SSE/streamable HTTP)
    mcp.add_middleware(PingMiddleware(interval_ms=settings.mcp_ping_interval * 1000))

    logger.info(
        "MCP observability applied: 6 middleware",
        extra={"server": mcp.name, "debug": settings.debug},
    )
