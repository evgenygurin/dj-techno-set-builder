"""DJ Workflow MCP server — high-level tools for DJ set building."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources
from app.mcp.workflows.analysis_tools import register_analysis_tools
from app.mcp.workflows.curation_tools import register_curation_tools
from app.mcp.workflows.discovery_tools import register_discovery_tools
from app.mcp.workflows.export_tools import register_export_tools
from app.mcp.workflows.import_tools import register_import_tools
from app.mcp.workflows.setbuilder_tools import register_setbuilder_tools
from app.mcp.workflows.sync_tools import register_sync_tools


def _register_visibility_tools(mcp: FastMCP) -> None:
    """Register admin/visibility-control tools on the MCP server."""

    @mcp.tool(tags={"admin"})
    async def activate_heavy_mode(ctx: Context) -> str:
        """Enable heavy analysis tools (full audio feature extraction).

        Call this to unlock resource-intensive tools that are hidden
        by default to prevent accidental long-running operations.
        """
        await ctx.enable_components(tags={"heavy"})
        return "Heavy analysis tools are now available."


def create_workflow_mcp() -> FastMCP:
    """Create the DJ Workflows MCP server with all tools registered."""
    mcp = FastMCP("DJ Workflows")
    register_analysis_tools(mcp)
    register_import_tools(mcp)
    register_discovery_tools(mcp)
    register_setbuilder_tools(mcp)
    register_export_tools(mcp)
    register_curation_tools(mcp)
    register_sync_tools(mcp)
    register_prompts(mcp)
    register_resources(mcp)
    _register_visibility_tools(mcp)

    # Hide heavy-tagged tools by default; activate via activate_heavy_mode
    mcp.disable(tags={"heavy"})

    return mcp
