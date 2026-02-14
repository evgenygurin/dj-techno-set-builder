"""Tests for discovery workflow tools."""

from __future__ import annotations


async def test_discovery_tools_registered():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "find_similar_tracks" in tool_names
    assert "search_by_criteria" in tool_names


async def test_search_by_criteria_is_readonly():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        if tool.name == "search_by_criteria":
            assert tool.annotations is not None
            break


async def test_discovery_tools_have_discovery_tag():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        if tool.name in {"find_similar_tracks", "search_by_criteria"}:
            assert tool.tags is not None
            assert "discovery" in tool.tags


async def test_gateway_has_namespaced_discovery_tools():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_find_similar_tracks" in tool_names
    assert "dj_search_by_criteria" in tool_names
