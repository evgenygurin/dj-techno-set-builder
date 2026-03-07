from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import get_session
from app.models import Base

# Temporarily disable MCP for tests due to typing_extensions conflict
# from app.main import create_app


def create_minimal_app():
    """Create app without MCP for testing."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    from app.database import close_database, init_database
    from app.routers import (
        albums,
        artists,
        audio,
        bpms,
        catalog,
        dj_library_items,
        dj_sets,
        features,
        health,
        keys,
        labels,
        providers,
        sync,
        tracks,
        transitions,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_database()
        yield
        await close_database()

    app = FastAPI(
        title="DJ Techno Set Builder",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Health check (no version)
    app.include_router(health.router)

    # API routes (versioned)
    app.include_router(albums.router, prefix="/api/v1")
    app.include_router(artists.router, prefix="/api/v1")
    app.include_router(audio.router, prefix="/api/v1")
    app.include_router(bpms.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(dj_library_items.router, prefix="/api/v1")
    app.include_router(dj_sets.router, prefix="/api/v1")
    app.include_router(features.router, prefix="/api/v1")
    app.include_router(keys.router, prefix="/api/v1")
    app.include_router(labels.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(sync.router, prefix="/api/v1")
    app.include_router(tracks.router, prefix="/api/v1")
    app.include_router(transitions.router, prefix="/api/v1")

    return app


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as sess:
            yield sess

    application = create_minimal_app()
    application.dependency_overrides[get_session] = _override_session

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
