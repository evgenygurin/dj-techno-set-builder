"""Tests for playlist sync diff logic."""

from __future__ import annotations

from app.mcp.sync.diff import SyncDirection, compute_sync_diff


class TestComputeSyncDiff:
    def test_identical_playlists(self) -> None:
        """No changes when playlists are identical."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b", "c"],
            remote_track_ids=["a", "b", "c"],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert diff.add_to_local == []
        assert diff.remove_from_local == []
        assert diff.add_to_remote == []
        assert diff.remove_from_remote == []
        assert diff.is_empty

    def test_local_to_remote_adds(self) -> None:
        """Local has extra tracks — push them to remote."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b", "c", "d"],
            remote_track_ids=["a", "b"],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )
        assert diff.add_to_remote == ["c", "d"]
        assert diff.remove_from_remote == []
        assert diff.add_to_local == []
        assert diff.remove_from_local == []

    def test_local_to_remote_removes(self) -> None:
        """Remote has extra tracks — remove them from remote."""
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["a", "b", "c"],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )
        assert diff.remove_from_remote == ["b", "c"]
        assert diff.add_to_remote == []

    def test_remote_to_local_adds(self) -> None:
        """Remote has extra tracks — pull them to local."""
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["a", "b", "c"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.add_to_local == ["b", "c"]
        assert diff.remove_from_local == []
        assert diff.add_to_remote == []

    def test_remote_to_local_removes(self) -> None:
        """Local has extra tracks — remove them from local."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b", "c"],
            remote_track_ids=["a"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.remove_from_local == ["b", "c"]

    def test_bidirectional_merge(self) -> None:
        """Bidirectional: add to each side what the other has."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b"],
            remote_track_ids=["b", "c"],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert diff.add_to_local == ["c"]
        assert diff.add_to_remote == ["a"]
        # Bidirectional never removes
        assert diff.remove_from_local == []
        assert diff.remove_from_remote == []

    def test_empty_local(self) -> None:
        diff = compute_sync_diff(
            local_track_ids=[],
            remote_track_ids=["a", "b"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.add_to_local == ["a", "b"]

    def test_empty_remote(self) -> None:
        diff = compute_sync_diff(
            local_track_ids=["a", "b"],
            remote_track_ids=[],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )
        assert diff.add_to_remote == ["a", "b"]

    def test_both_empty(self) -> None:
        diff = compute_sync_diff(
            local_track_ids=[],
            remote_track_ids=[],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert diff.is_empty

    def test_is_empty_false(self) -> None:
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["b"],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert not diff.is_empty

    def test_preserves_order(self) -> None:
        """Added tracks maintain their relative order."""
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["a", "x", "y", "z"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.add_to_local == ["x", "y", "z"]
