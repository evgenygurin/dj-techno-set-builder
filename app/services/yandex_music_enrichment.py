"""Enriches tracks with metadata from Yandex Music API.

Handles: provider linking, genre, artist, label, release creation.
Null-safe for missing album fields (labels, genre, etc.).
Uses ArtistRole.PRIMARY (int 0), not string "main".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music import YandexMusicClient
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
from app.models.ingestion import ProviderTrackId
from app.schemas.yandex_music import YmEnrichResponse
from app.utils.text_sort import sort_key

_PROVIDER_ID = 4  # ym — see providers seed data
_RATE_LIMIT_DELAY = 0.3  # seconds between YM API calls

logger = logging.getLogger(__name__)


class YandexMusicEnrichmentService:
    def __init__(
        self,
        session: AsyncSession,
        ym_client: YandexMusicClient,
    ) -> None:
        self.session = session
        self.ym_client = ym_client

    # ------ Public ------

    async def enrich_track(
        self,
        track_id: int,
        *,
        yandex_track_id: str,
    ) -> YmEnrichResponse:
        """Enrich a single track from Yandex Music data."""
        existing = await self._get_provider_link(track_id)
        if existing:
            return YmEnrichResponse(
                track_id=track_id,
                yandex_track_id=existing.provider_track_id,
                already_linked=True,
            )

        tracks_data = await self.ym_client.fetch_tracks([yandex_track_id])
        ym_track = tracks_data.get(yandex_track_id)
        if not ym_track:
            msg = f"Track {yandex_track_id} not found on Yandex Music"
            raise ValueError(msg)

        self.session.add(
            ProviderTrackId(
                track_id=track_id,
                provider_id=_PROVIDER_ID,
                provider_track_id=yandex_track_id,
            )
        )

        artist_names = await self._process_artists(track_id, ym_track.get("artists", []))

        genre_name = None
        label_name = None
        release_title = None
        albums = ym_track.get("albums", [])
        if albums:
            album = albums[0]
            genre_name = await self._process_genre(track_id, album)
            label_name, release_title = await self._process_release(track_id, album)

        await self.session.flush()

        return YmEnrichResponse(
            track_id=track_id,
            yandex_track_id=yandex_track_id,
            genre=genre_name,
            artists=artist_names,
            label=label_name,
            release_title=release_title,
        )

    async def enrich_batch(self, track_ids: list[int]) -> list[YmEnrichResponse]:
        """Enrich multiple tracks by auto-searching YM.

        Parses "Artist — Title" from track.title, searches YM, picks best
        match, calls enrich_track().
        """
        results: list[YmEnrichResponse] = []

        for tid in track_ids:
            stmt = select(Track).where(Track.track_id == tid)
            track = (await self.session.execute(stmt)).scalar_one_or_none()
            if not track:
                logger.warning("Track %d not found, skipping", tid)
                continue

            # Check if already enriched
            existing = await self._get_provider_link(tid)
            if existing:
                results.append(
                    YmEnrichResponse(
                        track_id=tid,
                        yandex_track_id=existing.provider_track_id,
                        already_linked=True,
                    )
                )
                continue

            # Parse "Artist — Title" format
            parts = track.title.split(" — ", 1)
            search_query = f"{parts[0]} {parts[1]}" if len(parts) == 2 else track.title

            # Search YM
            ym_results = await self.ym_client.search_tracks(search_query)
            if not ym_results:
                logger.warning("No YM results for track %d: %s", tid, track.title)
                continue

            ym_track_id = str(ym_results[0]["id"])
            result = await self.enrich_track(tid, yandex_track_id=ym_track_id)
            results.append(result)

            await asyncio.sleep(_RATE_LIMIT_DELAY)

        return results

    # ------ Helpers ------

    async def _get_provider_link(self, track_id: int) -> ProviderTrackId | None:
        stmt = select(ProviderTrackId).where(
            ProviderTrackId.track_id == track_id,
            ProviderTrackId.provider_id == _PROVIDER_ID,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _process_artists(self, track_id: int, ym_artists: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for ym_a in ym_artists:
            if ym_a.get("various"):
                continue
            name = ym_a["name"]
            names.append(name)
            artist = await self._get_or_create_artist(name)
            await self._link_track_artist(track_id, artist.artist_id, ArtistRole.PRIMARY)
        return names

    async def _process_genre(self, track_id: int, album: dict[str, Any]) -> str | None:
        genre_name: str | None = album.get("genre")
        if not genre_name:
            return None
        genre = await self._get_or_create_genre(genre_name)
        await self._link_track_genre(track_id, genre.genre_id)
        return genre_name

    async def _process_release(
        self, track_id: int, album: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        # Null-safe labels (problem #4 from plan)
        labels = album.get("labels", [])
        label_name = None
        label_id = None
        if labels:
            raw_label = labels[0]
            label_name = raw_label if isinstance(raw_label, str) else raw_label.get("name")
            if label_name:
                label = await self._get_or_create_label(label_name)
                label_id = label.label_id

        release_title = album.get("title")
        if release_title:
            release_date = album.get("releaseDate")
            rd = release_date[:10] if release_date else None
            year = album.get("year")
            precision = "day" if rd else ("year" if year else None)
            if not rd and year:
                rd = f"{year}-01-01"

            release = await self._get_or_create_release(
                title=release_title,
                label_id=label_id,
                release_date=rd,
                release_date_precision=precision,
            )
            track_pos = album.get("trackPosition", {})
            await self._link_track_release(
                track_id,
                release.release_id,
                track_number=track_pos.get("index"),
                disc_number=track_pos.get("volume"),
            )

        return label_name, release_title

    # ------ get_or_create helpers (all idempotent) ------

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
        self,
        *,
        title: str,
        label_id: int | None,
        release_date: str | None,
        release_date_precision: str | None,
    ) -> Release:
        stmt = select(Release).where(Release.title == title)
        release = (await self.session.execute(stmt)).scalar_one_or_none()
        if release:
            return release
        rd: date | None = None
        if release_date:
            rd = date.fromisoformat(release_date)
        release = Release(
            title=title,
            label_id=label_id,
            release_date=rd,
            release_date_precision=release_date_precision,
        )
        self.session.add(release)
        await self.session.flush()
        return release

    # ------ link helpers (skip if exists) ------

    async def _link_track_artist(self, track_id: int, artist_id: int, role: ArtistRole) -> None:
        stmt = select(TrackArtist).where(
            TrackArtist.track_id == track_id,
            TrackArtist.artist_id == artist_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackArtist(track_id=track_id, artist_id=artist_id, role=role.value))

    async def _link_track_genre(self, track_id: int, genre_id: int) -> None:
        stmt = select(TrackGenre).where(
            TrackGenre.track_id == track_id,
            TrackGenre.genre_id == genre_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            TrackGenre(
                track_id=track_id,
                genre_id=genre_id,
                source_provider_id=_PROVIDER_ID,
            )
        )

    async def _link_track_release(
        self,
        track_id: int,
        release_id: int,
        *,
        track_number: int | None,
        disc_number: int | None,
    ) -> None:
        stmt = select(TrackRelease).where(
            TrackRelease.track_id == track_id,
            TrackRelease.release_id == release_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            TrackRelease(
                track_id=track_id,
                release_id=release_id,
                track_number=track_number,
                disc_number=disc_number,
            )
        )
