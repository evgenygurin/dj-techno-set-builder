"""Tests for import workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_import_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "import_playlist" in tool_names
    assert "import_tracks" in tool_names


async def test_import_tools_have_import_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"import_playlist", "import_tracks"}:
            assert tool.tags is not None
            assert "import" in tool.tags


async def test_gateway_has_namespaced_import_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_import_playlist" in tool_names
    assert "dj_import_tracks" in tool_names
