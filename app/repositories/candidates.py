from typing import Any

from app.models.transitions import TransitionCandidate
from app.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[TransitionCandidate]):
    model = TransitionCandidate

    async def list_unscored(
        self,
        run_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TransitionCandidate], int]:
        filters: list[Any] = [
            self.model.run_id == run_id,
            self.model.is_fully_scored == False,  # noqa: E712
        ]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_for_track(
        self,
        track_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TransitionCandidate], int]:
        filters: list[Any] = [
            (self.model.from_track_id == track_id)
            | (self.model.to_track_id == track_id),
        ]
        return await self.list(offset=offset, limit=limit, filters=filters)
