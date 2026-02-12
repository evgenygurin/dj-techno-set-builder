from typing import Any

from app.models.catalog import Track
from app.repositories.base import BaseRepository


class TrackRepository(BaseRepository[Track]):
    model = Track

    async def search_by_title(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Track], int]:
        filters: list[Any] = [Track.title.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)
