"""Repository for DJ cue points with batch loading."""

from sqlalchemy import select

from app.core.models.dj import DjCuePoint
from app.infrastructure.repositories.base import BaseRepository


class DjCuePointRepository(BaseRepository[DjCuePoint]):
    model = DjCuePoint

    async def get_by_track_ids(
        self,
        track_ids: list[int],
    ) -> dict[int, list[DjCuePoint]]:
        """Batch-load cue points for given track IDs.

        Returns dict[track_id] -> list of DjCuePoint, ordered by position.
        """
        if not track_ids:
            return {}
        stmt = (
            select(DjCuePoint)
            .where(DjCuePoint.track_id.in_(track_ids))
            .order_by(DjCuePoint.track_id, DjCuePoint.position_ms)
        )
        result = await self.session.execute(stmt)
        cues_map: dict[int, list[DjCuePoint]] = {}
        for cue in result.scalars():
            cues_map.setdefault(cue.track_id, []).append(cue)
        return cues_map
