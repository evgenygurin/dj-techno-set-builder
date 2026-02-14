"""Tests for analysis workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_analysis_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "get_playlist_status" in tool_names
    assert "get_track_details" in tool_names


async def test_analysis_tools_have_readonly_annotation(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"get_playlist_status", "get_track_details"}:
            assert tool.annotations is not None


async def test_gateway_has_namespaced_analysis_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_get_playlist_status" in tool_names
    assert "dj_get_track_details" in tool_names
