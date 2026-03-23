import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import get_session
from app.main import create_app
from app.core.models import Base


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


@pytest.fixture(scope="session")
async def engine():
    """Session-scoped engine — in-memory SQLite (default) or PostgreSQL.

    When DATABASE_URL env var is set (e.g. in CI), uses that URL
    instead of in-memory SQLite.  SQLite-specific event listeners
    (isolation_level, BEGIN) are only registered for SQLite.

    StaticPool is used for SQLite to ensure single-connection sharing.
    PostgreSQL uses default pooling.
    """
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite://")
    is_sqlite = _is_sqlite(db_url)

    engine_kwargs: dict = {"echo": False}
    if is_sqlite:
        engine_kwargs["poolclass"] = StaticPool

    eng = create_async_engine(db_url, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(eng.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            """Disable pysqlite's implicit transaction handling."""
            dbapi_conn.isolation_level = None

        @event.listens_for(eng.sync_engine, "begin")
        def _do_begin(conn):
            """Emit our own BEGIN to match the explicit ROLLBACK."""
            conn.exec_driver_sql("BEGIN")

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def _connection(engine) -> AsyncIterator[AsyncConnection]:
    """Function-scoped connection wrapped in a transaction.

    The transaction is always rolled back on teardown, ensuring
    complete test isolation even with a shared StaticPool engine.
    """
    async with engine.connect() as conn, conn.begin() as txn:
        yield conn
        await txn.rollback()


@pytest.fixture
async def seed_providers(session: AsyncSession) -> None:
    """Seed standard providers into the test session.

    Uses merge() to handle cases where the provider already exists
    (e.g., created by the test itself before requesting this fixture).
    """
    from app.core.models.providers import Provider

    for pid, code, name in [
        (1, "spotify", "Spotify"),
        (2, "soundcloud", "SoundCloud"),
        (3, "beatport", "Beatport"),
        (4, "ym", "Yandex Music"),
    ]:
        await session.merge(Provider(provider_id=pid, provider_code=code, name=name))
    await session.flush()


@pytest.fixture
async def session(_connection) -> AsyncIterator[AsyncSession]:
    """Function-scoped session with automatic rollback.

    Bound to the shared connection's outer transaction via
    ``join_transaction_mode="create_savepoint"``.  Every
    ``session.commit()`` only releases a SAVEPOINT (not the real
    transaction).  On teardown the outer transaction is rolled back,
    so each test sees a clean database.
    """
    sess = AsyncSession(
        bind=_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield sess
    await sess.close()


@pytest.fixture
async def client(_connection) -> AsyncIterator[AsyncClient]:
    """Function-scoped HTTP client with full rollback after each test.

    Overrides FastAPI's ``get_session`` dependency to yield sessions
    bound to the same connection and outer transaction as the
    ``session`` fixture, so all data written through the API is
    rolled back after the test.
    """

    async def _override_session() -> AsyncIterator[AsyncSession]:
        sess = AsyncSession(
            bind=_connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield sess
        finally:
            await sess.close()

    application = create_app()
    application.dependency_overrides[get_session] = _override_session

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
