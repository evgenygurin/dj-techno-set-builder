"""Async bridge and session management for the CLI layer.

Provides ``run_async()`` to bridge Typer sync callbacks into the async
service layer, and ``open_session()`` for scoped DB access.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from rich.console import Console
from sqlalchemy.ext.asyncio import AsyncSession

console = Console()
err_console = Console(stderr=True)


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from synchronous Typer callback."""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        err_console.print("[yellow]Interrupted[/yellow]")
        sys.exit(130)


@contextlib.asynccontextmanager
async def open_session() -> AsyncIterator[AsyncSession]:
    """Yield an async DB session using the application session factory.

    Commits on clean exit, rolls back on exception.
    """
    from app.database import session_factory

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def with_session[T](
    fn: Callable[[AsyncSession], Coroutine[Any, Any, T]],
) -> T:
    """Convenience wrapper: open session, run fn, return result."""
    async with open_session() as session:
        return await fn(session)
