from typing import Any

from app.models.catalog import Label
from app.infrastructure.repositories.base import BaseRepository


class LabelRepository(BaseRepository[Label]):
    model = Label

    async def search_by_name(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Label], int]:
        filters: list[Any] = [Label.name.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)
