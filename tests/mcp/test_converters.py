"""Tests for ORM-to-Response converters."""

from unittest.mock import MagicMock

from app.mcp.converters import (
    artist_to_summary,
    playlist_to_summary,
    set_to_summary,
    track_to_detail,
    track_to_summary,
)


class TestTrackToSummary:
    def test_without_features(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000

        result = track_to_summary(track, {42: ["Boris Brejcha"]})
        assert result.ref == "local:42"
        assert result.title == "Gravity"
        assert result.artist == "Boris Brejcha"
        assert result.bpm is None
        assert result.key is None

    def test_with_features(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000

        features = MagicMock()
        features.bpm = 140.0
        features.lufs_i = -8.3
        features.key_code = 18  # Am = 8A

        result = track_to_summary(track, {42: ["Boris Brejcha"]}, features)
        assert result.bpm == 140.0
        assert result.energy_lufs == -8.3
        assert result.key == "8A"

    def test_unknown_artist(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Mystery"
        track.duration_ms = 360000

        result = track_to_summary(track, {})
        assert result.artist == "Unknown"


class TestTrackToDetail:
    def test_with_genres_labels(self):
        track = MagicMock()
        track.track_id = 42
        track.title = "Gravity"
        track.duration_ms = 360000

        result = track_to_detail(
            track,
            artists_map={42: ["Boris Brejcha"]},
            genres=["Techno"],
            labels=["Fckng Serious"],
            albums=["Gravity EP"],
        )
        assert result.has_features is False
        assert result.genres == ["Techno"]
        assert result.labels == ["Fckng Serious"]
        assert result.albums == ["Gravity EP"]


class TestPlaylistToSummary:
    def test_basic(self):
        playlist = MagicMock()
        playlist.playlist_id = 5
        playlist.name = "Techno develop"

        result = playlist_to_summary(playlist, item_count=247)
        assert result.ref == "local:5"
        assert result.name == "Techno develop"
        assert result.track_count == 247


class TestSetToSummary:
    def test_basic(self):
        dj_set = MagicMock()
        dj_set.set_id = 3
        dj_set.name = "Friday night"

        result = set_to_summary(dj_set, version_count=2, track_count=15)
        assert result.ref == "local:3"
        assert result.version_count == 2
        assert result.track_count == 15


class TestArtistToSummary:
    def test_basic(self):
        artist = MagicMock()
        artist.artist_id = 10
        artist.name = "Boris Brejcha"

        result = artist_to_summary(artist, tracks_in_db=5)
        assert result.ref == "local:10"
        assert result.tracks_in_db == 5
