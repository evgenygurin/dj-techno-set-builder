"""Track CRUD tools for DJ workflow MCP server.

list_tracks — paginated list with optional text search
get_track — single track by ref (ID returns detail, text returns match list)
create_track — create new track in local DB
update_track — update track fields by ref
delete_track — delete track by ref
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.mcp.converters import track_to_detail, track_to_summary
from app.mcp.dependencies import get_session
from app.mcp.entity_finder import TrackFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types import TrackDetail
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.schemas.tracks import TrackCreate, TrackUpdate
from app.services.tracks import TrackService


async def _build_track_detail(track_id: int, session: AsyncSession) -> TrackDetail | None:
    """Fetch all related data and build TrackDetail."""
    repo = TrackRepository(session)
    features_repo = AudioFeaturesRepository(session)

    track = await repo.get_by_id(track_id)
    if track is None:
        return None

    artists_map = await repo.get_artists_for_tracks([track_id])
    genres_map = await repo.get_genres_for_tracks([track_id])
    labels_map = await repo.get_labels_for_tracks([track_id])
    albums_map = await repo.get_albums_for_tracks([track_id])
    features = await features_repo.get_by_track(track_id)

    return track_to_detail(
        track,
        artists_map=artists_map,
        features=features,
        genres=genres_map.get(track_id, []),
        labels=labels_map.get(track_id, []),
        albums=albums_map.get(track_id, []),
    )


def register_track_tools(mcp: FastMCP) -> None:
    """Register Track CRUD tools on the MCP server."""

    @mcp.tool(tags={"crud", "track"}, annotations={"readOnlyHint": True})
    async def list_tracks(
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """List tracks with optional text search.

        Returns paginated TrackSummary list + library stats.

        Args:
            limit: Max results per page (default 20, max 100).
            cursor: Pagination cursor from previous response.
            search: Optional text to filter by title (fuzzy match).
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        repo = TrackRepository(session)

        if search:
            tracks, total = await repo.search_by_title(search, offset=offset, limit=clamped)
        else:
            tracks, total = await repo.list(offset=offset, limit=clamped)

        track_ids = [t.track_id for t in tracks]
        artists_map = await repo.get_artists_for_tracks(track_ids) if track_ids else {}

        summaries = [track_to_summary(t, artists_map) for t in tracks]
        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "track"}, annotations={"readOnlyHint": True})
    async def get_track(
        track_ref: str | int,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Get track details by ref.

        Exact refs (local:42, 42) return full TrackDetail.
        Text refs ("Boris Brejcha") return ranked list of TrackSummary matches.

        Args:
            track_ref: Track reference — local:42, 42, ym:12345, or text query.
        """
        ref = parse_ref(track_ref)

        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            detail = await _build_track_detail(ref.local_id, session)
            if detail is None:
                return json.dumps({"error": "Track not found", "ref": track_ref})
            return await wrap_detail(detail, session)

        if ref.ref_type == RefType.TEXT:
            repo = TrackRepository(session)
            finder = TrackFinder(repo, repo)
            found = await finder.find(ref, limit=20)
            return await wrap_list(found.entities, len(found.entities), 0, 20, session)

        return json.dumps({"error": "Platform refs not yet supported", "ref": track_ref})

    @mcp.tool(tags={"crud", "track"})
    async def create_track(
        title: str,
        duration_ms: int,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Create a new track in the local database.

        Args:
            title: Track title.
            duration_ms: Duration in milliseconds (must be > 0).
        """
        svc = TrackService(TrackRepository(session))
        track_read = await svc.create(TrackCreate(title=title, duration_ms=duration_ms))

        detail = await _build_track_detail(track_read.track_id, session)
        return await wrap_action(
            success=True,
            message=f"Created track local:{track_read.track_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "track"})
    async def update_track(
        track_ref: str | int,
        title: str | None = None,
        duration_ms: int | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Update track fields by ref.

        Args:
            track_ref: Track reference (must resolve to exact ID).
            title: New title (optional).
            duration_ms: New duration in ms (optional).
        """
        ref = parse_ref(track_ref)

        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps(
                {"error": "update requires exact ref (local:N or N)", "ref": track_ref}
            )

        svc = TrackService(TrackRepository(session))
        update_data = TrackUpdate(title=title, duration_ms=duration_ms)
        await svc.update(ref.local_id, update_data)

        detail = await _build_track_detail(ref.local_id, session)
        return await wrap_action(
            success=True,
            message=f"Updated track local:{ref.local_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "track"})
    async def delete_track(
        track_ref: str | int,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Delete a track by ref.

        Args:
            track_ref: Track reference (must resolve to exact ID).
        """
        ref = parse_ref(track_ref)

        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps(
                {"error": "delete requires exact ref (local:N or N)", "ref": track_ref}
            )

        svc = TrackService(TrackRepository(session))
        try:
            await svc.delete(ref.local_id)
        except NotFoundError:
            return json.dumps({"error": f"Track {ref.local_id} not found"})

        return await wrap_action(
            success=True,
            message=f"Deleted track local:{ref.local_id}",
            session=session,
        )
