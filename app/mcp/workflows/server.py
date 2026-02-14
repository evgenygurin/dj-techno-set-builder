"""DJ Workflow MCP server — high-level tools for DJ set building."""

from __future__ import annotations

from fastmcp import FastMCP

from app.mcp.workflows.analysis_tools import register_analysis_tools


def create_workflow_mcp() -> FastMCP:
    """Create the DJ Workflows MCP server with all tools registered."""
    mcp = FastMCP("DJ Workflows")
    register_analysis_tools(mcp)
    return mcp
