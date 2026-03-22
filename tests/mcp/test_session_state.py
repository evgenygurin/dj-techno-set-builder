"""Tests for session state helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.mcp.session_state import (
    get_last_build,
    get_last_export,
    get_last_playlist,
    save_build_result,
    save_export_config,
    save_playlist_context,
)


def _make_ctx() -> AsyncMock:
    """Create a mock Context with in-memory state store."""
    ctx = AsyncMock()
    state: dict[str, object] = {}
    ctx.set_state = AsyncMock(side_effect=lambda k, v: state.update({k: v}))
    ctx.get_state = AsyncMock(side_effect=lambda k: state.get(k))
    return ctx


# ---------------------------------------------------------------------------
# build result
# ---------------------------------------------------------------------------


async def test_save_and_get_build_result() -> None:
    ctx = _make_ctx()

    await save_build_result(ctx, set_id=1, version_id=42, quality=0.87)
    result = await get_last_build(ctx)

    assert result is not None
    assert result["set_id"] == 1
    assert result["version_id"] == 42
    assert result["quality"] == pytest.approx(0.87)


async def test_get_last_build_returns_none_when_empty() -> None:
    ctx = _make_ctx()

    result = await get_last_build(ctx)

    assert result is None


# ---------------------------------------------------------------------------
# playlist context
# ---------------------------------------------------------------------------


async def test_save_and_get_playlist_context() -> None:
    ctx = _make_ctx()

    await save_playlist_context(ctx, playlist_id=7, name="Techno develop", track_count=50)
    result = await get_last_playlist(ctx)

    assert result is not None
    assert result["playlist_id"] == 7
    assert result["name"] == "Techno develop"
    assert result["track_count"] == 50


async def test_get_last_playlist_returns_none() -> None:
    ctx = _make_ctx()

    result = await get_last_playlist(ctx)

    assert result is None


# ---------------------------------------------------------------------------
# export config
# ---------------------------------------------------------------------------


async def test_save_and_get_export_config() -> None:
    ctx = _make_ctx()

    await save_export_config(ctx, set_id=3, format="mp3", track_count=12)
    result = await get_last_export(ctx)

    assert result is not None
    assert result["set_id"] == 3
    assert result["format"] == "mp3"
    assert result["track_count"] == 12


async def test_get_last_export_returns_none() -> None:
    ctx = _make_ctx()

    result = await get_last_export(ctx)

    assert result is None
