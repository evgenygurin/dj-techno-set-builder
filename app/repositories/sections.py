from typing import Any

from app.models.sections import TrackSection
from app.repositories.base import BaseRepository


class SectionsRepository(BaseRepository[TrackSection]):
    model = TrackSection

    async def list_by_track(
        self,
        track_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TrackSection], int]:
        filters: list[Any] = [self.model.track_id == track_id]
        return await self.list(offset=offset, limit=limit, filters=filters)
