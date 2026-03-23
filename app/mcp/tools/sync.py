"""Sync tools for DJ workflow MCP server.

Phase 3: Replace stubs with working SyncEngine-based implementations.
"""

from __future__ import annotations

import asyncio
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.clients.yandex_music import YandexMusicClient
from app.core.config import settings
from app.core.errors import NotFoundError
from app.mcp.dependencies import (
    get_platform_registry,
    get_playlist_service,
    get_session,
    get_set_service,
    get_sync_engine,
    get_ym_client,
)
from app.mcp.elicitation import confirm_action
from app.mcp.platforms.protocol import MusicPlatform
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.resolve import resolve_local_id
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine, TrackMapper
from app.core.models.metadata_yandex import YandexMetadata
from app.core.models.sets import DjSet
from app.services.playlists import DjPlaylistService
from app.services.sets import DjSetService

logger = logging.getLogger(__name__)

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
    session: AsyncSession | None = None,
    ym_client: YandexMusicClient | None = None,
) -> dict[str, object]:
    """Push DJ set tracks to a YM playlist.

    Uses direct YM API client (not platform adapter) to get albumIds
    from yandex_metadata and auto-fetch revision for existing playlists.
    """
    dj_set = await set_svc.get(set_id)
    uid = int(settings.yandex_music_user_id)

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
    id_map = await track_mapper.local_to_platform(local_track_ids, "ym")

    # Build YM tracks with albumId from yandex_metadata
    ym_tracks: list[dict[str, str]] = []
    ym_id_to_album: dict[str, str] = {}

    if session is not None:
        ym_ids_list = list(id_map.values())
        if ym_ids_list:
            stmt = select(YandexMetadata).where(
                YandexMetadata.yandex_track_id.in_(ym_ids_list),
            )
            res = await session.execute(stmt)
            ym_id_to_album = {
                r.yandex_track_id: r.yandex_album_id or "0" for r in res.scalars().all()
            }

    for tid in local_track_ids:
        ym_id = id_map.get(tid)
        if ym_id is None:
            continue
        album_id = ym_id_to_album.get(ym_id, "0")
        ym_tracks.append({"id": ym_id, "albumId": album_id})

    playlist_name = f"set_{dj_set.name}"

    # Determine which API client to use
    api = ym_client
    if api is None:
        msg = "YM API client required for sync"
        raise ValueError(msg)

    if dj_set.ym_playlist_id:
        # Update existing: delete and recreate (simpler than diff-based update)
        kind = dj_set.ym_playlist_id
        try:
            await api.delete_playlist(uid, kind)
        except Exception:
            logger.warning("Failed to delete old YM playlist %d, creating new", kind)
        kind = await api.create_playlist(uid, playlist_name)
        if ym_tracks:
            await api.add_tracks_to_playlist(uid, kind, ym_tracks)
        remote_playlist_id = str(kind)
    else:
        # Create new playlist
        kind = await api.create_playlist(uid, playlist_name)
        if ym_tracks:
            await api.add_tracks_to_playlist(uid, kind, ym_tracks)
        remote_playlist_id = str(kind)

    # Update dj_sets.ym_playlist_id
    if session is not None:
        dj_set_obj = await session.get(DjSet, set_id)
        if dj_set_obj is not None:
            dj_set_obj.ym_playlist_id = kind
            await session.flush()

    return {
        "set_id": set_id,
        "ym_playlist_id": remote_playlist_id,
        "playlist_name": playlist_name,
        "track_count": len(ym_tracks),
        "unmapped_count": len(local_track_ids) - len(ym_tracks),
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
    id_map = await track_mapper.local_to_platform(local_track_ids, "ym")

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

    @mcp.tool(
        tags={"sync"},
        timeout=600,
        annotations={"destructiveHint": True, "openWorldHint": True},
    )
    async def sync_playlist(
        playlist_id: int,
        ctx: Context,
        platform: str = "ym",
        direction: str = "bidirectional",
        force: bool = False,
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
            force: Skip confirmation prompt (for CLI/batch mode).
        """
        # Confirm destructive sync directions
        if not force and direction in ("local_to_remote", "bidirectional"):
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
        ctx: Context,
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
        ctx: Context,
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

    @mcp.tool(
        tags={"sync", "yandex"},
        timeout=600,
        annotations={"destructiveHint": True, "openWorldHint": True},
    )
    async def sync_set_to_ym(
        set_ref: str | int,
        ctx: Context,
        force: bool = False,
        set_svc: DjSetService = Depends(get_set_service),
        sync_engine: SyncEngine = Depends(get_sync_engine),
        registry: PlatformRegistry = Depends(get_platform_registry),
        session: AsyncSession = Depends(get_session),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Push a DJ set to Yandex Music as a playlist.

        Creates or updates a YM playlist with the set's tracks.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            force: Skip confirmation prompt (for CLI/batch mode).
        """
        set_id = resolve_local_id(set_ref, "set")
        if not registry.is_connected("ym"):
            msg = "YM platform not connected"
            raise ValueError(msg)

        # Confirm push to YM
        if not force:
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
            session=session,
            ym_client=ym_client,
        )

    @mcp.tool(tags={"sync", "yandex"}, timeout=600)
    async def sync_set_from_ym(
        set_ref: str | int,
        ctx: Context,
        set_svc: DjSetService = Depends(get_set_service),
        sync_engine: SyncEngine = Depends(get_sync_engine),
        registry: PlatformRegistry = Depends(get_platform_registry),
    ) -> dict[str, object]:
        """Read feedback from YM playlist, detect removed/added tracks.

        Compares set tracks with YM playlist to identify what changed.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
        """
        set_id = resolve_local_id(set_ref, "set")
        if not registry.is_connected("ym"):
            msg = "YM platform not connected"
            raise ValueError(msg)
        platform = registry.get("ym")
        mapper = sync_engine._mapper
        try:
            return await _do_sync_set_from_ym(
                set_id=set_id,
                set_svc=set_svc,
                track_mapper=mapper,
                platform=platform,
            )
        except NotFoundError:
            return {"status": "error", "reason": f"Set {set_id} not found"}

    @mcp.tool(
        tags={"sync", "yandex"},
        timeout=600,
        annotations={"destructiveHint": True, "openWorldHint": True},
    )
    async def batch_sync_sets_to_ym(
        set_ids: list[int],
        ctx: Context,
        force: bool = True,
        set_svc: DjSetService = Depends(get_set_service),
        sync_engine: SyncEngine = Depends(get_sync_engine),
        registry: PlatformRegistry = Depends(get_platform_registry),
        session: AsyncSession = Depends(get_session),
        ym_client: YandexMusicClient = Depends(get_ym_client),
    ) -> dict[str, object]:
        """Push multiple DJ sets to YM as playlists.

        Delegates to _do_sync_set_to_ym for each set (delete/recreate pattern).
        Applies 1.5s rate limit between sets.

        Args:
            set_ids: List of DJ set IDs to sync.
            force: Skip confirmation (default True for batch).
        """
        if not registry.is_connected("ym"):
            msg = "YM platform not connected"
            raise ValueError(msg)

        platform = registry.get("ym")
        mapper = sync_engine._mapper
        results: list[dict[str, object]] = []
        synced = 0
        failed = 0

        for i, set_id in enumerate(set_ids):
            await ctx.report_progress(progress=i, total=len(set_ids))
            await ctx.info(f"Syncing set {set_id} ({i + 1}/{len(set_ids)})...")

            try:
                result = await _do_sync_set_to_ym(
                    set_id=set_id,
                    set_svc=set_svc,
                    track_mapper=mapper,
                    platform=platform,
                    session=session,
                    ym_client=ym_client,
                )
                result["set_id"] = set_id
                results.append(result)
                synced += 1

            except Exception:  # broad: skip failed set, process rest
                logger.exception("Failed to sync set %d", set_id)
                results.append(
                    {
                        "set_id": set_id,
                        "status": "failed",
                        "reason": "error during sync",
                    }
                )
                failed += 1

            # Rate limit between sets
            if i < len(set_ids) - 1:
                await asyncio.sleep(1.5)

        await ctx.report_progress(
            progress=len(set_ids),
            total=len(set_ids),
        )

        return {"synced": synced, "failed": failed, "results": results}
