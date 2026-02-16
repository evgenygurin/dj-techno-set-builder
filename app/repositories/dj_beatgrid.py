"""Repository for DJ beatgrids with batch loading."""

from sqlalchemy import select

from app.models.dj import DjBeatgrid
from app.repositories.base import BaseRepository


class DjBeatgridRepository(BaseRepository[DjBeatgrid]):
    model = DjBeatgrid

    async def get_canonical_by_track_ids(
        self,
        track_ids: list[int],
    ) -> dict[int, DjBeatgrid]:
        """Batch-load canonical beatgrids for given track IDs.

        Returns dict[track_id] -> DjBeatgrid (only is_canonical=True).
        Tracks without a canonical beatgrid are absent from the dict.
        """
        if not track_ids:
            return {}
        stmt = (
            select(DjBeatgrid)
            .where(
                DjBeatgrid.track_id.in_(track_ids),
                DjBeatgrid.is_canonical.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        return {bg.track_id: bg for bg in result.scalars()}
