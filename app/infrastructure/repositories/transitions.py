from typing import Any

from app.models.transitions import Transition
from app.infrastructure.repositories.base import BaseRepository


class TransitionRepository(BaseRepository[Transition]):
    model = Transition

    async def list_by_track(
        self, track_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Transition], int]:
        filters: list[Any] = [
            (Transition.from_track_id == track_id) | (Transition.to_track_id == track_id),
        ]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_by_quality(
        self, min_quality: float, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Transition], int]:
        filters: list[Any] = [Transition.transition_quality >= min_quality]
        return await self.list(offset=offset, limit=limit, filters=filters)
