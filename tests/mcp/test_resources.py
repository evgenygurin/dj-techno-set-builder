"""Tests for MCP resources."""

from __future__ import annotations


async def test_catalog_stats_resource_listed():
    """The catalog://stats static resource should be registered."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    resources = await mcp.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "catalog://stats" in uris


async def test_playlist_status_template_listed():
    """playlist://{playlist_id}/status should appear as a resource template."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    templates = await mcp.list_resource_templates()
    template_uris = {t.uri_template for t in templates}
    assert "playlist://{playlist_id}/status" in template_uris


async def test_set_summary_template_listed():
    """set://{set_id}/summary should appear as a resource template."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    templates = await mcp.list_resource_templates()
    template_uris = {t.uri_template for t in templates}
    assert "set://{set_id}/summary" in template_uris


async def test_resources_via_gateway_have_namespace():
    """Static resources should be namespaced in the gateway."""
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    resources = await mcp.list_resources()
    uris = {str(r.uri) for r in resources}
    # Gateway mounts the workflow server with namespace "dj", so the
    # catalog://stats resource becomes catalog://dj/stats
    assert "catalog://dj/stats" in uris


async def test_resource_templates_via_gateway_have_namespace():
    """Resource templates should be namespaced in the gateway."""
    from app.mcp.gateway import create_dj_mcp

    mcp = create_dj_mcp()
    templates = await mcp.list_resource_templates()
    template_uris = {t.uri_template for t in templates}
    assert "playlist://dj/{playlist_id}/status" in template_uris
    assert "set://dj/{set_id}/summary" in template_uris
