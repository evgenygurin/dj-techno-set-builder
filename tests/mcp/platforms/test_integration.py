"""Integration tests for multi-platform sync flow."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.platforms.protocol import (
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine
from app.mcp.sync.track_mapper import DbTrackMapper
from app.models.catalog import Track
from app.models.dj import DjPlaylist, DjPlaylistItem
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.services.playlists import DjPlaylistService


@dataclass
class InMemoryPlatform:
    """Fake platform adapter with in-memory playlist storage."""

    name: str = "fake"
    capabilities: frozenset[PlatformCapability] = frozenset(
        {
            PlatformCapability.SEARCH,
            PlatformCapability.PLAYLIST_READ,
            PlatformCapability.PLAYLIST_WRITE,
        }
    )
    playlists: dict[str, list[str]] = field(default_factory=dict)

    async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]:
        return []

    async def get_track(self, platform_id: str) -> PlatformTrack:
        return PlatformTrack(platform_id=platform_id, title="test", artists="test")

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        tracks = self.playlists.get(platform_id, [])
        return PlatformPlaylist(
            platform_id=platform_id,
            name=f"Playlist {platform_id}",
            track_ids=tracks,
        )

    async def create_playlist(self, name: str, track_ids: list[str]) -> str:
        pid = str(len(self.playlists) + 1)
        self.playlists[pid] = list(track_ids)
        return pid

    async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        self.playlists.setdefault(playlist_id, []).extend(track_ids)

    async def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        existing = self.playlists.get(playlist_id, [])
        remove_set = set(track_ids)
        self.playlists[playlist_id] = [t for t in existing if t not in remove_set]

    async def delete_playlist(self, playlist_id: str) -> None:
        self.playlists.pop(playlist_id, None)

    async def get_download_url(self, track_id: str, *, bitrate: int = 320) -> str | None:
        return None

    async def close(self) -> None:
        pass


@pytest.fixture
async def seed_sync_data(session: AsyncSession) -> None:
    """Seed test data: provider, tracks, playlist, provider_track_ids.

    Uses merge() + high IDs to avoid collisions with session-scoped engine.
    """
    await session.merge(Provider(provider_id=99, provider_code="fake", name="Fake Platform"))
    await session.flush()
    for t in [
        Track(track_id=80001, title="Alpha", duration_ms=300000, status=0),
        Track(track_id=80002, title="Beta", duration_ms=300000, status=0),
        Track(track_id=80003, title="Gamma", duration_ms=300000, status=0),
    ]:
        await session.merge(t)
    await session.flush()
    await session.merge(
        DjPlaylist(
            playlist_id=80010,
            name="Test Playlist",
            source_of_truth="local",
            platform_ids={"fake": "remote_1"},
        )
    )
    await session.flush()
    for item in [
        DjPlaylistItem(playlist_item_id=80100, playlist_id=80010, track_id=80001, sort_index=0),
        DjPlaylistItem(playlist_item_id=80101, playlist_id=80010, track_id=80002, sort_index=1),
    ]:
        await session.merge(item)
    await session.flush()
    for ptid in [
        ProviderTrackId(id=80201, track_id=80001, provider_id=99, provider_track_id="f_100"),
        ProviderTrackId(id=80202, track_id=80002, provider_id=99, provider_track_id="f_200"),
        ProviderTrackId(id=80203, track_id=80003, provider_id=99, provider_track_id="f_300"),
    ]:
        await session.merge(ptid)
    await session.flush()


class TestFullSyncFlow:
    async def test_local_to_remote_sync(self, session: AsyncSession, seed_sync_data: None) -> None:
        """Local playlist -> push to remote platform."""
        platform = InMemoryPlatform()
        platform.playlists["remote_1"] = ["f_200"]  # remote has only track 80002

        playlist_svc = DjPlaylistService(
            DjPlaylistRepository(session),
            DjPlaylistItemRepository(session),
        )
        mapper = DbTrackMapper(session)
        engine = SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)

        result = await engine.sync(
            playlist_id=80010,
            platform=platform,
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert result.added_to_remote == 1  # f_100 added
        assert result.removed_from_remote == 0  # f_200 stays (both have it)
        assert "f_100" in platform.playlists["remote_1"]
        assert "f_200" in platform.playlists["remote_1"]

    async def test_remote_to_local_sync(self, session: AsyncSession, seed_sync_data: None) -> None:
        """Remote platform -> pull new tracks to local."""
        platform = InMemoryPlatform()
        platform.playlists["remote_1"] = ["f_100", "f_200", "f_300"]  # remote has all 3

        playlist_svc = DjPlaylistService(
            DjPlaylistRepository(session),
            DjPlaylistItemRepository(session),
        )
        mapper = DbTrackMapper(session)
        engine = SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)

        result = await engine.sync(
            playlist_id=80010,
            platform=platform,
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )

        assert result.added_to_local == 1  # f_300 (track 80003) added
        assert result.removed_from_local == 0  # remote has all local tracks

    async def test_bidirectional_sync(self, session: AsyncSession, seed_sync_data: None) -> None:
        """Bidirectional: merge both sides."""
        platform = InMemoryPlatform()
        platform.playlists["remote_1"] = ["f_200", "f_300"]  # remote has 2,3; local has 1,2

        playlist_svc = DjPlaylistService(
            DjPlaylistRepository(session),
            DjPlaylistItemRepository(session),
        )
        mapper = DbTrackMapper(session)
        engine = SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)

        result = await engine.sync(
            playlist_id=80010,
            platform=platform,
            direction=SyncDirection.BIDIRECTIONAL,
        )

        # f_100 added to remote, f_300 added to local
        assert result.added_to_remote == 1
        assert result.added_to_local == 1
        assert result.removed_from_local == 0
        assert result.removed_from_remote == 0


class TestPlatformRegistryIntegration:
    def test_register_and_list(self) -> None:
        reg = PlatformRegistry()
        p1 = InMemoryPlatform(name="ym")
        p2 = InMemoryPlatform(name="spotify")
        reg.register(p1)
        reg.register(p2)

        assert sorted(reg.list_connected()) == ["spotify", "ym"]
        assert reg.get("ym") is p1
