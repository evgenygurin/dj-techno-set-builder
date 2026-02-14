"""Tests for export workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_export_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "export_set_m3u" in tool_names
    assert "export_set_json" in tool_names


async def test_export_tools_are_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"export_set_m3u", "export_set_json"}:
            assert tool.annotations is not None


async def test_export_tools_have_export_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"export_set_m3u", "export_set_json"}:
            assert tool.tags is not None
            assert "export" in tool.tags


async def test_gateway_has_namespaced_export_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_export_set_m3u" in tool_names
    assert "dj_export_set_json" in tool_names
