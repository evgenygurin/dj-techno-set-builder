"""Repository for DJ saved loops with batch loading."""

from sqlalchemy import select

from app.models.dj import DjSavedLoop
from app.repositories.base import BaseRepository


class DjSavedLoopRepository(BaseRepository[DjSavedLoop]):
    model = DjSavedLoop

    async def get_by_track_ids(
        self,
        track_ids: list[int],
    ) -> dict[int, list[DjSavedLoop]]:
        """Batch-load saved loops for given track IDs.

        Returns dict[track_id] -> list of DjSavedLoop, ordered by in_ms.
        """
        if not track_ids:
            return {}
        stmt = (
            select(DjSavedLoop)
            .where(DjSavedLoop.track_id.in_(track_ids))
            .order_by(DjSavedLoop.track_id, DjSavedLoop.in_ms)
        )
        result = await self.session.execute(stmt)
        loops_map: dict[int, list[DjSavedLoop]] = {}
        for loop in result.scalars():
            loops_map.setdefault(loop.track_id, []).append(loop)
        return loops_map
