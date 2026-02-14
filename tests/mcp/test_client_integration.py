"""In-memory Client integration tests for MCP tools.

Uses Client(server) for in-memory testing without network overhead.
Follows FastMCP testing pattern: server in fixture, Client in test body.

These tests go beyond metadata checks — they actually invoke tools
via the MCP Client protocol, verifying DI injection, Context handling,
and structured output serialization.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

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
    """Client sees all 12 DJ workflow tools + activate_heavy_mode."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        expected = {
            "get_playlist_status",
            "get_track_details",
            "import_playlist",
            "import_tracks",
            "find_similar_tracks",
            "search_by_criteria",
            "build_set",
            "score_transitions",
            "adjust_set",
            "export_set_m3u",
            "export_set_json",
            "activate_heavy_mode",
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
# Import tool invocations (stubs — no DB needed)
# ---------------------------------------------------------------------------


async def test_import_playlist_yandex_stub(workflow_mcp: FastMCP):
    """import_playlist returns zero-count ImportResult for supported source."""
    async with Client(workflow_mcp) as client:
        result = await client.call_tool(
            "import_playlist",
            {"source": "yandex", "playlist_id": "123"},
        )
        assert not result.is_error
        # Structured output: ImportResult with all-zero counts
        assert result.data.imported_count == 0
        assert result.data.skipped_count == 0
        assert result.data.enriched_count == 0


async def test_import_playlist_unsupported_source_raises(workflow_mcp: FastMCP):
    """import_playlist raises ToolError for unsupported source."""
    async with Client(workflow_mcp) as client:
        with pytest.raises(ToolError, match="Unsupported source 'spotify'"):
            await client.call_tool(
                "import_playlist",
                {"source": "spotify", "playlist_id": "123"},
            )


async def test_import_tracks_stub(workflow_mcp: FastMCP):
    """import_tracks returns skipped_count matching input length."""
    async with Client(workflow_mcp) as client:
        result = await client.call_tool(
            "import_tracks",
            {"track_ids": [100, 200, 300]},
        )
        assert not result.is_error
        assert result.data.imported_count == 0
        assert result.data.skipped_count == 3


async def test_import_tracks_empty_raises(workflow_mcp: FastMCP):
    """import_tracks raises ToolError for empty track list."""
    async with Client(workflow_mcp) as client:
        with pytest.raises(ToolError, match="track_ids must not be empty"):
            await client.call_tool(
                "import_tracks",
                {"track_ids": []},
            )


# ---------------------------------------------------------------------------
# Gateway namespaced tool invocations
# ---------------------------------------------------------------------------


async def test_gateway_import_playlist_via_namespace(gateway_mcp: FastMCP):
    """Gateway-namespaced dj_import_playlist works end-to-end."""
    async with Client(gateway_mcp) as client:
        result = await client.call_tool(
            "dj_import_playlist",
            {"source": "yandex", "playlist_id": "456"},
        )
        assert not result.is_error
        assert result.data.imported_count == 0


async def test_gateway_import_tracks_via_namespace(gateway_mcp: FastMCP):
    """Gateway-namespaced dj_import_tracks works end-to-end."""
    async with Client(gateway_mcp) as client:
        result = await client.call_tool(
            "dj_import_tracks",
            {"track_ids": [1, 2]},
        )
        assert not result.is_error
        assert result.data.skipped_count == 2
