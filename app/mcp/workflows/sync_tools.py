"""Sync tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.errors import NotFoundError, ValidationError
from app.mcp.dependencies import (
    get_playlist_service,
    get_set_service,
    get_track_service,
    get_ym_client,
)
from app.services.playlists import DjPlaylistService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.services.yandex_music_client import YandexMusicClient


def register_sync_tools(mcp: FastMCP) -> None:
    """Register sync tools on the MCP server."""

    @mcp.tool(tags={"sync", "yandex"})
    async def sync_set_to_ym(
        set_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        track_svc: TrackService = Depends(get_track_service),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Push a DJ set to Yandex Music as a playlist.

        Creates or updates a YM playlist named "set_{set_name}".
        Stores ym_playlist_id on the DjSet record for future syncs.

        This is a stub — full YM API integration (create_playlist,
        change_playlist_tracks) will be wired incrementally.

        Args:
            set_id: DJ set to sync to Yandex Music.
        """
        dj_set = await set_svc.get(set_id)

        # Get latest version items
        versions = await set_svc.list_versions(set_id)
        if not versions.items:
            raise NotFoundError("DjSetVersion", set_id=set_id)
        latest = max(versions.items, key=lambda v: v.set_version_id)

        items_list = await set_svc.list_items(latest.set_version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)

        await ctx.report_progress(progress=0, total=100)

        # Collect YM track IDs from metadata
        ym_track_ids: list[str] = []
        for item in items:
            try:
                await track_svc.get(item.track_id)
                # Track model doesn't have ym_track_id directly;
                # it's in metadata_yandex table (yandex_track_id).
                # For now, use track_id as placeholder.
                ym_track_ids.append(str(item.track_id))
            except NotFoundError:
                pass

        playlist_name = f"set_{dj_set.name}"

        await ctx.info(
            f"Sync set '{dj_set.name}' → YM playlist '{playlist_name}' "
            f"({len(ym_track_ids)} tracks). "
            "Full YM API integration pending — tracks collected."
        )

        # TODO: Wire YM API calls:
        # if dj_set.ym_playlist_id:
        #     await ym_client.change_playlist_tracks(...)
        # else:
        #     result = await ym_client.create_playlist(playlist_name)
        #     ym_playlist_id = result["kind"]
        #     await set_svc.update(set_id, DjSetUpdate(ym_playlist_id=ym_playlist_id))

        await ctx.report_progress(progress=100, total=100)

        return {
            "set_id": set_id,
            "ym_playlist_id": dj_set.ym_playlist_id,
            "playlist_name": playlist_name,
            "track_count": len(ym_track_ids),
            "status": "stub",
        }

    @mcp.tool(tags={"sync", "yandex"})
    async def sync_set_from_ym(
        set_id: int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Read likes/dislikes from YM set playlist, update pinned/excluded.

        For tracks in the YM set playlist:
        - liked AND in playlist -> pinned=true
        - disliked -> excluded (remove from set)
        - manually removed from YM playlist -> excluded
        - manually added to YM playlist -> pinned=true

        Requires sync_set_to_ym to have been called first.

        This is a stub — full YM API integration (get_playlist,
        get_liked_tracks, get_disliked_tracks) will be wired incrementally.

        Args:
            set_id: DJ set to sync feedback for.
        """
        dj_set = await set_svc.get(set_id)

        if not dj_set.ym_playlist_id:
            raise ValidationError("Set not synced to YM yet — call sync_set_to_ym first")

        await ctx.report_progress(progress=0, total=100)

        await ctx.info(
            f"Reading feedback from YM playlist {dj_set.ym_playlist_id} "
            f"for set '{dj_set.name}'. "
            "Full YM API integration pending."
        )

        # TODO: Wire YM API calls:
        # ym_playlist = await ym_client.get_playlist(dj_set.ym_playlist_id)
        # liked_ids = await ym_client.get_liked_tracks()
        # disliked_ids = await ym_client.get_disliked_tracks()
        # ... compare with current set items, update pinned flags

        await ctx.report_progress(progress=100, total=100)

        return {
            "set_id": set_id,
            "pinned_count": 0,
            "excluded_count": 0,
            "unchanged_count": 0,
            "status": "stub",
        }

    @mcp.tool(tags={"sync", "yandex"})
    async def sync_playlist(
        playlist_id: int,
        ctx: Context,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Bidirectional sync between YM playlist and local DB.

        - New tracks in YM -> add to local DB
        - Removed tracks in YM -> mark removed locally
        - New tracks locally -> add to YM playlist

        This is a stub — full bidirectional sync requires diffing
        YM playlist state against local items.

        Args:
            playlist_id: Local playlist ID to sync with its YM counterpart.
        """
        await ctx.report_progress(progress=0, total=100)

        await ctx.info(
            f"Bidirectional sync for playlist {playlist_id}. Full YM API integration pending."
        )

        # TODO: Wire YM API calls:
        # local_items = await playlist_svc.list_items(playlist_id)
        # ym_tracks = await ym_client.get_playlist(ym_playlist_id)
        # ... diff and reconcile

        await ctx.report_progress(progress=100, total=100)

        return {
            "playlist_id": playlist_id,
            "added_locally": 0,
            "removed_locally": 0,
            "added_to_ym": 0,
            "status": "stub",
        }
