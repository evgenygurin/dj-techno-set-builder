"""Tests for YandexMusicAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.mcp.platforms.protocol import PlatformCapability
from app.mcp.platforms.yandex import YandexMusicAdapter


@pytest.fixture
def mock_ym_client() -> AsyncMock:
    """Create a mock YandexMusicClient."""
    client = AsyncMock()
    client.search_tracks = AsyncMock(
        return_value=[
            {
                "id": 12345,
                "title": "Gravity",
                "artists": [{"name": "Boris Brejcha", "various": False}],
                "durationMs": 360000,
                "albums": [
                    {
                        "id": 999,
                        "title": "Gravity EP",
                        "type": "single",
                        "genre": "techno",
                        "year": 2023,
                        "labels": [{"name": "Fckng Serious"}],
                        "releaseDate": "2023-06-15",
                    }
                ],
                "coverUri": "avatars.yandex.net/get-music-content/123/cover/%%",
                "explicit": False,
            }
        ]
    )
    client.fetch_playlist_tracks = AsyncMock(
        return_value=[
            {"track": {"id": 111, "title": "A", "artists": [{"name": "X", "various": False}]}},
            {"track": {"id": 222, "title": "B", "artists": [{"name": "Y", "various": False}]}},
        ]
    )
    client.fetch_tracks_metadata = AsyncMock(
        return_value=[
            {
                "id": 12345,
                "title": "Gravity",
                "artists": [{"name": "Boris Brejcha", "various": False}],
                "durationMs": 360000,
                "albums": [],
                "coverUri": None,
                "explicit": False,
            }
        ]
    )
    client.fetch_playlist = AsyncMock(
        return_value={
            "kind": 1003,
            "revision": 5,
            "tracks": [
                {"track": {"id": 111}},
                {"track": {"id": 222}},
            ],
        }
    )
    client.create_playlist = AsyncMock(return_value=42)
    client.add_tracks_to_playlist = AsyncMock(return_value={"kind": 42, "revision": 2})
    client.remove_tracks_from_playlist = AsyncMock(return_value={"kind": 1003, "revision": 6})
    client.delete_playlist = AsyncMock()
    client.resolve_download_url = AsyncMock(return_value="https://cdn.example.com/track.mp3")
    client.close = AsyncMock()
    return client


@pytest.fixture
def adapter(mock_ym_client: AsyncMock) -> YandexMusicAdapter:
    return YandexMusicAdapter(client=mock_ym_client, user_id="250905515")


class TestYandexMusicAdapterProperties:
    def test_name(self, adapter: YandexMusicAdapter) -> None:
        assert adapter.name == "ym"

    def test_capabilities(self, adapter: YandexMusicAdapter) -> None:
        caps = adapter.capabilities
        assert PlatformCapability.SEARCH in caps
        assert PlatformCapability.DOWNLOAD in caps
        assert PlatformCapability.PLAYLIST_READ in caps
        assert PlatformCapability.PLAYLIST_WRITE in caps
        assert PlatformCapability.LIKES in caps


class TestSearchTracks:
    async def test_search_returns_platform_tracks(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        results = await adapter.search_tracks("Boris Brejcha", limit=10)

        assert len(results) == 1
        assert results[0].platform_id == "12345"
        assert results[0].title == "Gravity"
        assert results[0].artists == "Boris Brejcha"
        assert results[0].duration_ms == 360000
        mock_ym_client.search_tracks.assert_called_once_with("Boris Brejcha")

    async def test_search_empty(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        mock_ym_client.search_tracks.return_value = []
        results = await adapter.search_tracks("nonexistent")
        assert results == []


class TestGetTrack:
    async def test_get_track(self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock) -> None:
        track = await adapter.get_track("12345")

        assert track.platform_id == "12345"
        assert track.title == "Gravity"
        mock_ym_client.fetch_tracks_metadata.assert_called_once_with(["12345"])

    async def test_get_track_not_found(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        mock_ym_client.fetch_tracks_metadata.return_value = []
        with pytest.raises(ValueError, match="not found"):
            await adapter.get_track("99999")


class TestGetPlaylist:
    async def test_get_playlist(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        pl = await adapter.get_playlist("1003")

        assert pl.platform_id == "1003"
        assert pl.track_ids == ["111", "222"]
        assert pl.owner_id == "250905515"
        mock_ym_client.fetch_playlist_tracks.assert_called_once_with("250905515", "1003")

    async def test_get_playlist_empty(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        mock_ym_client.fetch_playlist_tracks.return_value = []
        pl = await adapter.get_playlist("1003")
        assert pl.track_ids == []


class TestGetDownloadUrl:
    async def test_download_url(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        url = await adapter.get_download_url("12345", bitrate=320)
        assert url == "https://cdn.example.com/track.mp3"
        mock_ym_client.resolve_download_url.assert_called_once_with("12345", prefer_bitrate=320)

    async def test_download_url_failure(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        mock_ym_client.resolve_download_url.side_effect = ValueError("No download info")
        url = await adapter.get_download_url("99999")
        assert url is None


class TestPlaylistWrite:
    """Playlist write operations via YM diff-based API."""

    async def test_create_playlist_without_tracks(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        result = await adapter.create_playlist("My Playlist", [])

        assert result == "42"
        mock_ym_client.create_playlist.assert_called_once_with("250905515", "My Playlist")
        mock_ym_client.add_tracks_to_playlist.assert_not_called()

    async def test_create_playlist_with_tracks(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        result = await adapter.create_playlist("My Playlist", ["100", "200"])

        assert result == "42"
        mock_ym_client.create_playlist.assert_called_once_with("250905515", "My Playlist")
        mock_ym_client.add_tracks_to_playlist.assert_called_once_with(
            "250905515",
            42,
            [{"id": "100", "albumId": "0"}, {"id": "200", "albumId": "0"}],
            revision=1,
        )

    async def test_add_tracks_to_playlist(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        await adapter.add_tracks_to_playlist("1003", ["333", "444"])

        mock_ym_client.fetch_playlist.assert_called_once_with("250905515", "1003")
        mock_ym_client.add_tracks_to_playlist.assert_called_once_with(
            "250905515",
            1003,
            [{"id": "333", "albumId": "0"}, {"id": "444", "albumId": "0"}],
            revision=5,
        )

    async def test_remove_tracks_from_playlist(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        await adapter.remove_tracks_from_playlist("1003", ["222"])

        mock_ym_client.fetch_playlist.assert_called_once_with("250905515", "1003")
        # Track 222 is at index 1, should be removed
        mock_ym_client.remove_tracks_from_playlist.assert_called_once_with(
            "250905515", 1003, from_index=1, to_index=2, revision=5
        )

    async def test_remove_multiple_tracks_reverse_order(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        """Removing multiple tracks happens in reverse index order."""
        await adapter.remove_tracks_from_playlist("1003", ["111", "222"])

        # Two calls expected: index 1 first (reversed), then index 0
        calls = mock_ym_client.remove_tracks_from_playlist.call_args_list
        assert len(calls) == 2
        # First call removes index 1 (track 222)
        assert calls[0].kwargs["from_index"] == 1
        # Second call removes index 0 (track 111)
        assert calls[1].kwargs["from_index"] == 0

    async def test_delete_playlist(
        self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock
    ) -> None:
        await adapter.delete_playlist("1003")
        mock_ym_client.delete_playlist.assert_called_once_with("250905515", 1003)


class TestClose:
    async def test_close(self, adapter: YandexMusicAdapter, mock_ym_client: AsyncMock) -> None:
        await adapter.close()
        mock_ym_client.close.assert_called_once()
