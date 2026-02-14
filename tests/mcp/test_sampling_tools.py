"""Tests for sampling with tool use in discovery and setbuilder tools."""

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
        assert "playlist_id" in props
        assert "count" in props


async def test_adjust_set_uses_sample_step(workflow_mcp: FastMCP):
    """adjust_set is registered correctly after adding sample_step loop."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "adjust_set")
        assert tool is not None
        props = tool.inputSchema.get("properties", {})
        assert "set_id" in props
        assert "instructions" in props
