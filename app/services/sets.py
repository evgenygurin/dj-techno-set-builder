from app.core.errors import NotFoundError
from app.infrastructure.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.schemas.sets import (
    DjSetCreate,
    DjSetItemCreate,
    DjSetItemList,
    DjSetItemRead,
    DjSetList,
    DjSetRead,
    DjSetUpdate,
    DjSetVersionCreate,
    DjSetVersionList,
    DjSetVersionRead,
)
from app.services.base import BaseService


class DjSetService(BaseService):
    def __init__(
        self,
        repo: DjSetRepository,
        version_repo: DjSetVersionRepository,
        item_repo: DjSetItemRepository,
    ) -> None:
        super().__init__()
        self.repo = repo
        self.version_repo = version_repo
        self.item_repo = item_repo

    # --- Set CRUD ---

    async def get(self, set_id: int) -> DjSetRead:
        dj_set = await self.repo.get_by_id(set_id)
        if not dj_set:
            raise NotFoundError("DjSet", set_id=set_id)
        return DjSetRead.model_validate(dj_set)

    async def list(
        self, *, offset: int = 0, limit: int = 50, search: str | None = None
    ) -> DjSetList:
        if search:
            items, total = await self.repo.search_by_name(search, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return DjSetList(
            items=[DjSetRead.model_validate(s) for s in items],
            total=total,
        )

    async def create(self, data: DjSetCreate) -> DjSetRead:
        dj_set = await self.repo.create(**data.model_dump())
        return DjSetRead.model_validate(dj_set)

    async def update(self, set_id: int, data: DjSetUpdate) -> DjSetRead:
        dj_set = await self.repo.get_by_id(set_id)
        if not dj_set:
            raise NotFoundError("DjSet", set_id=set_id)
        updated = await self.repo.update(dj_set, **data.model_dump(exclude_unset=True))
        return DjSetRead.model_validate(updated)

    async def delete(self, set_id: int) -> None:
        dj_set = await self.repo.get_by_id(set_id)
        if not dj_set:
            raise NotFoundError("DjSet", set_id=set_id)
        await self.repo.delete(dj_set)

    # --- Version CRUD ---

    async def list_versions(
        self, set_id: int, *, offset: int = 0, limit: int = 50
    ) -> DjSetVersionList:
        await self._require_set(set_id)
        items, total = await self.version_repo.list_by_set(set_id, offset=offset, limit=limit)
        return DjSetVersionList(
            items=[DjSetVersionRead.model_validate(v) for v in items],
            total=total,
        )

    async def create_version(self, set_id: int, data: DjSetVersionCreate) -> DjSetVersionRead:
        await self._require_set(set_id)
        version = await self.version_repo.create(set_id=set_id, **data.model_dump())
        return DjSetVersionRead.model_validate(version)

    async def get_version(self, set_version_id: int) -> DjSetVersionRead:
        version = await self.version_repo.get_by_id(set_version_id)
        if not version:
            raise NotFoundError("DjSetVersion", set_version_id=set_version_id)
        return DjSetVersionRead.model_validate(version)

    # --- Item CRUD ---

    async def list_items(
        self, set_version_id: int, *, offset: int = 0, limit: int = 50
    ) -> DjSetItemList:
        await self._require_version(set_version_id)
        items, total = await self.item_repo.list_by_version(
            set_version_id, offset=offset, limit=limit
        )
        return DjSetItemList(
            items=[DjSetItemRead.model_validate(i) for i in items],
            total=total,
        )

    async def add_item(self, set_version_id: int, data: DjSetItemCreate) -> DjSetItemRead:
        await self._require_version(set_version_id)
        item = await self.item_repo.create(set_version_id=set_version_id, **data.model_dump())
        return DjSetItemRead.model_validate(item)

    # --- Helpers ---

    async def _require_set(self, set_id: int) -> None:
        dj_set = await self.repo.get_by_id(set_id)
        if not dj_set:
            raise NotFoundError("DjSet", set_id=set_id)

    async def _require_version(self, set_version_id: int) -> None:
        version = await self.version_repo.get_by_id(set_version_id)
        if not version:
            raise NotFoundError("DjSetVersion", set_version_id=set_version_id)
