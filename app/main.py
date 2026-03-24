"""Application entry point — standalone FastMCP server.

No FastAPI, no REST API. Pure MCP over StreamableHTTP or stdio.
Per FastMCP v3 docs: mcp.run() handles all transport configuration.
"""

from __future__ import annotations

import logging

import sentry_sdk

from app.config import settings

logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    """Initialize Sentry SDK if DSN is configured.

    MUST be called before importing FastMCP so that the OTEL TracerProvider
    is set up before FastMCP creates its tracer.
    """
    if not settings.sentry_dsn:
        logger.debug("Sentry DSN not set, skipping init")
        return

    from sentry_sdk.integrations import Integration

    integrations: list[Integration] = []

    try:
        from sentry_sdk.integrations.mcp import MCPIntegration

        integrations.append(MCPIntegration())
    except ImportError:
        logger.warning("sentry_sdk.integrations.mcp not available, skipping MCPIntegration")

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=settings.sentry_send_pii,
        environment=settings.environment,
        integrations=integrations,
    )
    logger.info("Sentry initialized", extra={"environment": settings.environment})


# Initialize Sentry BEFORE importing FastMCP
_init_sentry()

from app.mcp import create_dj_mcp  # noqa: E402

mcp = create_dj_mcp()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
