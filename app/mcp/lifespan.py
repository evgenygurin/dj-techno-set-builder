"""MCP server lifespan — startup/shutdown for observability resources."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastmcp.server.lifespan import lifespan

logger = logging.getLogger(__name__)


@lifespan
async def mcp_lifespan(server):  # type: ignore[no-untyped-def]
    """Initialize observability resources on MCP server start.

    Yields context dict accessible via ctx.lifespan_context in tools.
    """
    started_at = datetime.now(tz=UTC).isoformat()
    logger.info(
        "MCP server starting",
        extra={"server": getattr(server, "name", "unknown"), "started_at": started_at},
    )
    try:
        yield {"started_at": started_at}
    finally:
        logger.info(
            "MCP server shutting down",
            extra={"server": getattr(server, "name", "unknown")},
        )
