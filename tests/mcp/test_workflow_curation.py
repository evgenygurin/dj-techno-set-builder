"""Tests for curation workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_curation_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "classify_tracks" in tool_names
    assert "analyze_library_gaps" in tool_names
    assert "review_set" in tool_names
    assert "audit_playlist" in tool_names
    # curate_set removed — absorbed into build_set with template_slot_fit
    assert "curate_set" not in tool_names


async def test_curation_tools_have_curation_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    curation_names = {
        "classify_tracks", "analyze_library_gaps",
        "review_set", "audit_playlist",
    }
    for tool in tools:
        if tool.name in curation_names:
            assert tool.tags is not None
            assert "curation" in tool.tags


async def test_readonly_tools_have_annotation(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    readonly_names = {
        "classify_tracks", "analyze_library_gaps",
        "review_set", "audit_playlist",
    }
    for tool in tools:
        if tool.name in readonly_names:
            assert tool.annotations is not None
            assert tool.annotations.readOnlyHint is True


async def test_review_set_has_setbuilder_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    for tool in tools:
        if tool.name == "review_set":
            assert tool.tags is not None
            assert "setbuilder" in tool.tags
            assert "curation" in tool.tags
            break


async def test_gateway_has_namespaced_curation_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_classify_tracks" in tool_names
    assert "dj_analyze_library_gaps" in tool_names
    assert "dj_review_set" in tool_names
    assert "dj_audit_playlist" in tool_names
    # curate_set removed
    assert "dj_curate_set" not in tool_names
