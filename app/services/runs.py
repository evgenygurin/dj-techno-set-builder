from app.errors import NotFoundError
from app.repositories.runs import FeatureRunRepository, TransitionRunRepository
from app.schemas.runs import (
    FeatureRunCreate,
    FeatureRunList,
    FeatureRunRead,
    TransitionRunCreate,
    TransitionRunList,
    TransitionRunRead,
)
from app.services.base import BaseService


class FeatureRunService(BaseService):
    def __init__(self, repo: FeatureRunRepository) -> None:
        super().__init__()
        self.repo = repo

    async def create(self, data: FeatureRunCreate) -> FeatureRunRead:
        run = await self.repo.create(**data.model_dump())
        return FeatureRunRead.model_validate(run)

    async def get(self, run_id: int) -> FeatureRunRead:
        run = await self.repo.get_by_id(run_id)
        if not run:
            raise NotFoundError("FeatureExtractionRun", run_id=run_id)
        return FeatureRunRead.model_validate(run)

    async def list(self, *, offset: int = 0, limit: int = 50) -> FeatureRunList:
        items, total = await self.repo.list(offset=offset, limit=limit)
        return FeatureRunList(
            items=[FeatureRunRead.model_validate(r) for r in items],
            total=total,
        )


class TransitionRunService(BaseService):
    def __init__(self, repo: TransitionRunRepository) -> None:
        super().__init__()
        self.repo = repo

    async def create(self, data: TransitionRunCreate) -> TransitionRunRead:
        run = await self.repo.create(**data.model_dump())
        return TransitionRunRead.model_validate(run)

    async def get(self, run_id: int) -> TransitionRunRead:
        run = await self.repo.get_by_id(run_id)
        if not run:
            raise NotFoundError("TransitionRun", run_id=run_id)
        return TransitionRunRead.model_validate(run)

    async def list(self, *, offset: int = 0, limit: int = 50) -> TransitionRunList:
        items, total = await self.repo.list(offset=offset, limit=limit)
        return TransitionRunList(
            items=[TransitionRunRead.model_validate(r) for r in items],
            total=total,
        )
