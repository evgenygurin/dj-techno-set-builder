"""Tests for MCP pagination support."""

from __future__ import annotations

from fastmcp import Client, FastMCP


async def test_pagination_returns_cursor_when_page_size_exceeded():
    """Server with list_page_size=2 paginates 3+ tools."""
    mcp = FastMCP("test", list_page_size=2)

    @mcp.tool
    def tool_a() -> str:
        """Tool A."""
        return "a"

    @mcp.tool
    def tool_b() -> str:
        """Tool B."""
        return "b"

    @mcp.tool
    def tool_c() -> str:
        """Tool C."""
        return "c"

    async with Client(mcp) as client:
        # First page: 2 tools + cursor
        result = await client.list_tools_mcp()
        assert len(result.tools) == 2
        assert result.nextCursor is not None

        # Second page: 1 tool, no cursor
        result2 = await client.list_tools_mcp(cursor=result.nextCursor)
        assert len(result2.tools) == 1
        assert result2.nextCursor is None


async def test_pagination_auto_collects_all():
    """Client.list_tools() auto-collects all pages."""
    mcp = FastMCP("test", list_page_size=2)

    @mcp.tool
    def tool_a() -> str:
        """Tool A."""
        return "a"

    @mcp.tool
    def tool_b() -> str:
        """Tool B."""
        return "b"

    @mcp.tool
    def tool_c() -> str:
        """Tool C."""
        return "c"

    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert len(tools) == 3


async def test_gateway_has_page_size():
    """Gateway uses mcp_page_size from settings."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()
    # list_page_size is set on the server settings
    assert gateway._list_page_size is not None
