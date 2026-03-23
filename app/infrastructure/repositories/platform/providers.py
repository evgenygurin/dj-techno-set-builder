from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.providers import Provider


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_code(self, code: str) -> Provider | None:
        stmt = select(Provider).where(Provider.provider_code == code)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(self, *, provider_id: int, code: str, name: str) -> Provider:
        existing = await self.get_by_code(code)
        if existing:
            return existing
        p = Provider(provider_id=provider_id, provider_code=code, name=name)
        self.session.add(p)
        await self.session.flush()
        return p
