from typing import Any

from app.models.sets import DjSet, DjSetItem, DjSetVersion
from app.repositories.base import BaseRepository


class DjSetRepository(BaseRepository[DjSet]):
    model = DjSet

    async def search_by_name(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjSet], int]:
        filters: list[Any] = [DjSet.name.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)


class DjSetVersionRepository(BaseRepository[DjSetVersion]):
    model = DjSetVersion

    async def list_by_set(
        self, set_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjSetVersion], int]:
        filters: list[Any] = [DjSetVersion.set_id == set_id]
        return await self.list(offset=offset, limit=limit, filters=filters)


class DjSetItemRepository(BaseRepository[DjSetItem]):
    model = DjSetItem

    async def list_by_version(
        self, set_version_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjSetItem], int]:
        filters: list[Any] = [DjSetItem.set_version_id == set_version_id]
        return await self.list(offset=offset, limit=limit, filters=filters)
