"""Tests for CLI main entry point and top-level commands."""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli.main import app


def test_help(runner: CliRunner) -> None:
    """Main --help shows all sub-commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "tracks" in result.output
    assert "playlists" in result.output
    assert "sets" in result.output
    assert "build" in result.output
    assert "deliver" in result.output
    assert "analysis" in result.output


def test_version(runner: CliRunner) -> None:
    """Version command prints version string."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "v0.1.0" in result.output


def test_info(runner: CliRunner, patched_cli: None) -> None:
    """Info command shows library stats."""
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "DJ Techno Set Builder" in result.output
    assert "Tracks" in result.output


def test_tracks_help(runner: CliRunner) -> None:
    """Tracks sub-command shows its own help."""
    result = runner.invoke(app, ["tracks", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "get" in result.output
    assert "create" in result.output
    assert "delete" in result.output


def test_playlists_help(runner: CliRunner) -> None:
    """Playlists sub-command shows its own help."""
    result = runner.invoke(app, ["playlists", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "get" in result.output
    assert "create" in result.output


def test_sets_help(runner: CliRunner) -> None:
    """Sets sub-command shows its own help."""
    result = runner.invoke(app, ["sets", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "get" in result.output
    assert "create" in result.output
    assert "tracks" in result.output


def test_build_help(runner: CliRunner) -> None:
    """Build sub-command shows its own help."""
    result = runner.invoke(app, ["build", "--help"])
    assert result.exit_code == 0
    assert "set" in result.output
    assert "rebuild" in result.output
    assert "score" in result.output


def test_deliver_help(runner: CliRunner) -> None:
    """Deliver sub-command shows its own help."""
    result = runner.invoke(app, ["deliver", "--help"])
    assert result.exit_code == 0
    assert "set" in result.output


def test_analysis_help(runner: CliRunner) -> None:
    """Analysis sub-command shows its own help."""
    result = runner.invoke(app, ["analysis", "--help"])
    assert result.exit_code == 0
    assert "features" in result.output
    assert "classify" in result.output
    assert "gaps" in result.output
    assert "inspect" in result.output
