from app.errors import NotFoundError
from app.repositories.labels import LabelRepository
from app.schemas.labels import LabelCreate, LabelList, LabelRead, LabelUpdate
from app.services.base import BaseService


class LabelService(BaseService):
    def __init__(self, repo: LabelRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, label_id: int) -> LabelRead:
        label = await self.repo.get_by_id(label_id)
        if not label:
            raise NotFoundError("Label", label_id=label_id)
        return LabelRead.model_validate(label)

    async def list(
        self, *, offset: int = 0, limit: int = 50, search: str | None = None
    ) -> LabelList:
        if search:
            items, total = await self.repo.search_by_name(search, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return LabelList(
            items=[LabelRead.model_validate(lbl) for lbl in items],
            total=total,
        )

    async def create(self, data: LabelCreate) -> LabelRead:
        label = await self.repo.create(**data.model_dump())
        return LabelRead.model_validate(label)

    async def update(self, label_id: int, data: LabelUpdate) -> LabelRead:
        label = await self.repo.get_by_id(label_id)
        if not label:
            raise NotFoundError("Label", label_id=label_id)
        updated = await self.repo.update(label, **data.model_dump(exclude_unset=True))
        return LabelRead.model_validate(updated)

    async def delete(self, label_id: int) -> None:
        label = await self.repo.get_by_id(label_id)
        if not label:
            raise NotFoundError("Label", label_id=label_id)
        await self.repo.delete(label)
