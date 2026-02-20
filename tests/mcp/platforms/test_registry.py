"""Tests for PlatformRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.mcp.platforms.protocol import (
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.mcp.platforms.registry import PlatformRegistry


@dataclass
class FakeAdapter:
    """Minimal MusicPlatform implementation for testing."""

    name: str = "fake"
    capabilities: frozenset[PlatformCapability] = frozenset(
        {PlatformCapability.SEARCH, PlatformCapability.PLAYLIST_READ}
    )
    closed: bool = field(default=False, init=False)

    async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]:
        return [PlatformTrack(platform_id="1", title=f"Result for {query}", artists="Artist")]

    async def get_track(self, platform_id: str) -> PlatformTrack:
        return PlatformTrack(platform_id=platform_id, title="Fake", artists="Fake")

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        return PlatformPlaylist(platform_id=platform_id, name="Fake PL", track_ids=[])

    async def create_playlist(self, name: str, track_ids: list[str]) -> str:
        return "new"

    async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        pass

    async def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        pass

    async def delete_playlist(self, playlist_id: str) -> None:
        pass

    async def get_download_url(self, track_id: str, *, bitrate: int = 320) -> str | None:
        return None

    async def close(self) -> None:
        self.closed = True


class TestPlatformRegistry:
    def test_register_and_get(self) -> None:
        reg = PlatformRegistry()
        adapter = FakeAdapter(name="ym")
        reg.register(adapter)

        assert reg.get("ym") is adapter

    def test_get_unknown_raises(self) -> None:
        reg = PlatformRegistry()
        with pytest.raises(KeyError, match="ym"):
            reg.get("ym")

    def test_is_connected(self) -> None:
        reg = PlatformRegistry()
        assert reg.is_connected("ym") is False

        reg.register(FakeAdapter(name="ym"))
        assert reg.is_connected("ym") is True

    def test_list_connected(self) -> None:
        reg = PlatformRegistry()
        reg.register(FakeAdapter(name="ym"))
        reg.register(FakeAdapter(name="spotify"))
        assert sorted(reg.list_connected()) == ["spotify", "ym"]

    def test_list_connected_empty(self) -> None:
        reg = PlatformRegistry()
        assert reg.list_connected() == []

    async def test_close_all(self) -> None:
        reg = PlatformRegistry()
        a1 = FakeAdapter(name="ym")
        a2 = FakeAdapter(name="spotify")
        reg.register(a1)
        reg.register(a2)

        await reg.close_all()
        assert a1.closed is True
        assert a2.closed is True

    def test_register_duplicate_replaces(self) -> None:
        reg = PlatformRegistry()
        a1 = FakeAdapter(name="ym")
        a2 = FakeAdapter(name="ym")
        reg.register(a1)
        reg.register(a2)

        assert reg.get("ym") is a2

    def test_has_capability(self) -> None:
        reg = PlatformRegistry()
        reg.register(FakeAdapter(name="ym"))

        assert reg.has_capability("ym", PlatformCapability.SEARCH) is True
        assert reg.has_capability("ym", PlatformCapability.DOWNLOAD) is False

    def test_has_capability_unknown_platform(self) -> None:
        reg = PlatformRegistry()
        assert reg.has_capability("ym", PlatformCapability.SEARCH) is False
