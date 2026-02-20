"""Entity resolution — find entities by ref (URN, text, ID).

Each entity type has its own Finder class. All return FindResult
with a list of matches (even for exact IDs — list of 0 or 1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.mcp.refs import ParsedRef, RefType
from app.mcp.types_v2 import (
    ArtistSummary,
    FindResult,
    PlaylistSummary,
    SetSummary,
    TrackSummary,
)

if TYPE_CHECKING:
    from app.repositories.artists import ArtistRepository
    from app.repositories.playlists import DjPlaylistRepository
    from app.repositories.sets import DjSetRepository
    from app.repositories.tracks import TrackRepository


class TrackFinder:
    """Resolve track refs to TrackSummary entities."""

    def __init__(self, track_repo: TrackRepository) -> None:
        self._repo = track_repo

    async def find(self, ref: ParsedRef, *, limit: int = 20) -> FindResult:
        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            return await self._find_by_id(ref.local_id)
        if ref.ref_type == RefType.TEXT and ref.query:
            return await self._find_by_text(ref.query, limit=limit)
        return FindResult(exact=False, entities=[], source="local")

    async def _find_by_id(self, track_id: int) -> FindResult:
        track = await self._repo.get_by_id(track_id)
        if track is None:
            return FindResult(exact=True, entities=[], source="local")

        artists = await self._repo.get_artists_for_tracks([track.track_id])
        artist_str = ", ".join(artists.get(track.track_id, []))

        summary = TrackSummary(
            ref=f"local:{track.track_id}",
            title=track.title,
            artist=artist_str or "Unknown",
            duration_ms=track.duration_ms,
        )
        return FindResult(exact=True, entities=[summary], source="local")

    async def _find_by_text(self, query: str, *, limit: int = 20) -> FindResult:
        tracks, _total = await self._repo.search_by_title(query, offset=0, limit=limit)
        if not tracks:
            return FindResult(exact=False, entities=[], source="local")

        track_ids = [t.track_id for t in tracks]
        artists_map = await self._repo.get_artists_for_tracks(track_ids)

        entities = [
            TrackSummary(
                ref=f"local:{t.track_id}",
                title=t.title,
                artist=", ".join(artists_map.get(t.track_id, [])) or "Unknown",
                duration_ms=t.duration_ms,
            )
            for t in tracks
        ]
        return FindResult(exact=False, entities=entities, source="local")


class PlaylistFinder:
    """Resolve playlist refs to PlaylistSummary entities."""

    def __init__(self, playlist_repo: DjPlaylistRepository) -> None:
        self._repo = playlist_repo

    async def find(self, ref: ParsedRef, *, limit: int = 20) -> FindResult:
        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            return await self._find_by_id(ref.local_id)
        if ref.ref_type == RefType.TEXT and ref.query:
            return await self._find_by_text(ref.query, limit=limit)
        return FindResult(exact=False, entities=[], source="local")

    async def _find_by_id(self, playlist_id: int) -> FindResult:
        playlist = await self._repo.get_by_id(playlist_id)
        if playlist is None:
            return FindResult(exact=True, entities=[], source="local")

        summary = PlaylistSummary(
            ref=f"local:{playlist.playlist_id}",
            name=playlist.name,
        )
        return FindResult(exact=True, entities=[summary], source="local")

    async def _find_by_text(self, query: str, *, limit: int = 20) -> FindResult:
        playlists, _total = await self._repo.search_by_name(
            query, offset=0, limit=limit
        )
        entities = [
            PlaylistSummary(
                ref=f"local:{p.playlist_id}",
                name=p.name,
            )
            for p in playlists
        ]
        return FindResult(exact=False, entities=entities, source="local")


class SetFinder:
    """Resolve set refs to SetSummary entities."""

    def __init__(self, set_repo: DjSetRepository) -> None:
        self._repo = set_repo

    async def find(self, ref: ParsedRef, *, limit: int = 20) -> FindResult:
        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            return await self._find_by_id(ref.local_id)
        if ref.ref_type == RefType.TEXT and ref.query:
            return await self._find_by_text(ref.query, limit=limit)
        return FindResult(exact=False, entities=[], source="local")

    async def _find_by_id(self, set_id: int) -> FindResult:
        dj_set = await self._repo.get_by_id(set_id)
        if dj_set is None:
            return FindResult(exact=True, entities=[], source="local")

        summary = SetSummary(
            ref=f"local:{dj_set.set_id}",
            name=dj_set.name,
        )
        return FindResult(exact=True, entities=[summary], source="local")

    async def _find_by_text(self, query: str, *, limit: int = 20) -> FindResult:
        sets, _total = await self._repo.search_by_name(query, offset=0, limit=limit)
        entities = [
            SetSummary(
                ref=f"local:{s.set_id}",
                name=s.name,
            )
            for s in sets
        ]
        return FindResult(exact=False, entities=entities, source="local")


class ArtistFinder:
    """Resolve artist refs to ArtistSummary entities."""

    def __init__(self, artist_repo: ArtistRepository) -> None:
        self._repo = artist_repo

    async def find(self, ref: ParsedRef, *, limit: int = 20) -> FindResult:
        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            return await self._find_by_id(ref.local_id)
        if ref.ref_type == RefType.TEXT and ref.query:
            return await self._find_by_text(ref.query, limit=limit)
        return FindResult(exact=False, entities=[], source="local")

    async def _find_by_id(self, artist_id: int) -> FindResult:
        artist = await self._repo.get_by_id(artist_id)
        if artist is None:
            return FindResult(exact=True, entities=[], source="local")

        summary = ArtistSummary(
            ref=f"local:{artist.artist_id}",
            name=artist.name,
        )
        return FindResult(exact=True, entities=[summary], source="local")

    async def _find_by_text(self, query: str, *, limit: int = 20) -> FindResult:
        artists, _total = await self._repo.search_by_name(
            query, offset=0, limit=limit
        )
        entities = [
            ArtistSummary(
                ref=f"local:{a.artist_id}",
                name=a.name,
            )
            for a in artists
        ]
        return FindResult(exact=False, entities=entities, source="local")
