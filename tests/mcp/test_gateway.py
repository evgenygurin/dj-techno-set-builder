"""Tests for MCP Gateway composition."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_gateway_creates_fastmcp(gateway_mcp: FastMCP):
    assert isinstance(gateway_mcp, FastMCP)
    assert gateway_mcp.name == "DJ Set Builder"


async def test_gateway_has_yandex_music_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    ym_tools = {n for n in tool_names if n.startswith("ym_")}
    assert len(ym_tools) > 0, f"No ym_ tools found. Available: {tool_names}"


async def test_gateway_has_workflow_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    dj_tools = {n for n in tool_names if n.startswith("dj_")}
    assert len(dj_tools) > 0, f"No dj_ tools found. Available: {tool_names}"


async def test_existing_yandex_music_tests_still_pass(ym_mcp: FastMCP):
    """Existing YM MCP tests should still work via direct import."""
    tools = await ym_mcp.list_tools()
    assert len(tools) > 0
