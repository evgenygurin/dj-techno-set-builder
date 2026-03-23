"""Tests for CLI sets sub-command."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.cli.main import app
from app.core.models.sets import DjSet, DjSetVersion


async def _seed_sets(factory: async_sessionmaker[AsyncSession]) -> list[int]:
    """Seed test DJ sets and return their IDs."""
    async with factory() as session:
        s1 = DjSet(name="Saturday Night Set")
        s2 = DjSet(name="Morning After", template_name="classic_60")
        session.add_all([s1, s2])
        await session.flush()
        ids = [s1.set_id, s2.set_id]
        await session.commit()
        return ids


async def _seed_set_with_version(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    """Seed a DJ set with one version, return (set_id, version_id)."""
    async with factory() as session:
        dj_set = DjSet(name="Test Set")
        session.add(dj_set)
        await session.flush()
        version = DjSetVersion(set_id=dj_set.set_id, version_label="v1", score=0.85)
        session.add(version)
        await session.flush()
        result = (dj_set.set_id, version.set_version_id)
        await session.commit()
        return result


def test_sets_list_empty(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """List sets with empty DB."""
    result = runner.invoke(app, ["sets", "list"])
    assert result.exit_code == 0
    assert "No sets found" in result.output


def test_sets_list(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """List sets shows seeded sets."""
    import asyncio

    asyncio.run(_seed_sets(cli_session))

    result = runner.invoke(app, ["sets", "list"])
    assert result.exit_code == 0
    assert "Saturday Night Set" in result.output
    assert "Morning After" in result.output


def test_sets_get(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Get set shows set details with version table."""
    import asyncio

    set_id, _version_id = asyncio.run(_seed_set_with_version(cli_session))

    result = runner.invoke(app, ["sets", "get", str(set_id)])
    assert result.exit_code == 0
    assert "Test Set" in result.output
    assert str(set_id) in result.output
    assert "Versions" in result.output


def test_sets_create(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Create set creates and shows confirmation."""
    result = runner.invoke(app, ["sets", "create", "My New Set"])
    assert result.exit_code == 0
    assert "Created set" in result.output
    assert "My New Set" in result.output


def test_sets_create_with_template(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Create set with template option."""
    result = runner.invoke(app, ["sets", "create", "Peak Set", "--template", "classic_60"])
    assert result.exit_code == 0
    assert "Created set" in result.output


def test_sets_delete_with_confirm(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Delete set with --yes flag."""
    import asyncio

    ids = asyncio.run(_seed_sets(cli_session))

    result = runner.invoke(app, ["sets", "delete", str(ids[0]), "--yes"])
    assert result.exit_code == 0
    assert "Deleted set" in result.output


def test_sets_get_not_found(
    runner: CliRunner,
    patched_cli: None,
) -> None:
    """Get non-existent set fails."""
    result = runner.invoke(app, ["sets", "get", "99999"])
    assert result.exit_code != 0


def test_sets_tracks_no_versions(
    runner: CliRunner,
    patched_cli: None,
    cli_session: async_sessionmaker[AsyncSession],
) -> None:
    """Show tracks for a set with no versions shows error."""
    import asyncio

    ids = asyncio.run(_seed_sets(cli_session))

    result = runner.invoke(app, ["sets", "tracks", str(ids[0])])
    assert result.exit_code != 0
