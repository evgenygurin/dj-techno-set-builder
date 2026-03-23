"""Set builder provider — build, rebuild, score, deliver."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_setbuilder_tools(mcp: FastMCP) -> None:
    """Register all set builder tools on the given MCP server."""
    from app.mcp.tools.delivery import register_delivery_tools
    from app.mcp.tools.setbuilder import register_setbuilder_tools as _reg_sb

    _reg_sb(mcp)
    register_delivery_tools(mcp)
