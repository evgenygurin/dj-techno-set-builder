"""Pure-function diff computation for playlist sync."""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class SyncDirection(Enum):
    """Direction of sync between local and remote playlists."""

    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"
    BIDIRECTIONAL = "bidirectional"


class SyncDiff(NamedTuple):
    """Diff result describing what changes are needed on each side.

    Platform track IDs (strings) are used throughout — the caller
    is responsible for mapping between local DB IDs and platform IDs.
    """

    add_to_local: list[str]
    remove_from_local: list[str]
    add_to_remote: list[str]
    remove_from_remote: list[str]

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.add_to_local,
                self.remove_from_local,
                self.add_to_remote,
                self.remove_from_remote,
            )
        )


def compute_sync_diff(
    *,
    local_track_ids: list[str],
    remote_track_ids: list[str],
    direction: SyncDirection,
) -> SyncDiff:
    """Compute diff between local and remote playlists.

    Args:
        local_track_ids: Platform track IDs present in local playlist.
        remote_track_ids: Platform track IDs present in remote playlist.
        direction: Sync direction strategy.

    Returns:
        SyncDiff with tracks to add/remove on each side.
    """
    local_set = set(local_track_ids)
    remote_set = set(remote_track_ids)

    only_local = [t for t in local_track_ids if t not in remote_set]
    only_remote = [t for t in remote_track_ids if t not in local_set]

    if direction == SyncDirection.LOCAL_TO_REMOTE:
        return SyncDiff(
            add_to_local=[],
            remove_from_local=[],
            add_to_remote=only_local,
            remove_from_remote=only_remote,
        )

    if direction == SyncDirection.REMOTE_TO_LOCAL:
        return SyncDiff(
            add_to_local=only_remote,
            remove_from_local=only_local,
            add_to_remote=[],
            remove_from_remote=[],
        )

    # BIDIRECTIONAL — merge both sides, never remove
    return SyncDiff(
        add_to_local=only_remote,
        remove_from_local=[],
        add_to_remote=only_local,
        remove_from_remote=[],
    )
