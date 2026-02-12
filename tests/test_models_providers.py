import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.providers import Provider


async def test_create_provider(session: AsyncSession) -> None:
    p = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add(p)
    await session.flush()
    result = await session.execute(select(Provider).where(Provider.provider_id == 1))
    assert result.scalar_one().provider_code == "spotify"


async def test_provider_code_unique(session: AsyncSession) -> None:
    session.add(Provider(provider_id=1, provider_code="spotify", name="Spotify"))
    session.add(Provider(provider_id=2, provider_code="spotify", name="Duplicate"))
    with pytest.raises(IntegrityError):
        await session.flush()
