"""Universal search + filter tools (Phase 1)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories.artists import ArtistRepository
from app.infrastructure.repositories.playlists import DjPlaylistRepository
from app.infrastructure.repositories.sets import DjSetRepository
from app.infrastructure.repositories.tracks import TrackRepository
from app.mcp.dependencies import get_session
from app.mcp.entity_finder import ArtistFinder, PlaylistFinder, SetFinder, TrackFinder
from app.mcp.library_stats import get_library_stats
from app.mcp.pagination import encode_cursor, paginate_params
from app.mcp.refs import parse_ref
from app.mcp.types import (
    EntityListResponse,
    MatchStats,
    PaginationInfo,
    SearchResponse,
)


def register_search_tools(mcp: FastMCP) -> None:
    """Register universal search + filter tools."""

    @mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
    async def search(
        query: str,
        scope: str = "all",
        limit: int = 20,
        cursor: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> SearchResponse:
        """Universal search across all entities and platforms.

        Searches local DB (tracks, playlists, sets, artists) by fuzzy text match.
        Returns categorized results + background statistics + pagination.

        Args:
            query: Search text — name, title, artist, anything.
            scope: "all" | "tracks" | "playlists" | "sets" | "artists".
            limit: Max results per category (default 20, max 100).
            cursor: Pagination cursor from previous response.
        """
        if not query or not query.strip():
            raise ToolError("query cannot be empty")

        offset, clamped_limit = paginate_params(cursor=cursor, limit=limit)
        ref = parse_ref(query)

        results: dict[str, list[dict[str, Any]]] = {}
        total_matches: dict[str, int] = {}

        track_repo = TrackRepository(session)
        playlist_repo = DjPlaylistRepository(session)
        set_repo = DjSetRepository(session)
        artist_repo = ArtistRepository(session)

        if scope in ("all", "tracks"):
            finder = TrackFinder(track_repo, track_repo)
            found = await finder.find(ref, limit=clamped_limit)
            results["tracks"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["tracks"] = len(found.entities)

        if scope in ("all", "playlists"):
            finder_pl = PlaylistFinder(playlist_repo)
            found = await finder_pl.find(ref, limit=clamped_limit)
            results["playlists"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["playlists"] = len(found.entities)

        if scope in ("all", "sets"):
            finder_set = SetFinder(set_repo)
            found = await finder_set.find(ref, limit=clamped_limit)
            results["sets"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["sets"] = len(found.entities)

        if scope in ("all", "artists"):
            finder_art = ArtistFinder(artist_repo)
            found = await finder_art.find(ref, limit=clamped_limit)
            results["artists"] = [e.model_dump(exclude_none=True) for e in found.entities]
            total_matches["artists"] = len(found.entities)

        library = await get_library_stats(session)

        has_more = any(len(v) >= clamped_limit for v in results.values())
        next_cursor = encode_cursor(offset=offset + clamped_limit) if has_more else None

        response = SearchResponse(
            results=results,
            stats=MatchStats(total_matches=total_matches),
            library=library,
            pagination=PaginationInfo(limit=clamped_limit, has_more=has_more, cursor=next_cursor),
        )
        return response

    @mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
    async def filter_tracks(
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        key_code_min: int | None = None,
        key_code_max: int | None = None,
        energy_min: float | None = None,
        energy_max: float | None = None,
        kick_min: float | None = None,
        kick_max: float | None = None,
        hp_ratio_min: float | None = None,
        hp_ratio_max: float | None = None,
        centroid_min: float | None = None,
        centroid_max: float | None = None,
        camelot_keys: list[str] | None = None,
        limit: int = 50,
        cursor: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> EntityListResponse:
        """Filter tracks by audio parameters (BPM, key, energy, spectral).

        Uses SQL-level filtering — efficient for large libraries.
        Returns paginated track list with BPM/key/energy populated.

        Args:
            bpm_min: Minimum BPM (e.g. 138.0).
            bpm_max: Maximum BPM (e.g. 145.0).
            key_code_min: Minimum key_code (0-23).
            key_code_max: Maximum key_code (0-23).
            energy_min: Minimum energy_mean (0.0-1.0, e.g. 0.3).
            energy_max: Maximum energy_mean (0.0-1.0, e.g. 0.8).
            kick_min: Minimum kick_prominence (0.0-1.0).
            kick_max: Maximum kick_prominence (0.0-1.0).
            hp_ratio_min: Minimum harmonic/percussive ratio (unbounded, avg ~2.2).
            hp_ratio_max: Maximum harmonic/percussive ratio (e.g. 8.0).
            centroid_min: Minimum spectral centroid in Hz (e.g. 300).
            centroid_max: Maximum spectral centroid in Hz (e.g. 5000).
            camelot_keys: Filter by Camelot keys, e.g. ["4A","5A","4B"].
            limit: Max results (default 50, max 100).
            cursor: Pagination cursor.
        """
        from app.infrastructure.repositories.audio_features import AudioFeaturesRepository
        from app.mcp.converters import track_to_summary
        from app.mcp.response import wrap_list

        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        features_repo = AudioFeaturesRepository(session)
        track_repo = TrackRepository(session)

        # Build key_codes list from range if provided
        key_codes: list[int] | None = None
        if key_code_min is not None or key_code_max is not None:
            lo = key_code_min if key_code_min is not None else 0
            hi = key_code_max if key_code_max is not None else 23
            key_codes = list(range(lo, hi + 1))

        features_list, total = await features_repo.filter_by_criteria(
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            key_codes=key_codes,
            energy_min=energy_min,
            energy_max=energy_max,
            kick_min=kick_min,
            kick_max=kick_max,
            hp_ratio_min=hp_ratio_min,
            hp_ratio_max=hp_ratio_max,
            centroid_min=centroid_min,
            centroid_max=centroid_max,
            camelot_keys=camelot_keys,
            offset=offset,
            limit=clamped,
        )

        track_ids = [f.track_id for f in features_list]
        tracks_by_id = {}
        artists_map: dict[int, list[str]] = {}
        if track_ids:
            for tid in track_ids:
                t = await track_repo.get_by_id(tid)
                if t:
                    tracks_by_id[tid] = t
            artists_map = await track_repo.get_artists_for_tracks(track_ids)

        summaries = []
        for f in features_list:
            track = tracks_by_id.get(f.track_id)
            if track:
                summaries.append(track_to_summary(track, artists_map, features=f))

        return await wrap_list(summaries, total, offset, clamped, session)
