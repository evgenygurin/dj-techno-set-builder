"""Tests for sampling with tool use in discovery tools."""

from __future__ import annotations

from fastmcp import Client, FastMCP


async def test_find_similar_tracks_provides_search_tool(workflow_mcp: FastMCP):
    """find_similar_tracks is registered correctly after adding tool use."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "find_similar_tracks")
        assert tool is not None
        # The tool still accepts the same params
        props = tool.inputSchema.get("properties", {})
        assert "playlist_ref" in props
        assert "count" in props
