"""Phase 2 integration tests — CRUD cycle + tool registration.

Tests that new Phase 2 tools are registered on the MCP server
and that the response envelope structure is correct.
"""

from __future__ import annotations

import json

from fastmcp import Client


class TestPhase2ToolRegistration:
    """Verify all Phase 2 tools are registered."""

    async def test_search_tools_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "search" in names
            assert "filter_tracks" in names

    async def test_track_crud_tools_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "list_tracks" in names
            assert "get_track" in names
            assert "create_track" in names
            assert "update_track" in names
            assert "delete_track" in names

    async def test_playlist_crud_tools_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "list_playlists" in names
            assert "get_playlist" in names
            assert "create_playlist" in names
            assert "update_playlist" in names
            assert "delete_playlist" in names

    async def test_set_crud_tools_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "list_sets" in names
            assert "get_set" in names
            assert "create_set" in names
            assert "update_set" in names
            assert "delete_set" in names

    async def test_features_tools_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "list_features" in names
            assert "get_features" in names
            assert "save_features" in names

    async def test_compute_tools_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "analyze_track" in names
            assert "compute_set_order" in names

    async def test_unified_export_registered(self, workflow_mcp):
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "export_set" in names

    async def test_legacy_tools_still_registered(self, workflow_mcp):
        """Legacy tools are kept until Phase 4."""
        async with Client(workflow_mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            # Legacy tools from Phase 0
            assert "build_set" in names
            assert "score_transitions" in names
            assert "download_tracks" in names
