"""Tests for Yandex Music MCP server creation and configuration."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_create_yandex_music_mcp_returns_fastmcp():
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    assert isinstance(mcp, FastMCP)


async def test_mcp_server_has_tools():
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    tools = await mcp.list_tools()
    assert len(tools) > 0, "MCP server should have at least one tool"


async def test_excluded_endpoints_are_absent():
    """Endpoints like /account, /feed, /rotor should be excluded."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    excluded_prefixes = {"get_account", "get_feed", "get_rotor", "get_station"}
    for prefix in excluded_prefixes:
        matching = {n for n in tool_names if n.startswith(prefix)}
        assert not matching, f"Excluded tools found: {matching}"


async def test_dj_relevant_tools_present():
    """Core DJ tools should be present: search, tracks, albums, artists."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = {"search_yandex_music", "get_tracks", "get_genres"}
    missing = expected - tool_names
    assert not missing, f"Expected DJ tools missing: {missing}. Available: {tool_names}"


async def test_tool_names_are_snake_case():
    """All tool names should be snake_case, not camelCase."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        assert tool.name == tool.name.lower(), f"Tool name not lowercase: {tool.name}"
        assert " " not in tool.name, f"Tool name has spaces: {tool.name}"
