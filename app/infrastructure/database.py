from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_connect_args: dict[str, object] = {}
if settings.database_url.startswith("sqlite"):
    _connect_args["timeout"] = 30  # busy_timeout: wait up to 30s for lock release

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    """Import models so metadata is populated, then (for dev) create tables."""
    import app.core.models  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        from app.core.models.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    await _seed_providers()


async def _seed_providers() -> None:
    """Ensure standard providers exist."""
    from app.infrastructure.repositories.platform.providers import ProviderRepository

    async with session_factory() as session:
        repo = ProviderRepository(session)
        await repo.get_or_create(provider_id=1, code="spotify", name="Spotify")
        await repo.get_or_create(provider_id=2, code="soundcloud", name="SoundCloud")
        await repo.get_or_create(provider_id=3, code="beatport", name="Beatport")
        await repo.get_or_create(provider_id=4, code="ym", name="Yandex Music")
        await session.commit()


async def close_db() -> None:
    await engine.dispose()
