"""DJ Workflow MCP server — high-level tools for DJ set building.

Phase 2: CRUD tools + compute/persist split + unified export.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources

# Phase 2: CRUD tools
from app.mcp.workflows.compute_tools import register_compute_tools
from app.mcp.workflows.curation_tools import register_curation_tools
from app.mcp.workflows.discovery_tools import register_discovery_tools
from app.mcp.workflows.download_tools import register_download_tools
from app.mcp.workflows.export_tools import register_export_tools
from app.mcp.workflows.features_tools import register_features_tools
from app.mcp.workflows.playlist_tools import register_playlist_tools

# Phase 1: Search + filter
from app.mcp.workflows.search_tools import register_search_tools
from app.mcp.workflows.set_tools import register_set_tools
from app.mcp.workflows.setbuilder_tools import register_setbuilder_tools
from app.mcp.workflows.sync_tools import register_sync_tools
from app.mcp.workflows.track_tools import register_track_tools
from app.mcp.workflows.unified_export_tools import register_unified_export_tools


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

    @mcp.tool(tags={"admin"})
    async def activate_ym_raw(ctx: Context) -> str:
        """Enable raw Yandex Music API tools.

        Unlocks the full YM API namespace for advanced queries
        not covered by the DJ workflow tools.
        """
        await ctx.enable_components(tags={"ym_raw"})
        return "Raw YM API tools are now available."

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"admin"},
    )
    async def list_platforms() -> dict[str, object]:
        """List all configured music platforms and their capabilities.

        Shows connected status and available capabilities for each platform.
        """
        from app.mcp.dependencies import get_platform_registry

        registry = get_platform_registry()
        platforms = []
        for name in registry.list_connected():
            adapter = registry.get(name)
            platforms.append(
                {
                    "name": name,
                    "capabilities": [c.name for c in adapter.capabilities],
                }
            )
        return {
            "platforms": platforms,
            "total": len(platforms),
        }


def create_workflow_mcp() -> FastMCP:
    """Create the DJ Workflows MCP server with all tools registered."""
    mcp = FastMCP("DJ Workflows")

    # === Phase 1: Search ===
    register_search_tools(mcp)

    # === Phase 2: CRUD + Compute ===
    register_track_tools(mcp)
    register_playlist_tools(mcp)
    register_set_tools(mcp)
    register_features_tools(mcp)
    register_compute_tools(mcp)
    register_unified_export_tools(mcp)

    # === Download ===
    register_download_tools(mcp)
    register_discovery_tools(mcp)
    register_setbuilder_tools(mcp)
    register_export_tools(mcp)
    register_curation_tools(mcp)
    register_sync_tools(mcp)

    # === Prompts & Resources ===
    register_prompts(mcp)
    register_resources(mcp)
    _register_visibility_tools(mcp)

    # Hide heavy-tagged tools by default; activate via activate_heavy_mode
    mcp.disable(tags={"heavy"})

    return mcp
