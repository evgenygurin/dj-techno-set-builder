"""Catalog provider — CRUD tools for tracks, playlists, sets, features."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_catalog_tools(mcp: FastMCP) -> None:
    """Register all catalog CRUD tools on the given MCP server."""
    from app.mcp.tools.track import register_track_tools
    from app.mcp.tools.playlist import register_playlist_tools
    from app.mcp.tools.set import register_set_tools
    from app.mcp.tools.features import register_features_tools

    register_track_tools(mcp)
    register_playlist_tools(mcp)
    register_set_tools(mcp)
    register_features_tools(mcp)
