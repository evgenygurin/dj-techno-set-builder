"""Tests for universal search + filter_tracks tools."""

from __future__ import annotations

from fastmcp import Client


async def test_search_registered(workflow_mcp):
    """search tool is registered in workflow server."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "search" in tool_names


async def test_filter_tracks_registered(workflow_mcp):
    """filter_tracks tool is registered in workflow server."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "filter_tracks" in tool_names


async def test_search_readonly_hint(workflow_mcp):
    """search tool has readOnlyHint annotation."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        search_tool = next(t for t in tools if t.name == "search")
        assert search_tool.annotations is not None
        assert search_tool.annotations.readOnlyHint is True


async def test_filter_tracks_readonly_hint(workflow_mcp):
    """filter_tracks tool has readOnlyHint annotation."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        ft_tool = next(t for t in tools if t.name == "filter_tracks")
        assert ft_tool.annotations is not None
        assert ft_tool.annotations.readOnlyHint is True


async def test_search_tool_has_description(workflow_mcp):
    """search tool has a meaningful description."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        search_tool = next(t for t in tools if t.name == "search")
        assert search_tool.description is not None
        assert "search" in search_tool.description.lower()


async def test_filter_tracks_tool_has_description(workflow_mcp):
    """filter_tracks tool has a meaningful description."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        ft_tool = next(t for t in tools if t.name == "filter_tracks")
        assert ft_tool.description is not None
        assert "filter" in ft_tool.description.lower()
