"""Tests for MCP lifespan management."""

from fastmcp import Client, Context, FastMCP


async def test_mcp_lifespan_yields_context():
    """Lifespan should yield a dict that tools can access via ctx.lifespan_context."""
    from app.mcp.lifespan import mcp_lifespan

    mcp = FastMCP("test", lifespan=mcp_lifespan)

    @mcp.tool()
    def echo(ctx: Context) -> str:
        started = ctx.lifespan_context.get("started_at")
        return f"started: {started is not None}"

    async with Client(mcp) as client:
        result = await client.call_tool("echo", {})
        # If lifespan ran, started_at should be present
        assert "started: True" in str(result)
