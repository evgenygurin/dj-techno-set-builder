"""MCP providers — domain-grouped tool registration.

Replaces the flat app/mcp/tools/server.py with provider-based composition.
Each provider groups related tools by domain (catalog, analysis, setbuilder, etc.).
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources

from app.mcp.providers.analysis import register_analysis_tools
from app.mcp.providers.catalog import register_catalog_tools
from app.mcp.providers.discovery import register_discovery_tools
from app.mcp.providers.export import register_export_tools
from app.mcp.providers.setbuilder import register_setbuilder_tools
from app.mcp.providers.sync import register_sync_tools


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
    """Create the DJ Workflows MCP server with all tools registered.

    Tools are organized into 6 domain providers:
    - catalog: CRUD for tracks, playlists, sets, features
    - analysis: audio analysis, classification, library gaps
    - setbuilder: build, rebuild, score, deliver
    - discovery: search, filter, discover, expand, download
    - export: M3U, JSON, Rekordbox export
    - sync: platform sync, link, source-of-truth
    """
    mcp = FastMCP("DJ Workflows")

    # Domain providers
    register_catalog_tools(mcp)
    register_analysis_tools(mcp)
    register_setbuilder_tools(mcp)
    register_discovery_tools(mcp)
    register_export_tools(mcp)
    register_sync_tools(mcp)

    # Prompts, resources, admin
    register_prompts(mcp)
    register_resources(mcp)
    _register_visibility_tools(mcp)

    # Hide heavy-tagged tools by default
    mcp.disable(tags={"heavy"})

    return mcp
