"""Tests for filter_tracks extended audio parameters."""

from __future__ import annotations

from fastmcp import Client


async def test_filter_tracks_extended_params(workflow_mcp):
    """filter_tracks exposes kick, hp_ratio, centroid, camelot_keys params."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "filter_tracks")
        props = set(tool.inputSchema.get("properties", {}).keys())
        assert "kick_min" in props
        assert "kick_max" in props
        assert "hp_ratio_min" in props
        assert "hp_ratio_max" in props
        assert "centroid_min" in props
        assert "centroid_max" in props
        assert "camelot_keys" in props


async def test_filter_tracks_camelot_keys_is_array(workflow_mcp):
    """camelot_keys parameter accepts an array of strings."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "filter_tracks")
        camelot_prop = tool.inputSchema["properties"]["camelot_keys"]
        # anyOf with array type and null
        type_options = camelot_prop.get("anyOf", [])
        array_type = next((t for t in type_options if t.get("type") == "array"), None)
        assert array_type is not None, "camelot_keys should accept array type"
        assert array_type["items"]["type"] == "string"


async def test_filter_tracks_keeps_existing_params(workflow_mcp):
    """Existing bpm/key/energy params still present after extension."""
    async with Client(workflow_mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "filter_tracks")
        props = set(tool.inputSchema.get("properties", {}).keys())
        assert "bpm_min" in props
        assert "bpm_max" in props
        assert "key_code_min" in props
        assert "key_code_max" in props
        assert "energy_min" in props
        assert "energy_max" in props
