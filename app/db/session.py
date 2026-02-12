"""Async engine & session factory.

Lazily created on first access so that ``settings.database_url``
is resolved at import time but the engine is only built when needed
(useful for tests that override the URL).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session and closes it afterwards."""
    async with _session_factory() as session:
        yield session


async def close_engine() -> None:
    """Dispose of the connection pool (call on app shutdown)."""
    await _engine.dispose()
