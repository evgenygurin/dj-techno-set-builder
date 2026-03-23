"""Export provider — M3U, JSON, Rekordbox export."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_export_tools(mcp: FastMCP) -> None:
    """Register all export tools on the given MCP server."""
    from app.mcp.tools.export import register_export_tools as _reg_export
    from app.mcp.tools.unified_export import register_unified_export_tools

    _reg_export(mcp)
    register_unified_export_tools(mcp)
