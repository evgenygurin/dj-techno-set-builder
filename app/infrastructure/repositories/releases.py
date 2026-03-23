from typing import Any

from app.core.models.catalog import Release
from app.infrastructure.repositories.base import BaseRepository


class ReleaseRepository(BaseRepository[Release]):
    model = Release

    async def search_by_title(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Release], int]:
        filters: list[Any] = [Release.title.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_by_label(
        self, label_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Release], int]:
        filters: list[Any] = [Release.label_id == label_id]
        return await self.list(offset=offset, limit=limit, filters=filters)
