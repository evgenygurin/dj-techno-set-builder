"""SyncEngine — orchestrates bidirectional playlist sync."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.mcp.platforms.protocol import MusicPlatform
from app.mcp.sync.diff import SyncDirection, compute_sync_diff

if TYPE_CHECKING:
    from app.services.playlists import DjPlaylistService

logger = logging.getLogger(__name__)


class TrackMapper(Protocol):
    """Maps between local track IDs and platform track IDs."""

    async def local_to_platform(self, track_ids: list[int], platform: str) -> dict[int, str]: ...

    async def platform_to_local(
        self, platform_ids: list[str], platform: str
    ) -> dict[str, int | None]: ...


@dataclass
class SyncResult:
    """Summary of a sync operation."""

    playlist_id: int
    platform: str
    direction: str
    added_to_local: int
    removed_from_local: int
    added_to_remote: int
    removed_from_remote: int
    skipped_unknown: int

    def to_dict(self) -> dict[str, object]:
        return {
            "playlist_id": self.playlist_id,
            "platform": self.platform,
            "direction": self.direction,
            "added_to_local": self.added_to_local,
            "removed_from_local": self.removed_from_local,
            "added_to_remote": self.added_to_remote,
            "removed_from_remote": self.removed_from_remote,
            "skipped_unknown": self.skipped_unknown,
        }


class SyncEngine:
    """Orchestrates bidirectional playlist sync between local DB and platforms.

    Flow:
    1. Load local playlist items -> get track_ids
    2. Map local track_ids to platform track IDs (via ProviderTrackId)
    3. Load remote playlist from platform
    4. Compute diff (local vs remote platform IDs)
    5. Apply changes to both sides
    """

    def __init__(
        self,
        playlist_svc: DjPlaylistService,
        track_mapper: TrackMapper,
    ) -> None:
        self._playlist_svc = playlist_svc
        self._mapper = track_mapper

    async def sync(
        self,
        playlist_id: int,
        platform: MusicPlatform,
        direction: SyncDirection,
    ) -> SyncResult:
        """Execute sync between local playlist and a remote platform.

        Args:
            playlist_id: Local playlist ID.
            platform: Platform adapter to sync with.
            direction: Sync direction strategy.

        Returns:
            SyncResult with counts of changes made.

        Raises:
            ValueError: If playlist is not linked to the platform.
        """
        # 1. Load local playlist
        playlist = await self._playlist_svc.get(playlist_id)
        platform_ids = playlist.platform_ids or {}
        remote_playlist_id = platform_ids.get(platform.name)

        if not remote_playlist_id:
            msg = (
                f"Playlist {playlist_id} not linked to platform "
                f"'{platform.name}'. Set platform_ids first."
            )
            raise ValueError(msg)

        # 2. Load local items and map to platform IDs
        items_list = await self._playlist_svc.list_items(playlist_id, offset=0, limit=5000)
        local_track_ids = [item.track_id for item in items_list.items]
        id_map = await self._mapper.local_to_platform(local_track_ids, platform.name)
        local_platform_ids = [id_map[tid] for tid in local_track_ids if tid in id_map]

        # 3. Load remote playlist
        remote_pl = await platform.get_playlist(remote_playlist_id)
        remote_platform_ids = remote_pl.track_ids

        # 4. Compute diff
        diff = compute_sync_diff(
            local_track_ids=local_platform_ids,
            remote_track_ids=remote_platform_ids,
            direction=direction,
        )

        # 5. Apply changes
        added_local = 0
        removed_local = 0
        added_remote = 0
        removed_remote = 0
        skipped = 0

        # Apply to remote
        if diff.add_to_remote:
            try:
                await platform.add_tracks_to_playlist(remote_playlist_id, diff.add_to_remote)
                added_remote = len(diff.add_to_remote)
            except NotImplementedError:
                logger.warning(
                    "Platform %s does not support playlist writes",
                    platform.name,
                )
                skipped += len(diff.add_to_remote)

        if diff.remove_from_remote:
            try:
                await platform.remove_tracks_from_playlist(
                    remote_playlist_id, diff.remove_from_remote
                )
                removed_remote = len(diff.remove_from_remote)
            except NotImplementedError:
                logger.warning(
                    "Platform %s does not support playlist writes",
                    platform.name,
                )
                skipped += len(diff.remove_from_remote)

        # Apply to local (add)
        if diff.add_to_local:
            reverse_map = await self._mapper.platform_to_local(diff.add_to_local, platform.name)
            next_sort = len(items_list.items)
            for pid in diff.add_to_local:
                local_tid = reverse_map.get(pid)
                if local_tid is None:
                    logger.info(
                        "Unknown platform track %s — skipping local add",
                        pid,
                    )
                    skipped += 1
                    continue
                from app.schemas.playlists import DjPlaylistItemCreate

                await self._playlist_svc.add_item(
                    playlist_id,
                    DjPlaylistItemCreate(
                        track_id=local_tid,
                        sort_index=next_sort,
                    ),
                )
                next_sort += 1
                added_local += 1

        # Apply to local (remove)
        if diff.remove_from_local:
            reverse_map = await self._mapper.platform_to_local(
                diff.remove_from_local, platform.name
            )
            for pid in diff.remove_from_local:
                local_tid = reverse_map.get(pid)
                if local_tid is None:
                    skipped += 1
                    continue
                # Find the playlist item for this track
                for item in items_list.items:
                    if item.track_id == local_tid:
                        await self._playlist_svc.remove_item(item.playlist_item_id)
                        removed_local += 1
                        break

        logger.info(
            "Sync playlist %d <-> %s:%s complete: +%d/-%d local, +%d/-%d remote, %d skipped",
            playlist_id,
            platform.name,
            remote_playlist_id,
            added_local,
            removed_local,
            added_remote,
            removed_remote,
            skipped,
        )

        return SyncResult(
            playlist_id=playlist_id,
            platform=platform.name,
            direction=direction.value,
            added_to_local=added_local,
            removed_from_local=removed_local,
            added_to_remote=added_remote,
            removed_from_remote=removed_remote,
            skipped_unknown=skipped,
        )
