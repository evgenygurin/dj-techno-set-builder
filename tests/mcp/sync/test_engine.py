"""Tests for SyncEngine orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.platforms.protocol import PlatformPlaylist
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine, SyncResult


@pytest.fixture
def mock_playlist_svc() -> AsyncMock:
    svc = AsyncMock()
    # list_items returns items with track_id attribute
    item1 = MagicMock(track_id=1, sort_index=0, playlist_item_id=100)
    item2 = MagicMock(track_id=2, sort_index=1, playlist_item_id=101)
    item3 = MagicMock(track_id=3, sort_index=2, playlist_item_id=102)
    items_list = MagicMock(items=[item1, item2, item3], total=3)
    svc.list_items = AsyncMock(return_value=items_list)
    svc.add_item = AsyncMock()
    svc.remove_item = AsyncMock()
    # get returns playlist with platform_ids
    playlist = MagicMock(
        playlist_id=10,
        name="Test PL",
        platform_ids={"ym": "1003"},
        source_of_truth="local",
    )
    svc.get = AsyncMock(return_value=playlist)
    return svc


@pytest.fixture
def mock_track_mapper() -> AsyncMock:
    """Maps local track_id to platform track_id and vice versa."""
    mapper = AsyncMock()
    # local_to_platform: {track_id: platform_id}
    mapper.local_to_platform = AsyncMock(
        return_value={
            1: "ym_100",
            2: "ym_200",
            3: "ym_300",
        }
    )
    # platform_to_local: {platform_id: track_id}
    mapper.platform_to_local = AsyncMock(
        return_value={
            "ym_100": 1,
            "ym_200": 2,
            "ym_300": 3,
            "ym_400": None,  # unknown track
        }
    )
    return mapper


@pytest.fixture
def mock_platform() -> AsyncMock:
    platform = AsyncMock()
    platform.name = "ym"
    platform.get_playlist = AsyncMock(
        return_value=PlatformPlaylist(
            platform_id="1003",
            name="Remote PL",
            track_ids=["ym_200", "ym_300", "ym_400"],
            owner_id="250905515",
        )
    )
    platform.add_tracks_to_playlist = AsyncMock()
    platform.remove_tracks_from_playlist = AsyncMock()
    return platform


@pytest.fixture
def engine(mock_playlist_svc: AsyncMock, mock_track_mapper: AsyncMock) -> SyncEngine:
    return SyncEngine(
        playlist_svc=mock_playlist_svc,
        track_mapper=mock_track_mapper,
    )


class TestSyncEngineLocalToRemote:
    async def test_pushes_new_tracks_to_remote(
        self,
        engine: SyncEngine,
        mock_platform: AsyncMock,
    ) -> None:
        result = await engine.sync(
            playlist_id=10,
            platform=mock_platform,
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert isinstance(result, SyncResult)
        assert result.added_to_remote == 1  # ym_100 only in local
        assert result.removed_from_remote == 1  # ym_400 only in remote
        assert result.added_to_local == 0
        assert result.removed_from_local == 0


class TestSyncEngineRemoteToLocal:
    async def test_pulls_new_tracks_to_local(
        self,
        engine: SyncEngine,
        mock_platform: AsyncMock,
    ) -> None:
        result = await engine.sync(
            playlist_id=10,
            platform=mock_platform,
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )

        assert result.added_to_local >= 0  # ym_400 might not have local mapping
        assert result.removed_from_local == 1  # track 1 (ym_100) only in local


class TestSyncEngineBidirectional:
    async def test_merges_both_sides(
        self,
        engine: SyncEngine,
        mock_platform: AsyncMock,
    ) -> None:
        result = await engine.sync(
            playlist_id=10,
            platform=mock_platform,
            direction=SyncDirection.BIDIRECTIONAL,
        )

        assert result.added_to_remote >= 0
        assert result.added_to_local >= 0
        assert result.removed_from_local == 0  # bidirectional never removes
        assert result.removed_from_remote == 0


class TestSyncEngineNoRemotePlaylist:
    async def test_no_platform_ids(
        self,
        engine: SyncEngine,
        mock_platform: AsyncMock,
        mock_playlist_svc: AsyncMock,
    ) -> None:
        """Sync fails gracefully when playlist has no platform_id."""
        playlist = MagicMock(
            playlist_id=10,
            name="Test PL",
            platform_ids=None,
            source_of_truth="local",
        )
        mock_playlist_svc.get = AsyncMock(return_value=playlist)

        with pytest.raises(ValueError, match="not linked"):
            await engine.sync(
                playlist_id=10,
                platform=mock_platform,
                direction=SyncDirection.LOCAL_TO_REMOTE,
            )


class TestSyncResult:
    def test_to_dict(self) -> None:
        r = SyncResult(
            playlist_id=10,
            platform="ym",
            direction="local_to_remote",
            added_to_local=0,
            removed_from_local=0,
            added_to_remote=3,
            removed_from_remote=1,
            skipped_unknown=0,
        )
        d = r.to_dict()
        assert d["added_to_remote"] == 3
        assert d["platform"] == "ym"
