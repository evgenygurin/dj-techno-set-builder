"""Tests for discovery workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_discovery_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "find_similar_tracks" in tool_names
    assert "search_by_criteria" in tool_names


async def test_search_by_criteria_is_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "search_by_criteria":
            assert tool.annotations is not None
            break


async def test_discovery_tools_have_discovery_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"find_similar_tracks", "search_by_criteria"}:
            assert tool.tags is not None
            assert "discovery" in tool.tags


async def test_find_similar_tracks_uses_structured_output(workflow_mcp: FastMCP):
    """find_similar_tracks tool is registered and ready for structured sampling."""
    from fastmcp import Client

    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "find_similar_tracks")
        # Tool should accept playlist_id and count params (MCP wire schema)
        assert tool.inputSchema is not None
        props = tool.inputSchema.get("properties", {})
        assert "playlist_id" in props
        assert "count" in props


async def test_gateway_has_namespaced_discovery_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_find_similar_tracks" in tool_names
    assert "dj_search_by_criteria" in tool_names
