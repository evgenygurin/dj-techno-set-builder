"""Tests for download_tools registration."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from app.mcp.tools.download import register_download_tools


@pytest.fixture
def mcp() -> FastMCP:
    server = FastMCP("test")
    register_download_tools(server)
    return server


async def test_download_tracks_registered(mcp: FastMCP):
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "download_tracks" in names


async def test_download_tracks_has_correct_tags(mcp: FastMCP):
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "download_tracks")
    assert "download" in (tool.tags or set())
