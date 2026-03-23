from typing import Any

from app.core.models.catalog import Artist
from app.infrastructure.repositories.base import BaseRepository


class ArtistRepository(BaseRepository[Artist]):
    model = Artist

    async def search_by_name(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Artist], int]:
        filters: list[Any] = [Artist.name.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)
