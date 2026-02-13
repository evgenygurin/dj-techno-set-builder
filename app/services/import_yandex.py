"""Orchestrator for importing/enriching tracks from Yandex Music."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Artist,
    Genre,
    Label,
    Release,
    Track,
    TrackArtist,
    TrackGenre,
    TrackRelease,
)
from app.models.enums import ArtistRole
from app.models.ingestion import ProviderTrackId, RawProviderResponse
from app.repositories.yandex_metadata import YandexMetadataRepository
from app.services.base import BaseService
from app.services.yandex_music_client import ParsedYmTrack, YandexMusicClient, parse_ym_track
from app.utils.text_sort import sort_key

_PROVIDER_ID = 4  # yandex_music — seeded in schema_v6.sql

logger = logging.getLogger(__name__)


class ImportYandexService(BaseService):
    def __init__(
        self,
        session: AsyncSession,
        ym_client: YandexMusicClient,
    ) -> None:
        super().__init__()
        self.session = session
        self.ym = ym_client
        self.ym_repo = YandexMetadataRepository(session)

    async def enrich_track(self, track_id: int) -> bool:
        """Search YM by track title, enrich metadata. Returns True if found."""
        track = await self._get_track(track_id)
        if not track:
            return False

        # Skip if already enriched
        existing = await self.ym_repo.get_by_track_id(track_id)
        if existing:
            return True

        # Search YM
        ym_tracks = await self.ym.search_tracks(track.title)
        if not ym_tracks:
            return False

        parsed = parse_ym_track(ym_tracks[0])
        await self._apply_enrichment(track, parsed)
        return True

    async def enrich_batch(self, track_ids: list[int]) -> dict[str, Any]:
        """Enrich multiple tracks. Returns {total, enriched, not_found, errors}."""
        enriched = 0
        not_found = 0
        errors: list[str] = []

        for tid in track_ids:
            try:
                ok = await self.enrich_track(tid)
                if ok:
                    enriched += 1
                else:
                    not_found += 1
            except Exception as e:
                errors.append(f"Track {tid}: {e}")
                logger.warning("Enrich failed for track %d: %s", tid, e)

        await self.session.flush()
        return {
            "total": len(track_ids),
            "enriched": enriched,
            "not_found": not_found,
            "errors": errors,
        }

    async def _get_track(self, track_id: int) -> Track | None:
        stmt = select(Track).where(Track.track_id == track_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _apply_enrichment(self, track: Track, parsed: ParsedYmTrack) -> None:
        """Create YandexMetadata + link Artist/Genre/Label/Release."""
        # 1. YandexMetadata
        await self.ym_repo.upsert(
            track_id=track.track_id,
            yandex_track_id=parsed.yandex_track_id,
            yandex_album_id=parsed.yandex_album_id,
            album_title=parsed.album_title,
            album_type=parsed.album_type,
            album_genre=parsed.album_genre,
            album_year=parsed.album_year,
            label_name=parsed.label_name,
            release_date=parsed.release_date,
            duration_ms=parsed.duration_ms,
            cover_uri=parsed.cover_uri,
            explicit=parsed.explicit,
            extra=parsed.raw,
        )

        # 2. ProviderTrackId
        await self._link_provider_track(track.track_id, parsed.yandex_track_id)

        # 3. Artists
        for name in parsed.artist_names:
            artist = await self._get_or_create_artist(name)
            await self._link_track_artist(track.track_id, artist.artist_id, ArtistRole.PRIMARY)

        # 4. Genre
        if parsed.album_genre:
            genre = await self._get_or_create_genre(parsed.album_genre)
            await self._link_track_genre(track.track_id, genre.genre_id)

        # 5. Label + Release
        label_id = None
        if parsed.label_name:
            label = await self._get_or_create_label(parsed.label_name)
            label_id = label.label_id

        if parsed.album_title:
            release = await self._get_or_create_release(
                title=parsed.album_title,
                label_id=label_id,
                release_date=parsed.release_date,
                year=parsed.album_year,
            )
            await self._link_track_release(track.track_id, release.release_id)

        # 6. Raw response (for debugging)
        raw = RawProviderResponse(
            track_id=track.track_id,
            provider_id=_PROVIDER_ID,
            provider_track_id=parsed.yandex_track_id,
            endpoint="search",
            payload=parsed.raw,
        )
        self.session.add(raw)
        await self.session.flush()

    # --- Get-or-create helpers ---
    async def _get_or_create_artist(self, name: str) -> Artist:
        stmt = select(Artist).where(Artist.name == name)
        artist = (await self.session.execute(stmt)).scalar_one_or_none()
        if artist:
            return artist
        artist = Artist(name=name, name_sort=sort_key(name))
        self.session.add(artist)
        await self.session.flush()
        return artist

    async def _get_or_create_genre(self, name: str) -> Genre:
        stmt = select(Genre).where(Genre.name == name)
        genre = (await self.session.execute(stmt)).scalar_one_or_none()
        if genre:
            return genre
        genre = Genre(name=name)
        self.session.add(genre)
        await self.session.flush()
        return genre

    async def _get_or_create_label(self, name: str) -> Label:
        stmt = select(Label).where(Label.name == name)
        label = (await self.session.execute(stmt)).scalar_one_or_none()
        if label:
            return label
        label = Label(name=name, name_sort=sort_key(name))
        self.session.add(label)
        await self.session.flush()
        return label

    async def _get_or_create_release(
        self, *, title: str, label_id: int | None, release_date: str | None, year: int | None
    ) -> Release:
        stmt = select(Release).where(Release.title == title)
        release = (await self.session.execute(stmt)).scalar_one_or_none()
        if release:
            return release
        precision = "day" if release_date else ("year" if year else None)
        date_val: date | None = None
        if release_date:
            date_val = date.fromisoformat(release_date)
        elif year:
            date_val = date(year, 1, 1)
        release = Release(
            title=title,
            label_id=label_id,
            release_date=date_val,
            release_date_precision=precision,
        )
        self.session.add(release)
        await self.session.flush()
        return release

    # --- Link helpers (idempotent) ---
    async def _link_provider_track(self, track_id: int, ym_id: str) -> None:
        stmt = select(ProviderTrackId).where(
            ProviderTrackId.track_id == track_id,
            ProviderTrackId.provider_id == _PROVIDER_ID,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            ProviderTrackId(track_id=track_id, provider_id=_PROVIDER_ID, provider_track_id=ym_id)
        )
        await self.session.flush()

    async def _link_track_artist(self, track_id: int, artist_id: int, role: ArtistRole) -> None:
        stmt = select(TrackArtist).where(
            TrackArtist.track_id == track_id, TrackArtist.artist_id == artist_id
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackArtist(track_id=track_id, artist_id=artist_id, role=role.value))
        await self.session.flush()

    async def _link_track_genre(self, track_id: int, genre_id: int) -> None:
        stmt = select(TrackGenre).where(
            TrackGenre.track_id == track_id,
            TrackGenre.genre_id == genre_id,
            TrackGenre.source_provider_id == _PROVIDER_ID,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            TrackGenre(track_id=track_id, genre_id=genre_id, source_provider_id=_PROVIDER_ID)
        )
        await self.session.flush()

    async def _link_track_release(self, track_id: int, release_id: int) -> None:
        stmt = select(TrackRelease).where(
            TrackRelease.track_id == track_id, TrackRelease.release_id == release_id
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackRelease(track_id=track_id, release_id=release_id))
        await self.session.flush()
