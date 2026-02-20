from typing import Any

from sqlalchemy import func, select

from app.models.sets import DjSet, DjSetItem, DjSetVersion
from app.repositories.base import BaseRepository


class DjSetRepository(BaseRepository[DjSet]):
    model = DjSet

    async def search_by_name(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjSet], int]:
        filters: list[Any] = [DjSet.name.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def get_stats_batch(self, set_ids: list[int]) -> dict[int, tuple[int, int]]:
        """Return {set_id: (version_count, track_count_in_latest_version)}.

        Two queries total regardless of how many sets — avoids N+1 in list_sets.
        """
        if not set_ids:
            return {}

        # 1. version_count per set
        ver_q = (
            select(DjSetVersion.set_id, func.count().label("ver_cnt"))
            .where(DjSetVersion.set_id.in_(set_ids))
            .group_by(DjSetVersion.set_id)
        )
        ver_rows = (await self.session.execute(ver_q)).all()
        version_counts = {row.set_id: row.ver_cnt for row in ver_rows}

        # 2. latest version id per set (max set_version_id)
        latest_q = (
            select(
                DjSetVersion.set_id,
                func.max(DjSetVersion.set_version_id).label("latest_vid"),
            )
            .where(DjSetVersion.set_id.in_(set_ids))
            .group_by(DjSetVersion.set_id)
        ).subquery()

        # 3. track_count for those latest versions
        item_q = (
            select(latest_q.c.set_id, func.count(DjSetItem.set_item_id).label("trk_cnt"))
            .join(DjSetItem, DjSetItem.set_version_id == latest_q.c.latest_vid, isouter=True)
            .group_by(latest_q.c.set_id)
        )
        item_rows = (await self.session.execute(item_q)).all()
        track_counts = {row.set_id: row.trk_cnt for row in item_rows}

        return {sid: (version_counts.get(sid, 0), track_counts.get(sid, 0)) for sid in set_ids}


class DjSetVersionRepository(BaseRepository[DjSetVersion]):
    model = DjSetVersion

    async def list_by_set(
        self, set_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjSetVersion], int]:
        filters: list[Any] = [DjSetVersion.set_id == set_id]
        return await self.list(offset=offset, limit=limit, filters=filters)


class DjSetItemRepository(BaseRepository[DjSetItem]):
    model = DjSetItem

    async def list_by_version(
        self, set_version_id: int, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[DjSetItem], int]:
        filters: list[Any] = [DjSetItem.set_version_id == set_version_id]
        return await self.list(offset=offset, limit=limit, filters=filters)
