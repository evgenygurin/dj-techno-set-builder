"""Discovery provider — search, filter, discover, expand, download."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_discovery_tools(mcp: FastMCP) -> None:
    """Register all discovery tools on the given MCP server."""
    from app.mcp.tools.curation_discovery import register_curation_discovery_tools
    from app.mcp.tools.discovery import register_discovery_tools as _reg_disc
    from app.mcp.tools.download import register_download_tools
    from app.mcp.tools.search import register_search_tools

    register_search_tools(mcp)
    _reg_disc(mcp)
    register_curation_discovery_tools(mcp)
    register_download_tools(mcp)
