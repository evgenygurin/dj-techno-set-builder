"""Tests for export workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_export_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "export_set_rekordbox" in tool_names


async def test_rekordbox_tool_is_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    rb_tool = next(t for t in tools if t.name == "export_set_rekordbox")
    assert rb_tool.annotations is not None


async def test_rekordbox_tool_has_export_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    rb_tool = next(t for t in tools if t.name == "export_set_rekordbox")
    assert rb_tool.tags is not None
    assert "export" in rb_tool.tags


async def test_gateway_has_namespaced_rekordbox_tool(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_export_set_rekordbox" in tool_names
