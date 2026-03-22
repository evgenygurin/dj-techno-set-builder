"""Tests for set builder workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_setbuilder_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "build_set" in tool_names
    assert "rebuild_set" in tool_names
    assert "score_transitions" in tool_names
    assert "score_track_pairs" in tool_names
    # adjust_set removed — replaced by rebuild_set with feedback loop
    assert "adjust_set" not in tool_names


async def test_score_transitions_is_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "score_transitions":
            assert tool.annotations is not None
            break


async def test_setbuilder_tools_have_setbuilder_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name in {"build_set", "rebuild_set", "score_transitions", "score_track_pairs"}:
            assert tool.tags is not None
            assert "setbuilder" in tool.tags


async def test_gateway_has_namespaced_setbuilder_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_build_set" in tool_names
    assert "dj_rebuild_set" in tool_names
    assert "dj_score_transitions" in tool_names
    assert "dj_score_track_pairs" in tool_names
    # adjust_set removed
    assert "dj_adjust_set" not in tool_names


async def test_score_track_pairs_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    names = {t.name for t in tools}
    assert "score_track_pairs" in names


async def test_score_track_pairs_is_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "score_track_pairs")
    assert tool.annotations is not None
    assert tool.tags is not None
    assert "setbuilder" in tool.tags


async def test_build_set_accepts_template(workflow_mcp: FastMCP):
    """build_set should accept template and exclude_track_ids params."""
    tools = await workflow_mcp.list_tools()
    build = next(t for t in tools if t.name == "build_set")
    props = set(build.parameters.get("properties", {}).keys())
    assert "template" in props
    assert "exclude_track_ids" in props
    assert "energy_arc" in props
    assert "track_count" in props
