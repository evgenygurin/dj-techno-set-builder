"""Sync provider — platform sync, link, source-of-truth."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_sync_tools(mcp: FastMCP) -> None:
    """Register all sync tools on the given MCP server."""
    from app.mcp.tools.sync import register_sync_tools as _reg

    _reg(mcp)
