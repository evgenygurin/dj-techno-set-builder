"""Sync tools for DJ workflow MCP server.

Phase 3: Replace stubs with working SyncEngine-based implementations.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.mcp.dependencies import (
    get_platform_registry,
    get_playlist_service,
    get_set_service,
    get_sync_engine,
)
from app.mcp.elicitation import confirm_action
from app.mcp.platforms.protocol import MusicPlatform
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine, TrackMapper
from app.services.playlists import DjPlaylistService
from app.services.sets import DjSetService

_DIRECTION_MAP = {
    "local_to_remote": SyncDirection.LOCAL_TO_REMOTE,
    "remote_to_local": SyncDirection.REMOTE_TO_LOCAL,
    "bidirectional": SyncDirection.BIDIRECTIONAL,
}


async def _do_sync_playlist(
    *,
    playlist_id: int,
    platform_name: str,
    direction: str,
    sync_engine: SyncEngine,
    platform_registry: PlatformRegistry,
) -> dict[str, object]:
    """Core sync logic, extracted for testability."""
    if not platform_registry.is_connected(platform_name):
        msg = f"Platform '{platform_name}' is not connected"
        raise ValueError(msg)

    sync_dir = _DIRECTION_MAP.get(direction)
    if sync_dir is None:
        valid = ", ".join(sorted(_DIRECTION_MAP.keys()))
        msg = f"Invalid direction '{direction}'. Valid: {valid}"
        raise ValueError(msg)

    platform = platform_registry.get(platform_name)

    result = await sync_engine.sync(
        playlist_id=playlist_id,
        platform=platform,
        direction=sync_dir,
    )
    return result.to_dict()


async def _do_sync_set_to_ym(
    *,
    set_id: int,
    set_svc: DjSetService,
    track_mapper: TrackMapper,
    platform: MusicPlatform,
) -> dict[str, object]:
    """Push DJ set tracks to a YM playlist."""
    dj_set = await set_svc.get(set_id)

    # Get latest version
    versions = await set_svc.list_versions(set_id)
    if not versions.items:
        msg = f"Set {set_id} has no versions"
        raise ValueError(msg)
    latest = max(versions.items, key=lambda v: v.set_version_id)

    # Get set items
    items_list = await set_svc.list_items(latest.set_version_id, offset=0, limit=500)
    items = sorted(items_list.items, key=lambda i: i.sort_index)
    local_track_ids = [item.track_id for item in items]

    # Map to platform IDs
    id_map = await track_mapper.local_to_platform(local_track_ids, "yandex_music")
    ym_track_ids = [id_map[tid] for tid in local_track_ids if tid in id_map]

    playlist_name = f"set_{dj_set.name}"

    if dj_set.ym_playlist_id:
        # Update existing playlist
        remote_playlist_id = str(dj_set.ym_playlist_id)
        try:
            remote_pl = await platform.get_playlist(remote_playlist_id)
            # Remove all existing, add new
            if remote_pl.track_ids:
                await platform.remove_tracks_from_playlist(remote_playlist_id, remote_pl.track_ids)
            if ym_track_ids:
                await platform.add_tracks_to_playlist(remote_playlist_id, ym_track_ids)
        except NotImplementedError:
            return {
                "set_id": set_id,
                "ym_playlist_id": remote_playlist_id,
                "playlist_name": playlist_name,
                "track_count": 0,
                "unmapped_count": len(local_track_ids),
                "status": "not_supported",
                "error": "Platform does not support playlist write operations",
            }
    else:
        # Create new playlist
        try:
            remote_playlist_id = await platform.create_playlist(playlist_name, ym_track_ids)
        except NotImplementedError:
            return {
                "set_id": set_id,
                "ym_playlist_id": None,
                "playlist_name": playlist_name,
                "track_count": 0,
                "unmapped_count": len(local_track_ids),
                "status": "not_supported",
                "error": "Platform does not support playlist creation",
            }

    return {
        "set_id": set_id,
        "ym_playlist_id": remote_playlist_id,
        "playlist_name": playlist_name,
        "track_count": len(ym_track_ids),
        "unmapped_count": len(local_track_ids) - len(ym_track_ids),
        "status": "synced",
    }


async def _do_sync_set_from_ym(
    *,
    set_id: int,
    set_svc: DjSetService,
    track_mapper: TrackMapper,
    platform: MusicPlatform,
) -> dict[str, object]:
    """Read YM playlist state and update set items."""
    dj_set = await set_svc.get(set_id)

    if not dj_set.ym_playlist_id:
        msg = f"Set {set_id} not synced to YM — call sync_set_to_ym first"
        raise ValueError(msg)

    # Get latest version items
    versions = await set_svc.list_versions(set_id)
    if not versions.items:
        msg = f"Set {set_id} has no versions"
        raise ValueError(msg)
    latest = max(versions.items, key=lambda v: v.set_version_id)

    items_list = await set_svc.list_items(latest.set_version_id, offset=0, limit=500)
    local_track_ids = [item.track_id for item in items_list.items]

    # Map local to platform IDs
    id_map = await track_mapper.local_to_platform(local_track_ids, "yandex_music")

    # Fetch remote playlist
    remote_pl = await platform.get_playlist(str(dj_set.ym_playlist_id))
    remote_set = set(remote_pl.track_ids)

    # Detect removed tracks (in set but not in YM playlist)
    removed_count = 0
    still_count = 0
    for item in items_list.items:
        ym_id = id_map.get(item.track_id)
        if ym_id is None:
            continue
        if ym_id not in remote_set:
            removed_count += 1
        else:
            still_count += 1

    return {
        "set_id": set_id,
        "ym_playlist_id": dj_set.ym_playlist_id,
        "still_in_playlist": still_count,
        "removed_count": removed_count,
        "status": "synced",
    }


def register_sync_tools(mcp: FastMCP) -> None:
    """Register sync tools on the MCP server."""

    @mcp.tool(tags={"sync"}, timeout=600)
    async def sync_playlist(
        playlist_id: int,
        platform: str = "ym",
        direction: str = "bidirectional",
        ctx: Context | None = None,
        sync_engine: SyncEngine = Depends(get_sync_engine),
        registry: PlatformRegistry = Depends(get_platform_registry),
    ) -> dict[str, object]:
        """Bidirectional sync between a local playlist and a music platform.

        Compares local playlist tracks with the platform playlist,
        then adds/removes tracks to bring them in sync.

        Args:
            playlist_id: Local playlist ID to sync.
            platform: Platform name ("ym", "spotify", etc.). Default: "ym".
            direction: "local_to_remote", "remote_to_local", or "bidirectional".
        """
        # Confirm destructive sync directions
        if direction in ("local_to_remote", "bidirectional") and ctx is not None:
            confirmed = await confirm_action(
                ctx,
                f"Sync playlist {playlist_id} ({direction}) to {platform}? "
                "This may modify remote playlist.",
            )
            if not confirmed:
                return {"status": "cancelled", "reason": "user declined sync"}

        return await _do_sync_playlist(
            playlist_id=playlist_id,
            platform_name=platform,
            direction=direction,
            sync_engine=sync_engine,
            platform_registry=registry,
        )

    @mcp.tool(tags={"sync"})
    async def set_source_of_truth(
        playlist_id: int,
        source: str,
        ctx: Context | None = None,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> dict[str, object]:
        """Configure which side is the source of truth for a playlist.

        Args:
            playlist_id: Local playlist ID.
            source: "local", "ym", "spotify", "beatport", or "soundcloud".
        """
        valid_sources = {"local", "ym", "spotify", "beatport", "soundcloud"}
        if source not in valid_sources:
            msg = f"Invalid source '{source}'. Valid: {', '.join(sorted(valid_sources))}"
            raise ValueError(msg)

        from app.schemas.playlists import DjPlaylistUpdate

        await playlist_svc.update(
            playlist_id,
            DjPlaylistUpdate(source_of_truth=source),
        )
        return {
            "playlist_id": playlist_id,
            "source_of_truth": source,
            "status": "updated",
        }

    @mcp.tool(tags={"sync"})
    async def link_playlist(
        playlist_id: int,
        platform: str,
        platform_playlist_id: str,
        ctx: Context | None = None,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> dict[str, object]:
        """Link a local playlist to a platform playlist for syncing.

        Call this before sync_playlist to establish the connection.

        Args:
            playlist_id: Local playlist ID.
            platform: Platform name ("ym", "spotify", etc.).
            platform_playlist_id: The playlist ID on the platform.
        """
        playlist = await playlist_svc.get(playlist_id)
        current_ids = playlist.platform_ids or {}
        current_ids[platform] = platform_playlist_id

        from app.schemas.playlists import DjPlaylistUpdate

        await playlist_svc.update(
            playlist_id,
            DjPlaylistUpdate(platform_ids=current_ids),
        )
        return {
            "playlist_id": playlist_id,
            "platform": platform,
            "platform_playlist_id": platform_playlist_id,
            "status": "linked",
        }

    @mcp.tool(tags={"sync", "yandex"}, timeout=600)
    async def sync_set_to_ym(
        set_id: int,
        ctx: Context | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        sync_engine: SyncEngine = Depends(get_sync_engine),
        registry: PlatformRegistry = Depends(get_platform_registry),
    ) -> dict[str, object]:
        """Push a DJ set to Yandex Music as a playlist.

        Creates or updates a YM playlist with the set's tracks.

        Args:
            set_id: DJ set to sync to Yandex Music.
        """
        if not registry.is_connected("ym"):
            msg = "YM platform not connected"
            raise ValueError(msg)

        # Confirm push to YM
        if ctx is not None:
            confirmed = await confirm_action(
                ctx,
                f"Push set {set_id} to Yandex Music? This will create/overwrite a YM playlist.",
            )
            if not confirmed:
                return {"status": "cancelled", "reason": "user declined push"}

        platform = registry.get("ym")
        mapper = sync_engine._mapper
        return await _do_sync_set_to_ym(
            set_id=set_id,
            set_svc=set_svc,
            track_mapper=mapper,
            platform=platform,
        )

    @mcp.tool(tags={"sync", "yandex"}, timeout=600)
    async def sync_set_from_ym(
        set_id: int,
        ctx: Context | None = None,
        set_svc: DjSetService = Depends(get_set_service),
        sync_engine: SyncEngine = Depends(get_sync_engine),
        registry: PlatformRegistry = Depends(get_platform_registry),
    ) -> dict[str, object]:
        """Read feedback from YM playlist, detect removed/added tracks.

        Compares set tracks with YM playlist to identify what changed.

        Args:
            set_id: DJ set to sync feedback for.
        """
        if not registry.is_connected("ym"):
            msg = "YM platform not connected"
            raise ValueError(msg)
        platform = registry.get("ym")
        mapper = sync_engine._mapper
        return await _do_sync_set_from_ym(
            set_id=set_id,
            set_svc=set_svc,
            track_mapper=mapper,
            platform=platform,
        )
