"""Universal search + filter_tracks tools for DJ workflow MCP server.

search() — fan-out query to tracks, playlists, sets via entity finders.
filter_tracks() — SQL-level filtering by BPM, key, energy, with pagination.
Both return SearchResponse with categorized results + stats + library stats.
"""

from __future__ import annotations

import contextlib

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.dependencies import get_session
from app.mcp.entity_finder import ArtistFinder, PlaylistFinder, SetFinder, TrackFinder
from app.mcp.library_stats import get_library_stats
from app.mcp.pagination import encode_cursor, paginate_params
from app.mcp.refs import parse_ref
from app.mcp.types_v2 import (
    MatchStats,
    PaginationInfo,
    SearchResponse,
)
from app.repositories.artists import ArtistRepository
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.playlists import DjPlaylistRepository
from app.repositories.sets import DjSetRepository
from app.repositories.tracks import TrackRepository


def register_search_tools(mcp: FastMCP) -> None:
    """Register search and filter tools on the MCP server."""

    @mcp.tool(
        tags={"search"},
        annotations={"readOnlyHint": True},
    )
    async def search(
        query: str,
        scope: str = "all",
        limit: int = 20,
        cursor: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> SearchResponse:
        """Universal search across tracks, playlists, sets, and artists.

        Fans out the query to all entity finders and returns categorized
        results with library stats and pagination.

        Args:
            query: Search text — title, artist name, playlist name, etc.
                   Supports URN refs too: "local:42", "ym:12345".
            scope: Which entity types to search.
                   "all" | "tracks" | "playlists" | "sets" | "artists"
            limit: Max results per category (default 20, max 100).
            cursor: Opaque pagination cursor from a previous response.
        """
        offset, capped = paginate_params(cursor=cursor, limit=limit)

        ref = parse_ref(query)

        scopes = (
            ["tracks", "playlists", "sets", "artists"]
            if scope == "all"
            else [scope]
        )

        results: dict[str, list] = {}  # type: ignore[type-arg]
        total_matches: dict[str, int] = {}

        if "tracks" in scopes:
            finder = TrackFinder(TrackRepository(session))
            found = await finder.find(ref, limit=capped)
            results["tracks"] = [e.model_dump() for e in found.entities]
            total_matches["tracks"] = len(found.entities)

        if "playlists" in scopes:
            finder_pl = PlaylistFinder(DjPlaylistRepository(session))
            found = await finder_pl.find(ref, limit=capped)
            results["playlists"] = [e.model_dump() for e in found.entities]
            total_matches["playlists"] = len(found.entities)

        if "sets" in scopes:
            finder_set = SetFinder(DjSetRepository(session))
            found = await finder_set.find(ref, limit=capped)
            results["sets"] = [e.model_dump() for e in found.entities]
            total_matches["sets"] = len(found.entities)

        if "artists" in scopes:
            finder_art = ArtistFinder(ArtistRepository(session))
            found = await finder_art.find(ref, limit=capped)
            results["artists"] = [e.model_dump() for e in found.entities]
            total_matches["artists"] = len(found.entities)

        library = await get_library_stats(session)

        total = sum(total_matches.values())
        has_more = total > offset + capped
        next_cursor = encode_cursor(offset=offset + capped) if has_more else None

        return SearchResponse(
            results=results,
            stats=MatchStats(total_matches=total_matches),
            library=library,
            pagination=PaginationInfo(
                limit=capped,
                has_more=has_more,
                cursor=next_cursor,
            ),
        )

    @mcp.tool(
        tags={"search", "audio"},
        annotations={"readOnlyHint": True},
    )
    async def filter_tracks(
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        keys: list[str] | None = None,
        energy_min: float | None = None,
        energy_max: float | None = None,
        limit: int = 20,
        cursor: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> SearchResponse:
        """Filter tracks by audio feature criteria (SQL-level).

        Searches the local library using extracted audio features.
        Much faster than in-memory filtering for large libraries.

        Args:
            bpm_min: Minimum BPM (inclusive).
            bpm_max: Maximum BPM (inclusive).
            keys: Camelot key codes to match (e.g. ["5A", "9A", "7B"]).
            energy_min: Minimum integrated LUFS loudness.
            energy_max: Maximum integrated LUFS loudness.
            limit: Max results (default 20, max 100).
            cursor: Opaque pagination cursor from a previous response.
        """
        from app.utils.audio.camelot import camelot_to_key_code, key_code_to_camelot

        offset, capped = paginate_params(cursor=cursor, limit=limit)

        # Convert Camelot keys to key_codes for SQL filter
        key_codes: list[int] | None = None
        if keys:
            codes = [camelot_to_key_code(k) for k in keys]
            key_codes = [c for c in codes if c is not None]
            if not key_codes:
                key_codes = None

        repo = AudioFeaturesRepository(session)
        features_list, total = await repo.filter_by_criteria(
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            key_codes=key_codes,
            energy_min=energy_min,
            energy_max=energy_max,
            offset=offset,
            limit=capped,
        )

        # Batch-load track data for matched features
        track_repo = TrackRepository(session)
        track_ids = [f.track_id for f in features_list]
        artists_map = await track_repo.get_artists_for_tracks(track_ids)

        from app.mcp.types_v2 import TrackSummary

        entities = []
        for feat in features_list:
            track = await track_repo.get_by_id(feat.track_id)
            if not track:
                continue

            camelot_key: str | None = None
            with contextlib.suppress(ValueError, TypeError):
                camelot_key = key_code_to_camelot(feat.key_code)

            entities.append(
                TrackSummary(
                    ref=f"local:{track.track_id}",
                    title=track.title,
                    artist=", ".join(artists_map.get(track.track_id, [])) or "Unknown",
                    bpm=feat.bpm,
                    key=camelot_key,
                    energy_lufs=feat.lufs_i,
                    duration_ms=track.duration_ms,
                ).model_dump()
            )

        library = await get_library_stats(session)
        has_more = total > offset + capped
        next_cursor = encode_cursor(offset=offset + capped) if has_more else None

        return SearchResponse(
            results={"tracks": entities},
            stats=MatchStats(total_matches={"tracks": total}),
            library=library,
            pagination=PaginationInfo(
                limit=capped,
                has_more=has_more,
                cursor=next_cursor,
            ),
        )
