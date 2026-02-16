from typing import Any

from sqlalchemy import select

from app.models.catalog import Artist, Track, TrackArtist
from app.repositories.base import BaseRepository


class TrackRepository(BaseRepository[Track]):
    model = Track

    async def search_by_title(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Track], int]:
        filters: list[Any] = [Track.title.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def get_artists_for_tracks(
        self, track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load artist names for given track IDs.

        Returns a dict mapping track_id → list of artist names,
        ordered by artist role (main artist first).
        Tracks with no artists are absent from the dict.
        """
        if not track_ids:
            return {}
        stmt = (
            select(TrackArtist.track_id, Artist.name)
            .join(Artist, TrackArtist.artist_id == Artist.artist_id)
            .where(TrackArtist.track_id.in_(track_ids))
            .order_by(TrackArtist.track_id, TrackArtist.role)
        )
        result = await self.session.execute(stmt)
        artists_map: dict[int, list[str]] = {}
        for tid, name in result:
            artists_map.setdefault(tid, []).append(name)
        return artists_map
