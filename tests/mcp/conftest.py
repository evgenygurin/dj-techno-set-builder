"""Shared fixtures for MCP tests.

Server instances are created in fixtures; Client is opened in
test bodies (FastMCP testing best practice — don't open Clients
in fixtures to avoid event loop issues).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture
def workflow_mcp() -> FastMCP:
    """DJ Workflows MCP server (12 hand-written tools + prompts + resources)."""
    from app.mcp.tools import create_workflow_mcp

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


@pytest.fixture
async def workflow_mcp_with_db(engine) -> AsyncIterator[FastMCP]:
    """DJ Workflows MCP server wired to test DB.

    Patches ``app.database.session_factory`` (used by ``get_session``)
    so every MCP tool call uses the same in-memory SQLite engine.
    """
    from app.mcp.tools import create_workflow_mcp

    factory = async_sessionmaker(engine, expire_on_commit=False)

    with patch("app.mcp.dependencies.session_factory", factory):
        yield create_workflow_mcp()
