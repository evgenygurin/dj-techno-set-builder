"""Tests for curation discovery MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP


async def test_discover_candidates_registered(workflow_mcp: FastMCP) -> None:
    """discover_candidates tool is registered on the workflow server."""
    tools = await workflow_mcp.list_tools()
    names = {t.name for t in tools}
    assert "discover_candidates" in names


async def test_discover_candidates_tags(workflow_mcp: FastMCP) -> None:
    """discover_candidates has curation and yandex tags."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "discover_candidates")
    assert tool.tags is not None
    assert {"curation", "yandex"} <= set(tool.tags)


async def test_discover_candidates_params(workflow_mcp: FastMCP) -> None:
    """discover_candidates exposes expected input parameters."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "discover_candidates")
    props = set(tool.parameters.get("properties", {}).keys())
    assert "seed_track_id" in props
    assert "batch_size" in props
    assert "exclude_track_ids" in props


async def test_discover_candidates_required_params(workflow_mcp: FastMCP) -> None:
    """seed_track_id is required, batch_size is optional."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "discover_candidates")
    required = set(tool.parameters.get("required", []))
    assert "seed_track_id" in required
    assert "batch_size" not in required


async def test_discover_candidates_gateway_namespaced(gateway_mcp: FastMCP) -> None:
    """discover_candidates is namespaced as dj_discover_candidates in gateway."""
    tools = await gateway_mcp.list_tools()
    names = {t.name for t in tools}
    assert "dj_discover_candidates" in names
