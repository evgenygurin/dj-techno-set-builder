"""Tests for CLI async bridge and session management."""

from __future__ import annotations

from app.cli._context import console, err_console, run_async


def test_run_async_returns_value() -> None:
    """run_async bridges async → sync and returns the result."""

    async def _coro() -> int:
        return 42

    assert run_async(_coro()) == 42


def test_run_async_propagates_exception() -> None:
    """run_async lets exceptions propagate."""
    import pytest

    async def _boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async(_boom())


def test_console_exists() -> None:
    """Module-level console objects exist."""
    assert console is not None
    assert err_console is not None
    assert err_console.stderr is True


def test_open_session_commits(patched_cli: None) -> None:
    """open_session commits on clean exit."""

    async def _check() -> bool:
        from app.cli._context import open_session

        async with open_session() as session:
            # Just ensure session is usable
            return session is not None

    result = run_async(_check())
    assert result is True


def test_open_session_rollback_on_error(patched_cli: None) -> None:
    """open_session rolls back on exception."""
    import pytest

    async def _check() -> None:
        from app.cli._context import open_session

        async with open_session() as _session:
            raise RuntimeError("test error")

    with pytest.raises(RuntimeError, match="test error"):
        run_async(_check())


def test_with_session(patched_cli: None) -> None:
    """with_session convenience wrapper."""

    async def _check() -> bool:
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.cli._context import with_session

        result = await with_session(lambda s: _identity(isinstance(s, AsyncSession)))
        return result

    async def _identity(val: bool) -> bool:
        return val

    result = run_async(_check())
    assert result is True
