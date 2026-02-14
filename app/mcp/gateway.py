"""MCP Gateway — combines all MCP sub-servers into one."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from app.config import settings
from app.mcp.lifespan import mcp_lifespan
from app.mcp.observability import apply_observability
from app.mcp.workflows import create_workflow_mcp
from app.mcp.yandex_music import create_yandex_music_mcp

logger = logging.getLogger(__name__)


def create_dj_mcp() -> FastMCP:
    """Create the gateway MCP server.

    Mounts Yandex Music (namespace "ym") and DJ Workflows (namespace "dj").
    Applies observability middleware and lifespan management.
    Adds PromptsAsTools and ResourcesAsTools transforms so that tool-only
    clients can still access prompts and resources.
    """
    gateway = FastMCP("DJ Set Builder", lifespan=mcp_lifespan)

    ym = create_yandex_music_mcp()
    gateway.mount(ym, namespace="ym")

    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    # Apply observability middleware stack
    apply_observability(gateway, settings)

    # Enable prompts/resources as tools for tool-only MCP clients
    try:
        from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools

        gateway.add_transform(PromptsAsTools(gateway))
        gateway.add_transform(ResourcesAsTools(gateway))
    except (ImportError, TypeError, AttributeError):
        logger.debug("PromptsAsTools/ResourcesAsTools not available; skipping transforms")

    return gateway
