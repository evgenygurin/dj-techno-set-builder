"""Tests for set builder workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_setbuilder_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "build_set" in tool_names
    assert "score_transitions" in tool_names
    assert "adjust_set" in tool_names


async def test_score_transitions_is_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "score_transitions":
            assert tool.annotations is not None
            break


async def test_setbuilder_tools_have_setbuilder_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"build_set", "score_transitions", "adjust_set"}:
            assert tool.tags is not None
            assert "setbuilder" in tool.tags


async def test_gateway_has_namespaced_setbuilder_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_build_set" in tool_names
    assert "dj_score_transitions" in tool_names
    assert "dj_adjust_set" in tool_names
