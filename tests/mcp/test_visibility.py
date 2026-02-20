"""Tests for visibility control and transforms."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_activate_heavy_mode_tool_exists(workflow_mcp: FastMCP):
    """The activate_heavy_mode tool should be registered."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "activate_heavy_mode" in tool_names


async def test_heavy_tagged_tools_hidden_by_default(workflow_mcp: FastMCP):
    """Tools tagged with 'heavy' should not appear in the default tool list.

    Currently no tools are tagged 'heavy' yet, but the disable(tags={'heavy'})
    call should not break anything. This test verifies the mechanism works.
    """
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}

    # activate_heavy_mode is tagged "admin", not "heavy", so it's visible
    assert "activate_heavy_mode" in tool_names

    # All listed tools should NOT have the "heavy" tag
    for tool in tools:
        if hasattr(tool, "tags") and tool.tags:
            assert "heavy" not in tool.tags, (
                f"Tool '{tool.name}' is tagged 'heavy' but should be hidden"
            )


async def test_gateway_has_transform_tools(gateway_mcp: FastMCP):
    """Gateway should have PromptsAsTools/ResourcesAsTools transform tools."""
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}

    # PromptsAsTools adds: list_prompts, get_prompt
    # ResourcesAsTools adds: list_resources, read_resource
    assert "list_prompts" in tool_names
    assert "get_prompt" in tool_names
    assert "list_resources" in tool_names
    assert "read_resource" in tool_names


async def test_gateway_preserves_all_dj_tools(gateway_mcp: FastMCP):
    """Adding transforms should not remove any existing dj_ tools."""
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}

    # Spot-check a few core tools still present
    assert "dj_build_set" in tool_names
    assert "dj_get_track" in tool_names
    assert "dj_export_set_rekordbox" in tool_names


async def test_gateway_preserves_ym_tools(gateway_mcp: FastMCP):
    """Adding transforms should not remove any existing ym_ tools."""
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    ym_tools = {n for n in tool_names if n.startswith("ym_")}
    assert len(ym_tools) > 0, f"No ym_ tools found. Available: {tool_names}"


async def test_activate_ym_raw_tool_exists(workflow_mcp: FastMCP):
    """The activate_ym_raw tool should be registered."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "activate_ym_raw" in tool_names


async def test_list_platforms_tool_exists(workflow_mcp: FastMCP):
    """The list_platforms tool should be registered."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "list_platforms" in tool_names


async def test_list_platforms_has_admin_tag(workflow_mcp: FastMCP):
    """list_platforms should be tagged as admin."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "list_platforms")
    assert tool.tags is not None
    assert "admin" in tool.tags


async def test_activate_ym_raw_has_admin_tag(workflow_mcp: FastMCP):
    """activate_ym_raw should be tagged as admin."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "activate_ym_raw")
    assert tool.tags is not None
    assert "admin" in tool.tags
