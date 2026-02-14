"""Tests for MCP Gateway composition."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_gateway_creates_fastmcp():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    assert isinstance(mcp, FastMCP)
    assert mcp.name == "DJ Set Builder"


async def test_gateway_has_yandex_music_tools():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    ym_tools = {n for n in tool_names if n.startswith("ym_")}
    assert len(ym_tools) > 0, f"No ym_ tools found. Available: {tool_names}"


async def test_gateway_has_workflow_tools():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    dj_tools = {n for n in tool_names if n.startswith("dj_")}
    assert len(dj_tools) > 0, f"No dj_ tools found. Available: {tool_names}"


async def test_existing_yandex_music_tests_still_pass():
    """Existing YM MCP tests should still work via direct import."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    tools = await mcp.list_tools()
    assert len(tools) > 0
