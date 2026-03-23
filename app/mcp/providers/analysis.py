"""Analysis provider — audio analysis, classification, library gaps."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_analysis_tools(mcp: FastMCP) -> None:
    """Register all analysis tools on the given MCP server."""
    from app.mcp.tools.compute import register_compute_tools
    from app.mcp.tools.curation import register_curation_tools

    register_compute_tools(mcp)
    register_curation_tools(mcp)
