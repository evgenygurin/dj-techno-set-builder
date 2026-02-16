from typing import Any

from sqlalchemy import select

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

    async def get_latest_by_track_ids(
        self,
        track_ids: list[int],
    ) -> dict[int, list[TrackSection]]:
        """Batch-load sections for given track IDs.

        Returns dict[track_id] -> list of TrackSection, ordered by start_ms.
        """
        if not track_ids:
            return {}
        stmt = (
            select(self.model)
            .where(self.model.track_id.in_(track_ids))
            .order_by(self.model.track_id, self.model.start_ms)
        )
        result = await self.session.execute(stmt)
        sections_map: dict[int, list[TrackSection]] = {}
        for section in result.scalars():
            sections_map.setdefault(section.track_id, []).append(section)
        return sections_map
