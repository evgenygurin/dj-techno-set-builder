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

from app.database import get_session
from app.main import create_app
from app.models import Base


@pytest.fixture(scope="session")
async def engine():
    """Session-scoped engine with StaticPool for in-memory SQLite.

    StaticPool ensures every ``engine.connect()`` returns the same
    underlying DBAPI connection, so tables created once are visible
    to all tests.  Tables are created once at session start and
    dropped at session end — no per-test DDL overhead.

    The ``isolation_level`` / ``do_begin`` event listeners disable
    pysqlite's implicit transaction handling so that SQLAlchemy can
    issue explicit ``BEGIN`` statements.  This is required for
    ``SAVEPOINT`` / ``ROLLBACK`` to work correctly with SQLite.
    See: https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl
    """
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        poolclass=StaticPool,
    )

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
