from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.metadata_yandex import YandexMetadata


class YandexMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_yandex_track_id(self, ym_id: str) -> YandexMetadata | None:
        stmt = select(YandexMetadata).where(YandexMetadata.yandex_track_id == ym_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_track_id(self, track_id: int) -> YandexMetadata | None:
        stmt = select(YandexMetadata).where(YandexMetadata.track_id == track_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self, *, track_id: int, yandex_track_id: str, **kwargs: Any
    ) -> YandexMetadata:
        existing = await self.get_by_track_id(track_id)
        if existing:
            for k, v in kwargs.items():
                if v is not None:
                    setattr(existing, k, v)
            if existing.yandex_track_id != yandex_track_id:
                existing.yandex_track_id = yandex_track_id
            await self.session.flush()
            return existing
        meta = YandexMetadata(
            track_id=track_id, yandex_track_id=yandex_track_id, **kwargs
        )
        self.session.add(meta)
        await self.session.flush()
        return meta

    async def list_unenriched_track_ids(self) -> list[int]:
        """Track IDs that have no YandexMetadata row."""
        stmt = (
            select(Track.track_id)
            .outerjoin(YandexMetadata, Track.track_id == YandexMetadata.track_id)
            .where(YandexMetadata.track_id.is_(None))
            .order_by(Track.track_id)
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]
