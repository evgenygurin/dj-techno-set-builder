"""Tests for tool timeout configuration."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_download_tracks_has_io_timeout(workflow_mcp: FastMCP):
    """I/O tools should have 600s timeout."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "download_tracks")
    assert tool.timeout == 600


async def test_sync_tools_have_io_timeout(workflow_mcp: FastMCP):
    """Sync tools should have 600s timeout."""
    tools = await workflow_mcp.list_tools()
    sync_names = {"sync_playlist", "sync_set_to_ym", "sync_set_from_ym"}
    for tool in tools:
        if tool.name in sync_names:
            assert tool.timeout == 600, f"{tool.name} timeout={tool.timeout}, expected 600"


async def test_build_set_has_compute_timeout(workflow_mcp: FastMCP):
    """Set builder tools should have 600s timeout (GA needs time for large templates)."""
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"build_set", "rebuild_set"}:
            assert tool.timeout == 600, f"{tool.name} timeout={tool.timeout}, expected 600"


async def test_score_tools_have_medium_timeout(workflow_mcp: FastMCP):
    """Scoring tools should have 120s timeout, compute_set_order 600s."""
    tools = await workflow_mcp.list_tools()
    score_names = {"score_transitions", "review_set"}
    for tool in tools:
        if tool.name in score_names:
            assert tool.timeout == 120, f"{tool.name} timeout={tool.timeout}, expected 120"
        if tool.name == "compute_set_order":
            assert tool.timeout == 600, f"compute_set_order timeout={tool.timeout}, expected 600"


async def test_analyze_track_has_compute_timeout(workflow_mcp: FastMCP):
    """analyze_track should have 300s timeout (audio feature extraction)."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "analyze_track")
    assert tool.timeout == 300
