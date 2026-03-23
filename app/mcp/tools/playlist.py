"""Playlist CRUD tools for DJ workflow MCP server."""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import NotFoundError
from app.mcp.converters import playlist_to_summary
from app.mcp.dependencies import get_playlist_service, get_session, get_ym_client
from app.mcp.entity_finder import PlaylistFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types import ActionResponse, EntityDetailResponse, EntityListResponse, PlaylistDetail
from app.schemas.playlists import DjPlaylistCreate, DjPlaylistUpdate
from app.services.playlists import DjPlaylistService
from app.services.yandex_music_client import YandexMusicClient

logger = logging.getLogger(__name__)


async def _build_playlist_detail(
    playlist_id: int,
    svc: DjPlaylistService,
) -> PlaylistDetail | None:
    """Build PlaylistDetail with track stats."""
    playlist = await svc.repo.get_by_id(playlist_id)
    if playlist is None:
        return None
    track_count = await svc.get_track_count(playlist_id)
    return PlaylistDetail(
        ref=f"local:{playlist.playlist_id}",
        name=playlist.name,
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
        svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> EntityListResponse:
        """List playlists with optional text search.

        Args:
            limit: Max results per page (default 20, max 100).
            cursor: Pagination cursor from previous response.
            search: Optional text to filter by name.
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)

        if search:
            playlists, total = await svc.repo.search_by_name(
                search,
                offset=offset,
                limit=clamped,
            )
        else:
            playlists, total = await svc.repo.list(offset=offset, limit=clamped)

        counts = await svc.item_repo.get_counts_batch(
            [p.playlist_id for p in playlists],
        )
        summaries = [
            playlist_to_summary(p, item_count=counts.get(p.playlist_id, 0)) for p in playlists
        ]
        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "playlist"}, annotations={"readOnlyHint": True})
    async def get_playlist(
        playlist_ref: str | int,
        session: AsyncSession = Depends(get_session),
        svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> EntityDetailResponse | EntityListResponse:
        """Get playlist details by ref. Text refs return match list.

        Args:
            playlist_ref: Playlist reference — local:5, 5, or text query.
        """
        ref = parse_ref(playlist_ref)

        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            detail = await _build_playlist_detail(ref.local_id, svc)
            if detail is None:
                raise ToolError(f"Playlist not found: {playlist_ref}")
            return await wrap_detail(detail, session)

        if ref.ref_type == RefType.TEXT:
            finder = PlaylistFinder(svc.repo)
            found = await finder.find(ref, limit=20)
            return await wrap_list(
                found.entities,
                len(found.entities),
                0,
                20,
                session,
            )

        raise ToolError(f"Platform refs not yet supported: {playlist_ref}")

    @mcp.tool(tags={"crud", "playlist"})
    async def create_playlist(
        name: str,
        source_app: int | None = None,
        session: AsyncSession = Depends(get_session),
        svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> ActionResponse:
        """Create a new playlist.

        Args:
            name: Playlist name.
            source_app: Optional source app code (1-5).
        """
        pl_read = await svc.create(
            DjPlaylistCreate(name=name, source_app=source_app),
        )
        detail = await _build_playlist_detail(pl_read.playlist_id, svc)
        return await wrap_action(
            success=True,
            message=f"Created playlist local:{pl_read.playlist_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "playlist"})
    async def update_playlist(
        playlist_ref: str | int,
        name: str | None = None,
        session: AsyncSession = Depends(get_session),
        svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> ActionResponse:
        """Update playlist fields by ref.

        Args:
            playlist_ref: Playlist reference (must resolve to exact ID).
            name: New name (optional).
        """
        ref = parse_ref(playlist_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            raise ToolError(f"update requires exact ref: {playlist_ref}")

        try:
            await svc.update(ref.local_id, DjPlaylistUpdate(name=name))
        except NotFoundError:
            raise ToolError(f"Playlist {ref.local_id} not found") from None

        detail = await _build_playlist_detail(ref.local_id, svc)
        return await wrap_action(
            success=True,
            message=f"Updated playlist local:{ref.local_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "playlist"}, annotations={"destructiveHint": True})
    async def delete_playlist(
        playlist_ref: str | int,
        session: AsyncSession = Depends(get_session),
        svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> ActionResponse:
        """Delete a playlist by ref.

        Args:
            playlist_ref: Playlist reference (must resolve to exact ID).
        """
        ref = parse_ref(playlist_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            raise ToolError(f"delete requires exact ref: {playlist_ref}")

        try:
            await svc.delete(ref.local_id)
        except NotFoundError:
            raise ToolError(f"Playlist {ref.local_id} not found") from None

        return await wrap_action(
            success=True,
            message=f"Deleted playlist local:{ref.local_id}",
            session=session,
        )

    @mcp.tool(tags={"sync", "yandex"})
    async def populate_from_ym(
        playlist_id: int,
        ym_kind: int,
        ctx: Context,
        svc: DjPlaylistService = Depends(get_playlist_service),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Populate a local playlist with tracks from a YM playlist.

        Args:
            playlist_id: Local playlist ID to populate.
            ym_kind: YM playlist kind (numeric ID).
        """
        user_id = settings.yandex_music_user_id
        await ctx.info(f"Fetching tracks from YM playlist kind={ym_kind}...")

        ym_tracks = await ym_client.fetch_playlist_tracks(
            user_id=str(user_id),
            kind=str(ym_kind),
        )
        total_ym = len(ym_tracks)

        ym_ids: list[str] = []
        for item in ym_tracks:
            track_obj = item.get("track", item)
            tid = track_obj.get("id")
            if tid is not None:
                ym_ids.append(str(tid))

        if not ym_ids:
            return {"added": 0, "skipped": 0, "total_ym": total_ym}

        matched_track_ids = await svc.match_ym_ids_to_track_ids(ym_ids)
        added, skipped = await svc.populate_from_track_ids(
            playlist_id,
            matched_track_ids,
        )
        await svc.link_platform(playlist_id, "ym", str(ym_kind))

        await ctx.info(
            f"Done: added={added}, skipped={skipped}, total_ym={total_ym}",
        )
        return {"added": added, "skipped": skipped, "total_ym": total_ym}
