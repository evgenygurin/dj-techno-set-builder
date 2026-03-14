"""Shared fixtures for CLI tests.

Uses Typer's CliRunner for synchronous invocation and patches
``app.database.session_factory`` to use the test in-memory SQLite engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli_session(engine: Any) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test engine.

    CLI commands use ``app.database.session_factory`` — we patch it to point
    to the test in-memory database via this fixture.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def patched_cli(cli_session: async_sessionmaker[AsyncSession]) -> Iterator[None]:
    """Patch ``app.database.session_factory`` so CLI commands hit the test DB."""
    with patch("app.database.session_factory", cli_session):
        yield
