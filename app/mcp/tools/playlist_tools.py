"""Playlist CRUD tools for DJ workflow MCP server.

list_playlists — paginated list with optional text search
get_playlist — single playlist by ref with detail stats
create_playlist — create new playlist
update_playlist — update playlist fields
delete_playlist — delete playlist
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import playlist_to_summary
from app.mcp.dependencies import get_session
from app.mcp.entity_finder import PlaylistFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types import PlaylistDetail
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.schemas.playlists import DjPlaylistCreate, DjPlaylistUpdate
from app.services.playlists import DjPlaylistService


def _make_svc(session: AsyncSession) -> DjPlaylistService:
    return DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )


async def _build_playlist_detail(playlist_id: int, session: AsyncSession) -> PlaylistDetail | None:
    """Build PlaylistDetail with track stats."""
    svc = _make_svc(session)
    try:
        pl_read = await svc.get(playlist_id)
    except Exception:
        return None

    items = await svc.list_items(playlist_id, limit=10000)
    track_count = items.total

    return PlaylistDetail(
        ref=f"local:{pl_read.playlist_id}",
        name=pl_read.name,
        track_count=track_count,
    )


def register_playlist_tools(mcp: FastMCP) -> None:
    """Register Playlist CRUD tools on the MCP server."""

    @mcp.tool(tags={"crud", "playlist"}, annotations={"readOnlyHint": True})
    async def list_playlists(
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """List playlists with optional text search.

        Returns paginated PlaylistSummary list + library stats.

        Args:
            limit: Max results per page (default 20, max 100).
            cursor: Pagination cursor from previous response.
            search: Optional text to filter by name.
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        repo = DjPlaylistRepository(session)

        if search:
            playlists, total = await repo.search_by_name(search, offset=offset, limit=clamped)
        else:
            playlists, total = await repo.list(offset=offset, limit=clamped)

        summaries = [playlist_to_summary(p) for p in playlists]
        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "playlist"}, annotations={"readOnlyHint": True})
    async def get_playlist(
        playlist_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Get playlist details by ref. Text refs return match list.

        Args:
            playlist_ref: Playlist reference — local:5, 5, or text query.
        """
        ref = parse_ref(playlist_ref)

        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            detail = await _build_playlist_detail(ref.local_id, session)
            if detail is None:
                return json.dumps({"error": "Playlist not found", "ref": playlist_ref})
            return await wrap_detail(detail, session)

        if ref.ref_type == RefType.TEXT:
            repo = DjPlaylistRepository(session)
            finder = PlaylistFinder(repo)
            found = await finder.find(ref, limit=20)
            return await wrap_list(found.entities, len(found.entities), 0, 20, session)

        return json.dumps({"error": "Platform refs not yet supported", "ref": playlist_ref})

    @mcp.tool(tags={"crud", "playlist"})
    async def create_playlist(
        name: str,
        source_app: int | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Create a new playlist in the local database.

        Args:
            name: Playlist name.
            source_app: Optional source app code (1-5).
        """
        svc = _make_svc(session)
        pl_read = await svc.create(DjPlaylistCreate(name=name, source_app=source_app))

        detail = await _build_playlist_detail(pl_read.playlist_id, session)
        return await wrap_action(
            success=True,
            message=f"Created playlist local:{pl_read.playlist_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "playlist"})
    async def update_playlist(
        playlist_ref: str,
        name: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Update playlist fields by ref.

        Args:
            playlist_ref: Playlist reference (must resolve to exact ID).
            name: New name (optional).
        """
        ref = parse_ref(playlist_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "update requires exact ref", "ref": playlist_ref})

        svc = _make_svc(session)
        await svc.update(ref.local_id, DjPlaylistUpdate(name=name))

        detail = await _build_playlist_detail(ref.local_id, session)
        return await wrap_action(
            success=True,
            message=f"Updated playlist local:{ref.local_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "playlist"})
    async def delete_playlist(
        playlist_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Delete a playlist by ref.

        Args:
            playlist_ref: Playlist reference (must resolve to exact ID).
        """
        ref = parse_ref(playlist_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "delete requires exact ref", "ref": playlist_ref})

        svc = _make_svc(session)
        await svc.delete(ref.local_id)

        return await wrap_action(
            success=True,
            message=f"Deleted playlist local:{ref.local_id}",
            session=session,
        )
