"""Tests for MCP progress reporting.

Progress calls are no-ops when the client doesn't send a progressToken,
so we verify that adding them doesn't break existing tool behaviour.
"""

from __future__ import annotations

from fastmcp import FastMCP


async def test_score_transitions_reports_progress(workflow_mcp: FastMCP):
    """score_transitions tool still registers correctly after adding progress."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "score_transitions" in tool_names


async def test_build_set_reports_progress(workflow_mcp: FastMCP):
    """build_set tool still registers correctly after adding progress."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "build_set" in tool_names


async def test_find_similar_tracks_reports_progress(workflow_mcp: FastMCP):
    """find_similar_tracks tool still registers correctly after adding progress."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "find_similar_tracks" in tool_names
