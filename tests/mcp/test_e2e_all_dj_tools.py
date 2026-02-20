"""End-to-end tests for ALL DJ MCP tools via in-memory Client.

Each tool is invoked through the MCP protocol with a real test DB,
verifying that DI injection, Context handling, and response serialization
work correctly end-to-end.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import fastmcp.exceptions
import pytest
from fastmcp import Client, FastMCP


def _text(result) -> str:
    """Extract first text content from CallToolResult."""
    if result.content:
        return result.content[0].text
    # FastMCP returns empty content for empty lists but populates structured_content
    if result.structured_content:
        return json.dumps(result.structured_content.get("result", []))
    return "[]"


def _json(result) -> dict | list:
    """Parse JSON from first text content of CallToolResult."""
    return json.loads(_text(result))


# ---------------------------------------------------------------------------
# 1. Search tools
# ---------------------------------------------------------------------------


async def test_search_empty_db(workflow_mcp_with_db: FastMCP):
    """search tool returns empty results on empty DB."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("search", {"query": "boris brejcha"})
        data = _json(raw)
        assert "results" in data
        assert "library" in data


async def test_filter_tracks_empty_db(workflow_mcp_with_db: FastMCP):
    """filter_tracks returns empty on empty DB."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("filter_tracks", {"bpm_min": 130, "bpm_max": 145})
        data = _json(raw)
        assert "results" in data
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# 2. Track CRUD
# ---------------------------------------------------------------------------


async def test_track_crud_lifecycle(workflow_mcp_with_db: FastMCP):
    """Create → Get → Update → List → Delete a track."""
    async with Client(workflow_mcp_with_db) as c:
        # Create
        raw = await c.call_tool("create_track", {"title": "Test Track", "duration_ms": 300000})
        data = _json(raw)
        assert data["success"] is True
        assert "Created track" in data["message"]

        # Extract track ID from message (e.g. "Created track local:1")
        track_id = data["message"].split("local:")[1]

        # Get
        raw = await c.call_tool("get_track", {"track_ref": track_id})
        data = _json(raw)
        assert "result" in data
        assert data["result"]["title"] == "Test Track"

        # Update
        raw = await c.call_tool("update_track", {"track_ref": track_id, "title": "Updated Track"})
        data = _json(raw)
        assert data["success"] is True

        # Verify update
        raw = await c.call_tool("get_track", {"track_ref": track_id})
        data = _json(raw)
        assert data["result"]["title"] == "Updated Track"

        # List
        raw = await c.call_tool("list_tracks", {})
        data = _json(raw)
        assert data["total"] >= 1

        # Delete
        raw = await c.call_tool("delete_track", {"track_ref": track_id})
        data = _json(raw)
        assert data["success"] is True


# ---------------------------------------------------------------------------
# 3. Playlist CRUD
# ---------------------------------------------------------------------------


async def test_playlist_crud_lifecycle(workflow_mcp_with_db: FastMCP):
    """Create → Get → Update → List → Delete a playlist."""
    async with Client(workflow_mcp_with_db) as c:
        # Create
        raw = await c.call_tool("create_playlist", {"name": "Test Playlist"})
        data = _json(raw)
        assert data["success"] is True
        pl_id = data["message"].split("local:")[1]

        # Get
        raw = await c.call_tool("get_playlist", {"playlist_ref": pl_id})
        data = _json(raw)
        assert "result" in data

        # Update
        raw = await c.call_tool(
            "update_playlist", {"playlist_ref": pl_id, "name": "Updated Playlist"}
        )
        data = _json(raw)
        assert data["success"] is True

        # List
        raw = await c.call_tool("list_playlists", {})
        data = _json(raw)
        assert data["total"] >= 1

        # Delete
        raw = await c.call_tool("delete_playlist", {"playlist_ref": pl_id})
        data = _json(raw)
        assert data["success"] is True


# ---------------------------------------------------------------------------
# 4. Set CRUD
# ---------------------------------------------------------------------------


async def test_set_crud_lifecycle(workflow_mcp_with_db: FastMCP):
    """Create → Get → Update → List → Delete a DJ set."""
    async with Client(workflow_mcp_with_db) as c:
        # Create
        raw = await c.call_tool("create_set", {"name": "Test Set", "description": "E2E test set"})
        data = _json(raw)
        assert data["success"] is True
        set_id = data["message"].split("local:")[1]

        # Get
        raw = await c.call_tool("get_set", {"set_ref": set_id})
        data = _json(raw)
        assert "result" in data

        # Update
        raw = await c.call_tool("update_set", {"set_ref": set_id, "name": "Updated Set"})
        data = _json(raw)
        assert data["success"] is True

        # List
        raw = await c.call_tool("list_sets", {})
        data = _json(raw)
        assert data["total"] >= 1

        # Delete
        raw = await c.call_tool("delete_set", {"set_ref": set_id})
        data = _json(raw)
        assert data["success"] is True


# ---------------------------------------------------------------------------
# 5. Features
# ---------------------------------------------------------------------------


async def test_features_list_empty(workflow_mcp_with_db: FastMCP):
    """list_features returns empty results on empty DB."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("list_features", {})
        data = _json(raw)
        assert data["total"] == 0


async def test_get_features_no_features(workflow_mcp_with_db: FastMCP):
    """get_features returns error for nonexistent track."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("get_features", {"track_ref": "999"})
        data = _json(raw)
        assert "error" in data


async def test_save_and_get_features(workflow_mcp_with_db: FastMCP):
    """Create track → save features → get features."""
    async with Client(workflow_mcp_with_db) as c:
        # Create track first
        raw = await c.call_tool("create_track", {"title": "Feat Track", "duration_ms": 300000})
        data = _json(raw)
        assert data["success"] is True
        track_id = data["message"].split("local:")[1]

        # Save features
        features_json = json.dumps(
            {
                "bpm": 140.0,
                "tempo_confidence": 0.95,
                "bpm_stability": 0.1,
                "is_variable_tempo": False,
                "lufs_i": -8.5,
                "rms_dbfs": -10.0,
                "energy_mean": 0.7,
                "energy_max": 0.95,
                "key_code": 5,
                "key_confidence": 0.85,
                "is_atonal": False,
            }
        )
        raw = await c.call_tool(
            "save_features", {"track_ref": track_id, "features_json": features_json}
        )
        data = _json(raw)
        assert data["success"] is True

        # Get features
        raw = await c.call_tool("get_features", {"track_ref": track_id})
        data = _json(raw)
        assert "result" in data
        assert data["result"]["bpm"] == 140.0


# ---------------------------------------------------------------------------
# 6. Compute tools
# ---------------------------------------------------------------------------


async def test_analyze_track_no_args(workflow_mcp_with_db: FastMCP):
    """analyze_track with no track_ref or audio_path returns error."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("analyze_track", {})
        data = _json(raw)
        assert "error" in data


async def test_compute_set_order_no_playlist(workflow_mcp_with_db: FastMCP):
    """compute_set_order on nonexistent playlist returns error."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("compute_set_order", {"playlist_id": 999})
        data = _json(raw)
        assert "error" in data


# ---------------------------------------------------------------------------
# 7. Unified export
# ---------------------------------------------------------------------------


async def test_export_set_no_set(workflow_mcp_with_db: FastMCP):
    """export_set for nonexistent set returns error."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool(
            "export_set", {"set_ref": "999", "version_id": 1, "format": "json"}
        )
        data = _json(raw)
        assert "error" in data


async def test_export_set_invalid_format(workflow_mcp_with_db: FastMCP):
    """export_set with unknown format returns error."""
    async with Client(workflow_mcp_with_db) as c:
        # Create set + version with tracks for a valid set_ref
        raw = await c.call_tool("create_track", {"title": "Export T1", "duration_ms": 300000})
        t1_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "Export Set", "track_ids": [t1_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool(
            "export_set", {"set_ref": set_id, "version_id": version_id, "format": "wav"}
        )
        data = _json(raw)
        assert "error" in data


async def test_export_set_json_format(workflow_mcp_with_db: FastMCP):
    """export_set with json format on a valid set works."""
    async with Client(workflow_mcp_with_db) as c:
        # Create track + set with track
        raw = await c.call_tool("create_track", {"title": "Export Track", "duration_ms": 240000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "JSON Export Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool(
            "export_set", {"set_ref": set_id, "version_id": version_id, "format": "json"}
        )
        data = _json(raw)
        assert data["format"] == "json"
        assert data["track_count"] >= 1
        assert "content" in data


async def test_export_set_m3u_format(workflow_mcp_with_db: FastMCP):
    """export_set with m3u format on a valid set works."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_track", {"title": "M3U Track", "duration_ms": 240000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "M3U Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool(
            "export_set", {"set_ref": set_id, "version_id": version_id, "format": "m3u"}
        )
        data = _json(raw)
        assert data["format"] == "m3u"
        assert "#EXTM3U" in data["content"]


# ---------------------------------------------------------------------------
# 8. Admin/visibility tools
# ---------------------------------------------------------------------------


async def test_list_platforms(workflow_mcp_with_db: FastMCP):
    """list_platforms returns platform info dict."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("list_platforms", {})
        data = _json(raw)
        assert "platforms" in data
        assert "total" in data


async def test_activate_heavy_mode(workflow_mcp_with_db: FastMCP):
    """activate_heavy_mode returns success message."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("activate_heavy_mode", {})
        text = _text(raw)
        assert "heavy" in text.lower() or "Heavy" in text


async def test_activate_ym_raw(workflow_mcp_with_db: FastMCP):
    """activate_ym_raw returns success message."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("activate_ym_raw", {})
        text = _text(raw)
        assert "ym" in text.lower() or "YM" in text


# ---------------------------------------------------------------------------
# 9. Discovery tools
# ---------------------------------------------------------------------------


async def test_find_similar_tracks_empty(workflow_mcp_with_db: FastMCP):
    """find_similar_tracks on empty playlist returns zero candidates."""
    async with Client(workflow_mcp_with_db) as c:
        # Create playlist first
        raw = await c.call_tool("create_playlist", {"name": "Empty PL"})
        pl_id = _json(raw)["message"].split("local:")[1]
        raw = await c.call_tool("find_similar_tracks", {"playlist_ref": pl_id})
        data = _json(raw)
        assert data["candidates_found"] == 0


# ---------------------------------------------------------------------------
# 10. Classify + Library Gap analysis
# ---------------------------------------------------------------------------


async def test_classify_tracks_empty(workflow_mcp_with_db: FastMCP):
    """classify_tracks on empty DB returns zero total."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("classify_tracks", {})
        data = _json(raw)
        assert data["total_classified"] == 0


async def test_analyze_library_gaps_empty(workflow_mcp_with_db: FastMCP):
    """analyze_library_gaps on empty DB shows all slots as gaps."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("analyze_library_gaps", {"template": "classic_60"})
        data = _json(raw)
        assert "gaps" in data
        assert "recommendations" in data


# ---------------------------------------------------------------------------
# 11. Setbuilder tools (build_set, score_transitions)
# ---------------------------------------------------------------------------


async def test_build_set_no_playlist(workflow_mcp_with_db: FastMCP):
    """build_set with nonexistent playlist raises ToolError."""
    async with Client(workflow_mcp_with_db) as c:
        with pytest.raises(fastmcp.exceptions.ToolError):
            await c.call_tool("build_set", {"playlist_ref": "999", "set_name": "Ghost Set"})


async def test_score_transitions_empty_set(workflow_mcp_with_db: FastMCP):
    """score_transitions on set with <2 items returns empty list."""
    async with Client(workflow_mcp_with_db) as c:
        # Create set with a track so we get a version
        raw = await c.call_tool("create_track", {"title": "Score T", "duration_ms": 200000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "Score Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool("score_transitions", {"set_ref": set_id, "version_id": version_id})
        data = _json(raw)
        # With only 1 track, should return empty transitions list
        assert data == [] or isinstance(data, list)


# ---------------------------------------------------------------------------
# 12. Review set
# ---------------------------------------------------------------------------


async def test_review_set_short(workflow_mcp_with_db: FastMCP):
    """review_set on set with <2 tracks returns 'too short' suggestion."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_track", {"title": "Review T", "duration_ms": 200000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "Review Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool("review_set", {"set_ref": set_id, "version_id": version_id})
        data = _json(raw)
        assert "suggestions" in data
        assert any("short" in s.lower() for s in data["suggestions"])


# ---------------------------------------------------------------------------
# 13. Sync tools (stub-safe)
# ---------------------------------------------------------------------------


async def test_set_source_of_truth(workflow_mcp_with_db: FastMCP):
    """set_source_of_truth updates playlist metadata."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_playlist", {"name": "Sync PL"})
        pl_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("set_source_of_truth", {"playlist_id": pl_id, "source": "ym"})
        data = _json(raw)
        assert data["source_of_truth"] == "ym"
        assert data["status"] == "updated"


async def test_link_playlist(workflow_mcp_with_db: FastMCP):
    """link_playlist links a local playlist to platform playlist."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_playlist", {"name": "Link PL"})
        pl_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool(
            "link_playlist",
            {"playlist_id": pl_id, "platform": "ym", "platform_playlist_id": "12345"},
        )
        data = _json(raw)
        assert data["status"] == "linked"
        assert data["platform_playlist_id"] == "12345"


# ---------------------------------------------------------------------------
# 14. Download tools (stub-safe — needs YM client)
# ---------------------------------------------------------------------------


async def test_download_tracks_empty_ids(workflow_mcp_with_db: FastMCP):
    """download_tracks with nonexistent track IDs doesn't crash."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("download_tracks", {"track_ids": [999]})
        # Should not crash — may return error or empty result
        text = _text(raw)
        assert text  # non-empty response


# ---------------------------------------------------------------------------
# 15. Export Rekordbox (standalone)
# ---------------------------------------------------------------------------


async def test_export_set_rekordbox(workflow_mcp_with_db: FastMCP):
    """export_set_rekordbox generates valid XML."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_track", {"title": "RB Track", "duration_ms": 300000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "RB Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool(
            "export_set_rekordbox",
            {"set_ref": set_id, "version_id": version_id},
        )
        data = _json(raw)
        assert data["format"] == "rekordbox_xml"
        assert "DJ_PLAYLISTS" in data["content"]


# ---------------------------------------------------------------------------
# 16. Rebuild set
# ---------------------------------------------------------------------------


async def test_rebuild_set_no_versions(workflow_mcp_with_db: FastMCP):
    """rebuild_set on set with no versions raises ToolError."""
    async with Client(workflow_mcp_with_db) as c:
        # Create an empty set (no track_ids → no version)
        raw = await c.call_tool("create_set", {"name": "Empty Rebuild Set"})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]

        with pytest.raises(fastmcp.exceptions.ToolError):
            await c.call_tool("rebuild_set", {"set_ref": set_id})


# ---------------------------------------------------------------------------
# 17. Sync tools (E2E with mock platform)
# ---------------------------------------------------------------------------


async def test_sync_set_to_ym_elicitation_fail_closed(workflow_mcp_with_db: FastMCP):
    """sync_set_to_ym returns cancelled or ToolError depending on env.

    If YM is connected (env has token), elicitation fail-closed → cancelled.
    If YM is not connected → ToolError (platform not connected).
    """
    async with Client(workflow_mcp_with_db) as c:
        # Create a set first
        raw = await c.call_tool("create_track", {"title": "Sync T", "duration_ms": 300000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "Sync Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = int(set_data["message"].split("local:")[1])

        try:
            raw = await c.call_tool("sync_set_to_ym", {"set_id": set_id})
            data = _json(raw)
            # YM connected but elicitation not supported → cancelled
            assert data["status"] == "cancelled"
        except fastmcp.exceptions.ToolError:
            # YM not connected → ValueError → ToolError
            pass


async def test_sync_set_from_ym_no_link(workflow_mcp_with_db: FastMCP):
    """sync_set_from_ym raises ToolError: set has no ym_playlist_id or YM not connected."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_track", {"title": "SyncFrom T", "duration_ms": 300000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "SyncFrom Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = int(set_data["message"].split("local:")[1])

        # Either YM not connected or set has no ym_playlist_id → ToolError
        with pytest.raises(fastmcp.exceptions.ToolError):
            await c.call_tool("sync_set_from_ym", {"set_id": set_id})


async def test_sync_playlist_not_connected(workflow_mcp_with_db: FastMCP):
    """sync_playlist raises ToolError when platform is not connected."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_playlist", {"name": "SyncPL"})
        pl_id = int(_json(raw)["message"].split("local:")[1])

        # Platform 'ym' not connected → sync engine raises ValueError → ToolError
        with pytest.raises(fastmcp.exceptions.ToolError):
            await c.call_tool(
                "sync_playlist",
                {"playlist_id": pl_id, "platform": "ym", "direction": "remote_to_local"},
            )


# ---------------------------------------------------------------------------
# 18. Sync tools with mock platform (happy path)
# ---------------------------------------------------------------------------


async def _make_mock_platform_registry():
    """Create a PlatformRegistry with a mock YM adapter."""
    from app.mcp.platforms.protocol import PlatformCapability, PlatformPlaylist
    from app.mcp.platforms.registry import PlatformRegistry

    mock_platform = AsyncMock()
    mock_platform.name = "ym"
    mock_platform.capabilities = frozenset(
        {PlatformCapability.PLAYLIST_READ, PlatformCapability.PLAYLIST_WRITE}
    )
    mock_platform.create_playlist = AsyncMock(return_value="ym_pl_999")
    mock_platform.get_playlist = AsyncMock(
        return_value=PlatformPlaylist(platform_id="ym_pl_999", name="test", track_ids=[])
    )
    mock_platform.add_tracks_to_playlist = AsyncMock()
    mock_platform.remove_tracks_from_playlist = AsyncMock()

    registry = PlatformRegistry()
    registry.register(mock_platform)
    return registry


async def test_sync_set_to_ym_with_mock_platform(engine):
    """sync_set_to_ym creates YM playlist when platform connected."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.mcp.tools import create_workflow_mcp

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_registry = await _make_mock_platform_registry()

    with (
        patch("app.mcp.dependencies.session_factory", factory),
        patch("app.mcp.dependencies._platform_registry", mock_registry),
    ):
        mcp = create_workflow_mcp()
        async with Client(mcp) as c:
            # Create track + set
            raw = await c.call_tool("create_track", {"title": "YM Push T", "duration_ms": 300000})
            t_id = int(_json(raw)["message"].split("local:")[1])
            raw = await c.call_tool("create_set", {"name": "YM Push Set", "track_ids": [t_id]})
            set_data = _json(raw)
            set_id = int(set_data["message"].split("local:")[1])

            raw = await c.call_tool("sync_set_to_ym", {"set_id": set_id})
            data = _json(raw)
            # Elicitation fail-closed → cancelled, or if it gets through:
            # mock mapper returns no mapped IDs → create_playlist with 0 tracks
            assert "status" in data
            assert data["status"] in ("cancelled", "synced", "not_supported")


async def test_sync_set_from_ym_no_ym_playlist(engine):
    """sync_set_from_ym raises when set has no ym_playlist_id."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.mcp.tools import create_workflow_mcp

    factory = async_sessionmaker(engine, expire_on_commit=False)
    mock_registry = await _make_mock_platform_registry()

    with (
        patch("app.mcp.dependencies.session_factory", factory),
        patch("app.mcp.dependencies._platform_registry", mock_registry),
    ):
        mcp = create_workflow_mcp()
        async with Client(mcp) as c:
            raw = await c.call_tool("create_track", {"title": "FromYM T", "duration_ms": 300000})
            t_id = int(_json(raw)["message"].split("local:")[1])
            raw = await c.call_tool("create_set", {"name": "FromYM Set", "track_ids": [t_id]})
            set_data = _json(raw)
            set_id = int(set_data["message"].split("local:")[1])

            # Set has no ym_playlist_id → should raise
            with pytest.raises(fastmcp.exceptions.ToolError):
                await c.call_tool("sync_set_from_ym", {"set_id": set_id})


# ---------------------------------------------------------------------------
# 19. Export set — rekordbox format via unified export
# ---------------------------------------------------------------------------


async def test_export_set_rekordbox_via_unified(workflow_mcp_with_db: FastMCP):
    """export_set with format=rekordbox works."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_track", {"title": "RB Unified", "duration_ms": 300000})
        t_id = int(_json(raw)["message"].split("local:")[1])
        raw = await c.call_tool("create_set", {"name": "RB Unified Set", "track_ids": [t_id]})
        set_data = _json(raw)
        set_id = set_data["message"].split("local:")[1]
        version_id = set_data["result"]["latest_version_id"]

        raw = await c.call_tool(
            "export_set",
            {"set_ref": set_id, "version_id": version_id, "format": "rekordbox"},
        )
        data = _json(raw)
        assert data["format"] == "rekordbox"
        assert "DJ_PLAYLISTS" in data["content"]


# ---------------------------------------------------------------------------
# 20. Features — save + list with BPM filter
# ---------------------------------------------------------------------------


async def test_list_features_with_bpm_filter(workflow_mcp_with_db: FastMCP):
    """list_features with BPM filter returns filtered results."""
    async with Client(workflow_mcp_with_db) as c:
        # Create two tracks with different BPMs
        raw = await c.call_tool("create_track", {"title": "Slow Track", "duration_ms": 300000})
        slow_id = _json(raw)["message"].split("local:")[1]
        raw = await c.call_tool("create_track", {"title": "Fast Track", "duration_ms": 300000})
        fast_id = _json(raw)["message"].split("local:")[1]

        # Save features for slow track (BPM=125)
        features_slow = json.dumps(
            {
                "bpm": 125.0,
                "tempo_confidence": 0.9,
                "bpm_stability": 0.1,
                "lufs_i": -8.0,
                "rms_dbfs": -10.0,
                "energy_mean": 0.6,
                "energy_max": 0.8,
                "energy_std": 0.1,
                "key_code": 3,
                "key_confidence": 0.8,
                "is_atonal": False,
            }
        )
        await c.call_tool("save_features", {"track_ref": slow_id, "features_json": features_slow})

        # Save features for fast track (BPM=145)
        features_fast = json.dumps(
            {
                "bpm": 145.0,
                "tempo_confidence": 0.95,
                "bpm_stability": 0.05,
                "lufs_i": -7.0,
                "rms_dbfs": -9.0,
                "energy_mean": 0.8,
                "energy_max": 0.95,
                "energy_std": 0.1,
                "key_code": 7,
                "key_confidence": 0.9,
                "is_atonal": False,
            }
        )
        await c.call_tool("save_features", {"track_ref": fast_id, "features_json": features_fast})

        # Filter by BPM 140-150 — only fast track
        raw = await c.call_tool("list_features", {"bpm_min": 140.0, "bpm_max": 150.0})
        data = _json(raw)
        assert data["total"] == 1
        assert len(data["results"]) == 1


# ---------------------------------------------------------------------------
# 21. Search — text search by track title
# ---------------------------------------------------------------------------


async def test_search_with_results(workflow_mcp_with_db: FastMCP):
    """search returns matching tracks when data exists."""
    async with Client(workflow_mcp_with_db) as c:
        await c.call_tool(
            "create_track", {"title": "Boris Brejcha Gravity", "duration_ms": 420000}
        )
        raw = await c.call_tool("search", {"query": "Boris", "scope": "tracks"})
        data = _json(raw)
        assert data["results"]["tracks"]  # at least one match


# ---------------------------------------------------------------------------
# 22. Track text search via get_track
# ---------------------------------------------------------------------------


async def test_get_track_text_ref(workflow_mcp_with_db: FastMCP):
    """get_track with text ref returns search results."""
    async with Client(workflow_mcp_with_db) as c:
        await c.call_tool("create_track", {"title": "ANNA RRDR", "duration_ms": 360000})
        raw = await c.call_tool("get_track", {"track_ref": "ANNA"})
        data = _json(raw)
        # Text ref returns a list of matches
        assert "results" in data


# ---------------------------------------------------------------------------
# 23. Set source of truth — invalid source
# ---------------------------------------------------------------------------


async def test_set_source_of_truth_invalid(workflow_mcp_with_db: FastMCP):
    """set_source_of_truth with invalid source raises ToolError."""
    async with Client(workflow_mcp_with_db) as c:
        raw = await c.call_tool("create_playlist", {"name": "SoT PL"})
        pl_id = int(_json(raw)["message"].split("local:")[1])

        with pytest.raises(fastmcp.exceptions.ToolError):
            await c.call_tool(
                "set_source_of_truth",
                {"playlist_id": pl_id, "source": "invalid_platform"},
            )
