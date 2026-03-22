"""Tests for download MCP tools."""

from fastmcp import FastMCP


async def test_download_tracks_tool_registered_in_workflow(workflow_mcp: FastMCP) -> None:
    """download_tracks tool is registered in workflow MCP server."""
    tools = [t.name for t in await workflow_mcp.list_tools()]
    assert "download_tracks" in tools


async def test_download_tracks_tool_registered_in_gateway(gateway_mcp: FastMCP) -> None:
    """download_tracks tool is registered in gateway with dj_ namespace."""
    tools = [t.name for t in await gateway_mcp.list_tools()]
    assert "dj_download_tracks" in tools


async def test_download_tracks_tool_has_correct_metadata(workflow_mcp: FastMCP) -> None:
    """download_tracks tool has correct tags and readonly flag."""
    tools = {t.name: t for t in await workflow_mcp.list_tools()}
    tool = tools["download_tracks"]

    assert "download" in tool.tags
    assert "yandex" in tool.tags
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.openWorldHint is True
