"""Tests for MusicPlatform protocol definition."""

from __future__ import annotations

from dataclasses import dataclass

from app.mcp.platforms.protocol import (
    MusicPlatform,
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)


class TestPlatformTrack:
    def test_create(self) -> None:
        t = PlatformTrack(
            platform_id="12345",
            title="Gravity",
            artists="Boris Brejcha",
            duration_ms=360000,
        )
        assert t.platform_id == "12345"
        assert t.duration_ms == 360000

    def test_optional_fields(self) -> None:
        t = PlatformTrack(
            platform_id="12345",
            title="Gravity",
            artists="Boris Brejcha",
        )
        assert t.duration_ms is None
        assert t.cover_uri is None


class TestPlatformPlaylist:
    def test_create(self) -> None:
        p = PlatformPlaylist(
            platform_id="1003",
            name="My Techno",
            track_ids=["111", "222", "333"],
            owner_id="250905515",
        )
        assert len(p.track_ids) == 3


class TestPlatformCapability:
    def test_values(self) -> None:
        assert PlatformCapability.SEARCH in PlatformCapability
        assert PlatformCapability.DOWNLOAD in PlatformCapability
        assert PlatformCapability.PLAYLIST_WRITE in PlatformCapability


class TestProtocolCompliance:
    """Verify that a minimal implementation satisfies the Protocol."""

    def test_dummy_adapter_satisfies_protocol(self) -> None:
        @dataclass
        class DummyAdapter:
            name: str = "dummy"
            capabilities: frozenset[PlatformCapability] = frozenset({PlatformCapability.SEARCH})

            async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]:
                return []

            async def get_track(self, platform_id: str) -> PlatformTrack:
                return PlatformTrack(
                    platform_id=platform_id,
                    title="test",
                    artists="test",
                )

            async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
                return PlatformPlaylist(
                    platform_id=platform_id,
                    name="test",
                    track_ids=[],
                )

            async def create_playlist(self, name: str, track_ids: list[str]) -> str:
                return "new_id"

            async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
                pass

            async def remove_tracks_from_playlist(
                self, playlist_id: str, track_ids: list[str]
            ) -> None:
                pass

            async def delete_playlist(self, playlist_id: str) -> None:
                pass

            async def get_download_url(self, track_id: str, *, bitrate: int = 320) -> str | None:
                return None

            async def close(self) -> None:
                pass

        adapter = DummyAdapter()
        # Protocol check via runtime_checkable
        assert isinstance(adapter, MusicPlatform)
        platform: MusicPlatform = adapter
        assert platform.name == "dummy"
        assert PlatformCapability.SEARCH in platform.capabilities
