from typing import Any

from sqlalchemy import select

from app.core.models.catalog import (
    Artist,
    Genre,
    Label,
    Release,
    Track,
    TrackArtist,
    TrackGenre,
    TrackRelease,
)
from app.infrastructure.repositories.base import BaseRepository


class TrackRepository(BaseRepository[Track]):
    model = Track

    async def search_by_title(
        self, query: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Track], int]:
        filters: list[Any] = [Track.title.ilike(f"%{query}%")]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def get_artists_for_tracks(
        self,
        track_ids: list[int],
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

    async def get_genres_for_tracks(
        self,
        track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load genre names for given track IDs."""
        if not track_ids:
            return {}
        stmt = (
            select(TrackGenre.track_id, Genre.name)
            .join(Genre, TrackGenre.genre_id == Genre.genre_id)
            .where(TrackGenre.track_id.in_(track_ids))
            .order_by(TrackGenre.track_id)
        )
        result = await self.session.execute(stmt)
        genres_map: dict[int, list[str]] = {}
        for tid, name in result:
            genres_map.setdefault(tid, []).append(name)
        return genres_map

    async def get_labels_for_tracks(
        self,
        track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load label names for given track IDs (via releases)."""
        if not track_ids:
            return {}
        stmt = (
            select(TrackRelease.track_id, Label.name)
            .join(Release, TrackRelease.release_id == Release.release_id)
            .join(Label, Release.label_id == Label.label_id)
            .where(TrackRelease.track_id.in_(track_ids))
            .order_by(TrackRelease.track_id)
            .distinct()
        )
        result = await self.session.execute(stmt)
        labels_map: dict[int, list[str]] = {}
        for tid, name in result:
            labels_map.setdefault(tid, []).append(name)
        return labels_map

    async def get_albums_for_tracks(
        self,
        track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load album/release titles for given track IDs."""
        if not track_ids:
            return {}
        stmt = (
            select(TrackRelease.track_id, Release.title)
            .join(Release, TrackRelease.release_id == Release.release_id)
            .where(TrackRelease.track_id.in_(track_ids))
            .order_by(TrackRelease.track_id)
        )
        result = await self.session.execute(stmt)
        albums_map: dict[int, list[str]] = {}
        for tid, title in result:
            albums_map.setdefault(tid, []).append(title)
        return albums_map
