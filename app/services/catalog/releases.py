from app.core.errors import NotFoundError
from app.infrastructure.repositories.catalog.releases import ReleaseRepository
from app.schemas.releases import ReleaseCreate, ReleaseList, ReleaseRead, ReleaseUpdate
from app.services.base import BaseService


class ReleaseService(BaseService):
    def __init__(self, repo: ReleaseRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, release_id: int) -> ReleaseRead:
        release = await self.repo.get_by_id(release_id)
        if not release:
            raise NotFoundError("Release", release_id=release_id)
        return ReleaseRead.model_validate(release)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        label_id: int | None = None,
    ) -> ReleaseList:
        if search:
            items, total = await self.repo.search_by_title(search, offset=offset, limit=limit)
        elif label_id is not None:
            items, total = await self.repo.list_by_label(label_id, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return ReleaseList(
            items=[ReleaseRead.model_validate(r) for r in items],
            total=total,
        )

    async def create(self, data: ReleaseCreate) -> ReleaseRead:
        release = await self.repo.create(**data.model_dump())
        return ReleaseRead.model_validate(release)

    async def update(self, release_id: int, data: ReleaseUpdate) -> ReleaseRead:
        release = await self.repo.get_by_id(release_id)
        if not release:
            raise NotFoundError("Release", release_id=release_id)
        updated = await self.repo.update(release, **data.model_dump(exclude_unset=True))
        return ReleaseRead.model_validate(updated)

    async def delete(self, release_id: int) -> None:
        release = await self.repo.get_by_id(release_id)
        if not release:
            raise NotFoundError("Release", release_id=release_id)
        await self.repo.delete(release)
