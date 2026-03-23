from app.core.errors import NotFoundError
from app.infrastructure.repositories.audio.transitions import TransitionRepository
from app.schemas.transitions import TransitionList, TransitionRead
from app.services.base import BaseService


class TransitionService(BaseService):
    def __init__(self, repo: TransitionRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, transition_id: int) -> TransitionRead:
        transition = await self.repo.get_by_id(transition_id)
        if not transition:
            raise NotFoundError("Transition", transition_id=transition_id)
        return TransitionRead.model_validate(transition)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        track_id: int | None = None,
        min_quality: float | None = None,
    ) -> TransitionList:
        if track_id is not None:
            items, total = await self.repo.list_by_track(track_id, offset=offset, limit=limit)
        elif min_quality is not None:
            items, total = await self.repo.list_by_quality(min_quality, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return TransitionList(
            items=[TransitionRead.model_validate(t) for t in items],
            total=total,
        )

    async def delete(self, transition_id: int) -> None:
        transition = await self.repo.get_by_id(transition_id)
        if not transition:
            raise NotFoundError("Transition", transition_id=transition_id)
        await self.repo.delete(transition)
