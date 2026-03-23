"""Tests for CLI playlists sub-command."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.cli.main import app
from app.core.models.dj import DjPlaylist


async def _seed_playlists(factory: async_sessionmaker[AsyncSession]) -> list[int]:
    """Seed test playlists and return their IDs."""
    async with factory() as session:
        p1 = DjPlaylist(name="Peak Hour Techno")
        p2 = DjPlaylist(name="Deep & Minimal")
        session.add_all([p1, p2])
        await session.flush()
        ids = [p1.playlist_id, p2.playlist_id]
        await session.commit()
        return ids


def test_playlists_list_empty(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """List playlists with empty DB."""
    result = runner.invoke(app, ["playlists", "list"])
    assert result.exit_code == 0
    assert "No playlists found" in result.output


def test_playlists_list(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """List playlists shows seeded playlists."""
    import asyncio

    asyncio.run(_seed_playlists(cli_session))

    result = runner.invoke(app, ["playlists", "list"])
    assert result.exit_code == 0
    assert "Peak Hour Techno" in result.output
    assert "Deep & Minimal" in result.output


def test_playlists_get(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Get playlist shows details."""
    import asyncio

    ids = asyncio.run(_seed_playlists(cli_session))

    result = runner.invoke(app, ["playlists", "get", str(ids[0])])
    assert result.exit_code == 0
    assert "Peak Hour Techno" in result.output
    assert str(ids[0]) in result.output


def test_playlists_create(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Create playlist creates and shows confirmation."""
    result = runner.invoke(app, ["playlists", "create", "My New Playlist"])
    assert result.exit_code == 0
    assert "Created playlist" in result.output
    assert "My New Playlist" in result.output


def test_playlists_delete_with_confirm(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Delete playlist with --yes flag."""
    import asyncio

    ids = asyncio.run(_seed_playlists(cli_session))

    result = runner.invoke(app, ["playlists", "delete", str(ids[0]), "--yes"])
    assert result.exit_code == 0
    assert "Deleted playlist" in result.output


def test_playlists_get_not_found(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Get non-existent playlist fails."""
    result = runner.invoke(app, ["playlists", "get", "99999"])
    assert result.exit_code != 0
