"""Tests for playlist workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_populate_from_ym_registered(workflow_mcp: FastMCP):
    """populate_from_ym tool should be registered."""
    tools = await workflow_mcp.list_tools()
    names = {t.name for t in tools}
    assert "populate_from_ym" in names


async def test_populate_from_ym_params(workflow_mcp: FastMCP):
    """populate_from_ym should accept playlist_id and ym_kind parameters."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "populate_from_ym")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "playlist_id" in props
    assert "ym_kind" in props


async def test_populate_from_ym_has_sync_tag(workflow_mcp: FastMCP):
    """populate_from_ym should have sync and yandex tags."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "populate_from_ym")
    assert tool.tags is not None
    assert "sync" in tool.tags
    assert "yandex" in tool.tags
