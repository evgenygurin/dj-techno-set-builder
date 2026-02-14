"""Tests for import workflow tools."""

from __future__ import annotations


async def test_import_tools_registered():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "import_playlist" in tool_names
    assert "import_tracks" in tool_names


async def test_import_tools_have_import_tag():
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        if tool.name in {"import_playlist", "import_tracks"}:
            assert tool.tags is not None
            assert "import" in tool.tags


async def test_gateway_has_namespaced_import_tools():
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "dj_import_playlist" in tool_names
    assert "dj_import_tracks" in tool_names
