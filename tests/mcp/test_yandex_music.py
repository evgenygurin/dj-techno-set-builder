"""Tests for Yandex Music MCP server creation and configuration."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_create_yandex_music_mcp_returns_fastmcp(ym_mcp: FastMCP):
    assert isinstance(ym_mcp, FastMCP)


async def test_mcp_server_has_tools(ym_mcp: FastMCP):
    tools = await ym_mcp.list_tools()
    assert len(tools) > 0, "MCP server should have at least one tool"


async def test_excluded_endpoints_are_absent(ym_mcp: FastMCP):
    """Endpoints like /account, /feed, /rotor should be excluded."""
    tools = await ym_mcp.list_tools()
    tool_names = {t.name for t in tools}
    excluded_prefixes = {"get_account", "get_feed", "get_rotor", "get_station"}
    for prefix in excluded_prefixes:
        matching = {n for n in tool_names if n.startswith(prefix)}
        assert not matching, f"Excluded tools found: {matching}"


async def test_dj_relevant_tools_present(ym_mcp: FastMCP):
    """Core DJ tools should be present: search, tracks, albums, artists."""
    tools = await ym_mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = {"search_yandex_music", "get_tracks", "get_genres"}
    missing = expected - tool_names
    assert not missing, f"Expected DJ tools missing: {missing}. Available: {tool_names}"


async def test_tool_names_are_snake_case(ym_mcp: FastMCP):
    """All tool names should be snake_case, not camelCase."""
    tools = await ym_mcp.list_tools()
    for tool in tools:
        assert tool.name == tool.name.lower(), f"Tool name not lowercase: {tool.name}"
        assert " " not in tool.name, f"Tool name has spaces: {tool.name}"
