from __future__ import annotations

import builtins

from app.core.errors import NotFoundError
from app.infrastructure.repositories.catalog.tracks import TrackRepository
from app.schemas.tracks import TrackCreate, TrackList, TrackRead, TrackUpdate
from app.services.base import BaseService


class TrackService(BaseService):
    def __init__(self, repo: TrackRepository) -> None:
        super().__init__()
        self.repo = repo

    async def get(self, track_id: int) -> TrackRead:
        track = await self.repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        return TrackRead.model_validate(track)

    async def list(
        self, *, offset: int = 0, limit: int = 50, search: str | None = None
    ) -> TrackList:
        if search:
            items, total = await self.repo.search_by_title(search, offset=offset, limit=limit)
        else:
            items, total = await self.repo.list(offset=offset, limit=limit)
        return TrackList(
            items=[TrackRead.model_validate(t) for t in items],
            total=total,
        )

    async def create(self, data: TrackCreate) -> TrackRead:
        track = await self.repo.create(**data.model_dump())
        return TrackRead.model_validate(track)

    async def update(self, track_id: int, data: TrackUpdate) -> TrackRead:
        track = await self.repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        updated = await self.repo.update(track, **data.model_dump(exclude_unset=True))
        return TrackRead.model_validate(updated)

    async def delete(self, track_id: int) -> None:
        track = await self.repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        await self.repo.delete(track)

    async def get_track_artists(
        self,
        track_ids: builtins.list[int],
    ) -> dict[int, builtins.list[str]]:
        """Get artist names for given track IDs.

        Returns a dict mapping track_id → list of artist names.
        """
        return await self.repo.get_artists_for_tracks(track_ids)
