"""Tests for visibility control and transforms."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_activate_heavy_mode_tool_exists(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "activate_heavy_mode" in tool_names


async def test_heavy_tagged_tools_hidden_by_default(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for t in tools:
        if hasattr(t, "tags") and t.tags:
            assert "heavy" not in t.tags, f"Tool '{t.name}' is tagged 'heavy' but should be hidden"


async def test_gateway_has_transform_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "list_prompts" in tool_names
    assert "get_prompt" in tool_names
    assert "list_resources" in tool_names
    assert "read_resource" in tool_names


async def test_gateway_preserves_all_dj_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_build_set" in tool_names
    assert "dj_get_track" in tool_names


async def test_gateway_has_ym_tools(gateway_mcp: FastMCP):
    """YM client methods registered as ym_* tools."""
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    ym_tools = {n for n in tool_names if n.startswith("dj_ym_")}
    assert len(ym_tools) > 20, f"Expected >20 ym tools, got {len(ym_tools)}: {ym_tools}"


async def test_list_platforms_tool_exists(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "list_platforms" in tool_names
