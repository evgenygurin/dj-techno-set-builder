"""Tests for EntityFinder — ref resolution to entity lookups."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.entity_finder import ArtistFinder, PlaylistFinder, SetFinder, TrackFinder
from app.mcp.refs import parse_ref
from app.mcp.types import FindResult


@pytest.fixture
def mock_track_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.search_by_title = AsyncMock(return_value=([], 0))
    repo.get_artists_for_tracks = AsyncMock(return_value={})
    return repo


@pytest.fixture
def mock_playlist_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.search_by_name = AsyncMock(return_value=([], 0))
    return repo


@pytest.fixture
def mock_set_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.search_by_name = AsyncMock(return_value=([], 0))
    return repo


@pytest.fixture
def mock_artist_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.search_by_name = AsyncMock(return_value=([], 0))
    return repo


class TestTrackFinder:
    async def test_find_by_local_id_found(self, mock_track_repo):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000
        mock_track_repo.get_by_id = AsyncMock(return_value=track)
        mock_track_repo.get_artists_for_tracks = AsyncMock(return_value={42: ["Boris Brejcha"]})

        finder = TrackFinder(mock_track_repo, mock_track_repo)
        ref = parse_ref("local:42")
        result = await finder.find(ref)

        assert isinstance(result, FindResult)
        assert result.exact is True
        assert len(result.entities) == 1
        assert result.entities[0].ref == "local:42"
        assert result.entities[0].title == "Gravity"
        assert result.entities[0].artist == "Boris Brejcha"

    async def test_find_by_local_id_not_found(self, mock_track_repo):
        finder = TrackFinder(mock_track_repo, mock_track_repo)
        ref = parse_ref("local:999")
        result = await finder.find(ref)

        assert result.exact is True
        assert len(result.entities) == 0

    async def test_find_by_text_query(self, mock_track_repo):
        track1 = MagicMock()
        track1.track_id = 42
        track1.title = "Gravity"
        track1.duration_ms = 360000
        track2 = MagicMock()
        track2.track_id = 43
        track2.title = "Butterfly Effect"
        track2.duration_ms = 300000

        mock_track_repo.search_by_title = AsyncMock(return_value=([track1, track2], 2))
        mock_track_repo.get_artists_for_tracks = AsyncMock(
            return_value={42: ["Boris Brejcha"], 43: ["Boris Brejcha"]}
        )

        finder = TrackFinder(mock_track_repo, mock_track_repo)
        ref = parse_ref("Boris Brejcha")
        result = await finder.find(ref, limit=10)

        assert result.exact is False
        assert len(result.entities) == 2
        assert result.source == "local"


class TestPlaylistFinder:
    async def test_find_by_id(self, mock_playlist_repo):
        playlist = MagicMock()
        playlist.playlist_id = 5
        playlist.name = "Techno develop"
        mock_playlist_repo.get_by_id = AsyncMock(return_value=playlist)

        finder = PlaylistFinder(mock_playlist_repo)
        ref = parse_ref("local:5")
        result = await finder.find(ref)

        assert result.exact is True
        assert result.entities[0].name == "Techno develop"

    async def test_find_by_text(self, mock_playlist_repo):
        p = MagicMock()
        p.playlist_id = 5
        p.name = "Techno develop"
        mock_playlist_repo.search_by_name = AsyncMock(return_value=([p], 1))

        finder = PlaylistFinder(mock_playlist_repo)
        ref = parse_ref("Techno")
        result = await finder.find(ref)

        assert len(result.entities) == 1


class TestSetFinder:
    async def test_find_by_id(self, mock_set_repo):
        dj_set = MagicMock()
        dj_set.set_id = 3
        dj_set.name = "Friday night"
        mock_set_repo.get_by_id = AsyncMock(return_value=dj_set)

        finder = SetFinder(mock_set_repo)
        ref = parse_ref("local:3")
        result = await finder.find(ref)

        assert result.exact is True
        assert result.entities[0].name == "Friday night"


class TestArtistFinder:
    async def test_find_by_id(self, mock_artist_repo):
        artist = MagicMock()
        artist.artist_id = 10
        artist.name = "Boris Brejcha"
        mock_artist_repo.get_by_id = AsyncMock(return_value=artist)

        finder = ArtistFinder(mock_artist_repo)
        ref = parse_ref("local:10")
        result = await finder.find(ref)

        assert result.exact is True
        assert result.entities[0].name == "Boris Brejcha"
