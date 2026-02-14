"""MCP Gateway — combines all MCP sub-servers into one."""

from __future__ import annotations

from fastmcp import FastMCP

from app.mcp.workflows import create_workflow_mcp
from app.mcp.yandex_music import create_yandex_music_mcp


def create_dj_mcp() -> FastMCP:
    """Create the gateway MCP server.

    Mounts Yandex Music (namespace "ym") and DJ Workflows (namespace "dj").
    """
    gateway = FastMCP("DJ Set Builder")

    ym = create_yandex_music_mcp()
    gateway.mount(ym, namespace="ym")

    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    return gateway
