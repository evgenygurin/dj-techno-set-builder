"""Shared fixtures for MCP tests.

Server instances are created in fixtures; Client is opened in
test bodies (FastMCP testing best practice — don't open Clients
in fixtures to avoid event loop issues).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(scope="session")
def workflow_mcp() -> FastMCP:
    """DJ Workflows MCP server (12 hand-written tools + prompts + resources)."""
    from app.mcp.tools import create_workflow_mcp

    return create_workflow_mcp()


@pytest.fixture(scope="session")
def gateway_mcp() -> FastMCP:
    """Full DJ Set Builder gateway (YM + DJ namespaces + transforms)."""
    from app.mcp.gateway import create_dj_mcp

    return create_dj_mcp()


@pytest.fixture(scope="session")
def ym_mcp() -> FastMCP:
    """Yandex Music MCP sub-server (~30 OpenAPI-generated tools)."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    return create_yandex_music_mcp()


@pytest.fixture
async def workflow_mcp_with_db(_connection) -> AsyncIterator[FastMCP]:
    """DJ Workflows MCP server wired to test DB.

    Patches ``app.mcp.dependencies.session_factory`` with a factory
    that returns sessions bound to the shared test connection using
    ``join_transaction_mode="create_savepoint"``.  This ensures
    every ``session.commit()`` inside MCP tool calls only releases
    a SAVEPOINT, so the outer transaction can roll everything back.
    """
    from app.mcp.tools import create_workflow_mcp

    @asynccontextmanager
    async def _savepoint_session_factory() -> AsyncIterator[AsyncSession]:
        sess = AsyncSession(
            bind=_connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield sess
        finally:
            await sess.close()

    with patch("app.mcp.dependencies.session_factory", _savepoint_session_factory):
        yield create_workflow_mcp()
