"""Tests for sync workflow tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_sync_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "sync_set_to_ym" in tool_names
    assert "sync_set_from_ym" in tool_names
    assert "sync_playlist" in tool_names


async def test_sync_tools_have_sync_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    ym_sync_tools = {"sync_set_to_ym", "sync_set_from_ym"}
    for tool in tools:
        if tool.name in ym_sync_tools:
            assert tool.tags is not None
            assert "sync" in tool.tags
            assert "yandex" in tool.tags
        elif tool.name == "sync_playlist":
            assert tool.tags is not None
            assert "sync" in tool.tags


async def test_gateway_has_namespaced_sync_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_sync_set_to_ym" in tool_names
    assert "dj_sync_set_from_ym" in tool_names
    assert "dj_sync_playlist" in tool_names


async def test_sync_set_to_ym_params(workflow_mcp: FastMCP):
    """sync_set_to_ym should accept set_id and force parameters."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "sync_set_to_ym")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "set_id" in props
    assert "force" in props


async def test_sync_set_from_ym_params(workflow_mcp: FastMCP):
    """sync_set_from_ym should accept set_id parameter."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "sync_set_from_ym")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "set_id" in props


async def test_sync_playlist_params(workflow_mcp: FastMCP):
    """sync_playlist should accept playlist_id and force parameters."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "sync_playlist")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "playlist_id" in props
    assert "force" in props


async def test_set_source_of_truth_registered(workflow_mcp: FastMCP):
    """set_source_of_truth tool should be registered."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "set_source_of_truth" in tool_names


async def test_link_playlist_registered(workflow_mcp: FastMCP):
    """link_playlist tool should be registered."""
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "link_playlist" in tool_names


async def test_set_source_of_truth_params(workflow_mcp: FastMCP):
    """set_source_of_truth should accept playlist_id and source parameters."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "set_source_of_truth")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "playlist_id" in props
    assert "source" in props


async def test_link_playlist_params(workflow_mcp: FastMCP):
    """link_playlist should accept playlist_id, platform, platform_playlist_id."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "link_playlist")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "playlist_id" in props
    assert "platform" in props
    assert "platform_playlist_id" in props


async def test_batch_sync_sets_to_ym_registered(workflow_mcp: FastMCP):
    """batch_sync_sets_to_ym tool should be registered."""
    tools = await workflow_mcp.list_tools()
    names = {t.name for t in tools}
    assert "batch_sync_sets_to_ym" in names


async def test_batch_sync_sets_to_ym_params(workflow_mcp: FastMCP):
    """batch_sync_sets_to_ym should accept set_ids and force parameters."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "batch_sync_sets_to_ym")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "set_ids" in props
    assert "force" in props


async def test_batch_sync_sets_to_ym_has_tags(workflow_mcp: FastMCP):
    """batch_sync_sets_to_ym should have sync and yandex tags."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "batch_sync_sets_to_ym")
    assert tool.tags is not None
    assert "sync" in tool.tags
    assert "yandex" in tool.tags
