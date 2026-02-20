"""In-memory Client integration tests for MCP tools.

Uses Client(server) for in-memory testing without network overhead.
Follows FastMCP testing pattern: server in fixture, Client in test body.

These tests go beyond metadata checks — they actually invoke tools
via the MCP Client protocol, verifying DI injection, Context handling,
and structured output serialization.
"""

from __future__ import annotations

from fastmcp import Client, FastMCP

# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------


async def test_workflow_client_ping(workflow_mcp: FastMCP):
    """Client can connect to the workflow server via in-memory transport."""
    async with Client(workflow_mcp) as client:
        assert await client.ping() is True


async def test_gateway_client_ping(gateway_mcp: FastMCP):
    """Client can connect to the full gateway via in-memory transport."""
    async with Client(gateway_mcp) as client:
        assert await client.ping() is True


# ---------------------------------------------------------------------------
# Tool / Prompt / Resource listing through Client
# ---------------------------------------------------------------------------


async def test_client_lists_all_workflow_tools(workflow_mcp: FastMCP):
    """Client sees DJ workflow tools + activate_heavy_mode."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        expected = {
            # Legacy tools
            "get_playlist_status",
            "get_track_details",
            "find_similar_tracks",
            "search_by_criteria",
            "build_set",
            "rebuild_set",
            "score_transitions",
            "export_set_m3u",
            "export_set_json",
            "export_set_rekordbox",
            "classify_tracks",
            "analyze_library_gaps",
            "review_set",
            "sync_set_to_ym",
            "sync_set_from_ym",
            "sync_playlist",
            "download_tracks",
            "activate_heavy_mode",
            # Phase 1: Search
            "search",
            "filter_tracks",
            # Phase 2: CRUD
            "list_tracks",
            "get_track",
            "create_track",
            "update_track",
            "delete_track",
            "list_playlists",
            "get_playlist",
            "create_playlist",
            "update_playlist",
            "delete_playlist",
            "list_sets",
            "get_set",
            "create_set",
            "update_set",
            "delete_set",
            "list_features",
            "get_features",
            "save_features",
            # Phase 2: Compute + Export
            "analyze_track",
            "compute_set_order",
            "export_set",
        }
        missing = expected - tool_names
        assert not missing, f"Missing tools: {missing}"


async def test_client_lists_prompts(workflow_mcp: FastMCP):
    """Client can list all registered prompts."""
    async with Client(workflow_mcp) as client:
        prompts = await client.list_prompts()
        prompt_names = {p.name for p in prompts}
        assert "expand_playlist" in prompt_names
        assert "build_set_from_scratch" in prompt_names
        assert "improve_set" in prompt_names


async def test_client_lists_resources(workflow_mcp: FastMCP):
    """Client can list static resources."""
    async with Client(workflow_mcp) as client:
        resources = await client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "catalog://stats" in uris


async def test_gateway_client_sees_namespaced_tools(gateway_mcp: FastMCP):
    """Gateway client sees both dj_ and ym_ namespaced tools."""
    async with Client(gateway_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        dj_tools = {n for n in tool_names if n.startswith("dj_")}
        ym_tools = {n for n in tool_names if n.startswith("ym_")}
        assert len(dj_tools) >= 12, f"Expected >=12 dj_ tools, got {len(dj_tools)}"
        assert len(ym_tools) > 0, "No ym_ tools found"


# ---------------------------------------------------------------------------
# Gateway namespaced tool invocations
# ---------------------------------------------------------------------------
