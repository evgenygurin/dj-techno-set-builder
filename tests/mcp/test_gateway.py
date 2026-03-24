"""Tests for MCP Gateway composition."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_gateway_creates_fastmcp(gateway_mcp: FastMCP):
    assert isinstance(gateway_mcp, FastMCP)
    assert gateway_mcp.name == "DJ Set Builder"


async def test_gateway_has_dj_tools(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    dj_tools = {n for n in tool_names if n.startswith("dj_")}
    assert len(dj_tools) > 0, f"No dj_ tools found. Available: {tool_names}"


async def test_gateway_no_ym_namespace(gateway_mcp: FastMCP):
    """YM OpenAPI server removed — only dj_ namespace."""
    tools = await gateway_mcp.list_tools()
    tool_names = {t.name for t in tools}
    ym_tools = {n for n in tool_names if n.startswith("ym_")}
    assert len(ym_tools) == 0, f"Unexpected ym_ tools: {ym_tools}"


async def test_gateway_has_middleware(gateway_mcp: FastMCP):
    assert len(gateway_mcp.middleware) >= 6


async def test_gateway_has_lifespan(gateway_mcp: FastMCP):
    from fastmcp.server.lifespan import Lifespan
    from fastmcp.server.server import default_lifespan

    assert gateway_mcp._lifespan is not default_lifespan
    assert isinstance(gateway_mcp._lifespan, Lifespan)
