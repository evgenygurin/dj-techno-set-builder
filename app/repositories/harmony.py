"""Repositories for harmony-related models (keys, Camelot wheel)."""

from sqlalchemy import select

from app.models.harmony import Key, KeyEdge
from app.repositories.base import BaseRepository


class KeyRepository(BaseRepository[Key]):
    model = Key


class KeyEdgeRepository(BaseRepository[KeyEdge]):
    model = KeyEdge

    async def list_all(self) -> list[KeyEdge]:
        """Fetch all key edges for lookup table construction."""
        stmt = select(self.model)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
