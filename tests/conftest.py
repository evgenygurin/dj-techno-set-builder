"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.router import ModuleRegistry
from app.core.logging import setup_logging
from app.db.base import Base
from app.main import create_app

# Configure logging once for the test session
setup_logging(log_level="DEBUG", json_output=False)


@pytest.fixture
async def engine():
    """In-memory SQLite async engine — fresh per test."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
def app():
    """Fresh FastAPI app per test (no lifespan — ASGITransport skips it)."""
    return create_app(registry=ModuleRegistry())


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
