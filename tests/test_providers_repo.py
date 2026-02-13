from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.providers import ProviderRepository


async def test_get_or_create_provider(session: AsyncSession) -> None:
    repo = ProviderRepository(session)
    p = await repo.get_or_create(provider_id=4, code="yandex_music", name="Yandex Music")
    assert p.provider_id == 4
    assert p.provider_code == "yandex_music"

    # Idempotent — second call returns same
    p2 = await repo.get_or_create(provider_id=4, code="yandex_music", name="Yandex Music")
    assert p2.provider_id == p.provider_id


async def test_get_by_code(session: AsyncSession) -> None:
    repo = ProviderRepository(session)
    assert await repo.get_by_code("yandex_music") is None

    await repo.get_or_create(provider_id=4, code="yandex_music", name="Yandex Music")
    p = await repo.get_by_code("yandex_music")
    assert p is not None
    assert p.name == "Yandex Music"
