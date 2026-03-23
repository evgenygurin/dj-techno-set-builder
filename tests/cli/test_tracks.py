"""Tests for CLI tracks sub-command."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.cli.main import app
from app.core.models.catalog import Track


async def _seed_tracks(factory: async_sessionmaker[AsyncSession]) -> list[int]:
    """Seed test tracks and return their IDs."""
    async with factory() as session:
        t1 = Track(title="Acid Rain", duration_ms=420000, status=0)
        t2 = Track(title="Deep Warehouse", duration_ms=360000, status=0)
        t3 = Track(title="Techno Dawn", duration_ms=300000, status=0)
        session.add_all([t1, t2, t3])
        await session.flush()
        ids = [t1.track_id, t2.track_id, t3.track_id]
        await session.commit()
        return ids


def test_tracks_list_empty(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """List tracks with empty DB shows 'No tracks found'."""
    result = runner.invoke(app, ["tracks", "list"])
    assert result.exit_code == 0
    assert "No tracks found" in result.output


def test_tracks_list(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """List tracks shows seeded tracks."""
    import asyncio

    asyncio.run(_seed_tracks(cli_session))

    result = runner.invoke(app, ["tracks", "list"])
    assert result.exit_code == 0
    assert "Acid Rain" in result.output
    assert "Deep Warehouse" in result.output


def test_tracks_get(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Get track shows track details."""
    import asyncio

    ids = asyncio.run(_seed_tracks(cli_session))

    result = runner.invoke(app, ["tracks", "get", str(ids[0])])
    assert result.exit_code == 0
    assert "Acid Rain" in result.output
    assert str(ids[0]) in result.output


def test_tracks_get_not_found(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Get non-existent track fails."""
    result = runner.invoke(app, ["tracks", "get", "99999"])
    assert result.exit_code != 0


def test_tracks_create(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Create track creates and shows confirmation."""
    result = runner.invoke(app, ["tracks", "create", "New Track", "300000"])
    assert result.exit_code == 0
    assert "Created track" in result.output
    assert "New Track" in result.output


def test_tracks_delete_with_confirm(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Delete track with --yes flag."""
    import asyncio

    ids = asyncio.run(_seed_tracks(cli_session))

    result = runner.invoke(app, ["tracks", "delete", str(ids[0]), "--yes"])
    assert result.exit_code == 0
    assert "Deleted track" in result.output


def test_tracks_search(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Search tracks by title."""
    import asyncio

    asyncio.run(_seed_tracks(cli_session))

    result = runner.invoke(app, ["tracks", "search", "acid"])
    assert result.exit_code == 0
    assert "Acid Rain" in result.output


def test_tracks_list_with_limit(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """List tracks with limit option."""
    import asyncio

    asyncio.run(_seed_tracks(cli_session))

    result = runner.invoke(app, ["tracks", "list", "--limit", "1"])
    assert result.exit_code == 0
    # Should show total but limited rows
    assert "Total:" in result.output
