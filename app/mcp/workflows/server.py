"""DJ Workflow MCP server — high-level tools for DJ set building."""

from __future__ import annotations

from fastmcp import FastMCP

from app.mcp.workflows.analysis_tools import register_analysis_tools
from app.mcp.workflows.discovery_tools import register_discovery_tools
from app.mcp.workflows.export_tools import register_export_tools
from app.mcp.workflows.import_tools import register_import_tools
from app.mcp.workflows.setbuilder_tools import register_setbuilder_tools


def create_workflow_mcp() -> FastMCP:
    """Create the DJ Workflows MCP server with all tools registered."""
    mcp = FastMCP("DJ Workflows")
    register_analysis_tools(mcp)
    register_import_tools(mcp)
    register_discovery_tools(mcp)
    register_setbuilder_tools(mcp)
    register_export_tools(mcp)
    return mcp
