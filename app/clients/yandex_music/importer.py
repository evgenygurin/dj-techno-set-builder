"""Import tracks from Yandex Music — search, fetch metadata, create all entities.

One class does everything: Track + Artist + Genre + Label + Release +
ProviderTrackId + YandexMetadata. No separate "enrichment" step.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music.client import YandexMusicClient
from app.clients.yandex_music.types import ParsedYmTrack, parse_ym_track
from app.errors import NotFoundError
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
from app.repositories.providers import ProviderRepository
from app.repositories.yandex_metadata import YandexMetadataRepository
from app.services.base import BaseService
from app.utils.text_sort import sort_key

_PROVIDER_CODE = "ym"
_RATE_LIMIT_DELAY = 0.3

logger = logging.getLogger(__name__)


class ImportYandexService(BaseService):
    """Import and link tracks from Yandex Music.

    Two modes:
    - import_by_search(track_id) — search YM by track title, pick first match
    - import_by_ym_id(track_id, ym_id) — fetch by exact YM track ID

    Both create all related entities (artists, genre, label, release)
    and link them to the local track in one pass.

    Lifecycle: create per-request, discard after. Session would leak otherwise.
    """

    def __init__(self, session: AsyncSession, ym_client: YandexMusicClient) -> None:
        super().__init__()
        self.session = session
        self.ym = ym_client
        self.ym_repo = YandexMetadataRepository(session)
        self._provider_repo = ProviderRepository(session)
        self._provider_id: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def import_by_search(self, track_id: int) -> bool:
        """Search YM by track title, import metadata. Returns True if found."""
        track = await self._require_track(track_id)

        if await self._already_linked(track_id):
            return True

        ym_tracks = await self.ym.search_tracks(track.title)
        if not ym_tracks:
            return False

        parsed = parse_ym_track(ym_tracks[0])
        await self._apply(track, parsed)
        return True

    async def import_by_ym_id(self, track_id: int, ym_track_id: str) -> dict[str, Any]:
        """Import by exact YM ID. Returns summary dict."""
        if await self._already_linked(track_id):
            return {"track_id": track_id, "yandex_track_id": ym_track_id, "already_linked": True}

        tracks_data = await self.ym.fetch_tracks([ym_track_id])
        ym_track = tracks_data.get(ym_track_id)
        if not ym_track:
            msg = f"Track {ym_track_id} not found on Yandex Music"
            raise ValueError(msg)

        track = await self._require_track(track_id)
        parsed = parse_ym_track(ym_track)
        await self._apply(track, parsed)

        return {
            "track_id": track_id,
            "yandex_track_id": ym_track_id,
            "artists": parsed.artist_names,
            "genre": parsed.album_genre,
            "label": parsed.label_name,
            "release_title": parsed.album_title,
        }

    async def import_batch(self, track_ids: list[int]) -> dict[str, Any]:
        """Import multiple tracks by auto-searching YM. Returns stats."""
        imported = 0
        not_found = 0
        already = 0
        errors: list[str] = []

        for tid in track_ids:
            try:
                if await self._already_linked(tid):
                    already += 1
                    continue
                ok = await self.import_by_search(tid)
                if ok:
                    imported += 1
                else:
                    not_found += 1
            except (httpx.HTTPStatusError, httpx.ConnectError, NotFoundError, ValueError) as e:
                errors.append(f"Track {tid}: {e}")
                logger.warning("Import failed for track %d: %s", tid, e)

            await asyncio.sleep(_RATE_LIMIT_DELAY)

        await self.session.flush()
        return {
            "total": len(track_ids),
            "imported": imported,
            "not_found": not_found,
            "already_linked": already,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Core: apply all metadata from parsed YM track
    # ------------------------------------------------------------------

    async def _apply(self, track: Track, parsed: ParsedYmTrack) -> None:
        """Create YandexMetadata + link Artist/Genre/Label/Release in one pass."""
        provider_id = await self._resolve_provider_id()

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
        await self._link_provider(track.track_id, parsed.yandex_track_id, provider_id)

        # 3. Artists
        for name in parsed.artist_names:
            artist = await self._get_or_create_artist(name)
            await self._link_track_artist(track.track_id, artist.artist_id)

        # 4. Genre
        if parsed.album_genre:
            genre = await self._get_or_create_genre(parsed.album_genre)
            await self._link_track_genre(track.track_id, genre.genre_id, provider_id)

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

        # 6. Raw response
        self.session.add(
            RawProviderResponse(
                track_id=track.track_id,
                provider_id=provider_id,
                provider_track_id=parsed.yandex_track_id,
                endpoint="search",
                payload=parsed.raw,
            )
        )
        await self.session.flush()

    # ------------------------------------------------------------------
    # Helpers: get-or-create (idempotent)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Helpers: link (skip if exists)
    # ------------------------------------------------------------------

    async def _link_provider(self, track_id: int, ym_id: str, provider_id: int) -> None:
        stmt = select(ProviderTrackId).where(
            ProviderTrackId.track_id == track_id,
            ProviderTrackId.provider_id == provider_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            ProviderTrackId(track_id=track_id, provider_id=provider_id, provider_track_id=ym_id)
        )
        await self.session.flush()

    async def _link_track_artist(self, track_id: int, artist_id: int) -> None:
        stmt = select(TrackArtist).where(
            TrackArtist.track_id == track_id, TrackArtist.artist_id == artist_id
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            TrackArtist(track_id=track_id, artist_id=artist_id, role=ArtistRole.PRIMARY.value)
        )

    async def _link_track_genre(self, track_id: int, genre_id: int, provider_id: int) -> None:
        stmt = select(TrackGenre).where(
            TrackGenre.track_id == track_id,
            TrackGenre.genre_id == genre_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(
            TrackGenre(track_id=track_id, genre_id=genre_id, source_provider_id=provider_id)
        )

    async def _link_track_release(self, track_id: int, release_id: int) -> None:
        stmt = select(TrackRelease).where(
            TrackRelease.track_id == track_id, TrackRelease.release_id == release_id
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackRelease(track_id=track_id, release_id=release_id))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _require_track(self, track_id: int) -> Track:
        stmt = select(Track).where(Track.track_id == track_id)
        track = (await self.session.execute(stmt)).scalar_one_or_none()
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        return track

    async def _already_linked(self, track_id: int) -> bool:
        provider_id = await self._resolve_provider_id()
        stmt = select(ProviderTrackId).where(
            ProviderTrackId.track_id == track_id,
            ProviderTrackId.provider_id == provider_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def _resolve_provider_id(self) -> int:
        if self._provider_id is not None:
            return self._provider_id
        provider = await self._provider_repo.get_by_code(_PROVIDER_CODE)
        if provider is None:
            raise RuntimeError(
                f"Provider '{_PROVIDER_CODE}' not found. Run migrations or seed providers."
            )
        self._provider_id = provider.provider_id
        return self._provider_id
