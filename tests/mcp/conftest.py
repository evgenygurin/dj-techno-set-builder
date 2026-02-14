"""Shared fixtures for MCP tests.

Server instances are created in fixtures; Client is opened in
test bodies (FastMCP testing best practice — don't open Clients
in fixtures to avoid event loop issues).
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP


@pytest.fixture
def workflow_mcp() -> FastMCP:
    """DJ Workflows MCP server (12 hand-written tools + prompts + resources)."""
    from app.mcp.workflows import create_workflow_mcp

    return create_workflow_mcp()


@pytest.fixture
def gateway_mcp() -> FastMCP:
    """Full DJ Set Builder gateway (YM + DJ namespaces + transforms)."""
    from app.mcp.gateway import create_dj_mcp

    return create_dj_mcp()


@pytest.fixture
def ym_mcp() -> FastMCP:
    """Yandex Music MCP sub-server (~30 OpenAPI-generated tools)."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    return create_yandex_music_mcp()
