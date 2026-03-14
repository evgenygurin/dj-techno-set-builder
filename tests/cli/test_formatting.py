"""Tests for CLI formatting helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.cli._formatting import (
    _ms_to_mmss,
    _score_style,
    _truncate,
    build_result_panel,
    features_panel,
    playlists_table,
    sets_table,
    tracks_table,
    transitions_table,
)

# ── Helper function tests ──────────────────────────────────────────────────


def test_ms_to_mmss_basic() -> None:
    assert _ms_to_mmss(0) == "0:00"
    assert _ms_to_mmss(60_000) == "1:00"
    assert _ms_to_mmss(90_000) == "1:30"
    assert _ms_to_mmss(420_000) == "7:00"
    assert _ms_to_mmss(359_999) == "5:59"


def test_score_style() -> None:
    assert _score_style(0.90) == "green"
    assert _score_style(0.85) == "green"
    assert _score_style(0.84) == "yellow"
    assert _score_style(0.70) == "yellow"
    assert _score_style(0.50) == "red"
    assert _score_style(0.01) == "red"
    assert _score_style(0.0) == "red bold"


def test_truncate() -> None:
    assert _truncate("short", 10) == "short"
    assert _truncate("exactly ten", 11) == "exactly ten"
    assert _truncate("this is a long string", 10) == "this is a\u2026"


# ── Table builder tests ───────────────────────────────────────────────────


def _make_track(
    track_id: int = 1,
    title: str = "Test Track",
    duration_ms: int = 300000,
) -> SimpleNamespace:
    return SimpleNamespace(track_id=track_id, title=title, duration_ms=duration_ms, status=0)


def _make_playlist(playlist_id: int = 1, name: str = "Test Playlist") -> SimpleNamespace:
    return SimpleNamespace(
        playlist_id=playlist_id,
        name=name,
        source_of_truth="local",
        created_at=datetime(2025, 1, 15, tzinfo=UTC),
    )


def _make_set(set_id: int = 1, name: str = "Test Set") -> SimpleNamespace:
    return SimpleNamespace(
        set_id=set_id,
        name=name,
        template_name="classic_60",
        created_at=datetime(2025, 1, 15, tzinfo=UTC),
    )


def test_tracks_table_builds() -> None:
    """Tracks table builds with data."""
    table = tracks_table([_make_track(1, "Song A"), _make_track(2, "Song B")])
    assert table.title == "Tracks"
    assert table.row_count == 2


def test_tracks_table_custom_title() -> None:
    table = tracks_table([_make_track()], title="My Tracks")
    assert table.title == "My Tracks"


def test_tracks_table_with_artists() -> None:
    artists_map = {1: ["DJ Alpha", "DJ Beta"]}
    table = tracks_table([_make_track(1)], artists_map=artists_map)
    assert table.row_count == 1


def test_tracks_table_empty() -> None:
    table = tracks_table([])
    assert table.row_count == 0


def test_playlists_table_builds() -> None:
    table = playlists_table([_make_playlist(1), _make_playlist(2, "Other")])
    assert table.title == "Playlists"
    assert table.row_count == 2


def test_sets_table_builds() -> None:
    table = sets_table([_make_set(1), _make_set(2, "Set B")])
    assert table.title == "DJ Sets"
    assert table.row_count == 2


def test_transitions_table_builds() -> None:
    scores = [
        {
            "from_title": "Track A",
            "to_title": "Track B",
            "total": 0.92,
            "bpm": 0.95,
            "harmonic": 0.88,
            "energy": 0.85,
            "recommended_type": "blend",
        },
        {
            "from_title": "Track B",
            "to_title": "Track C",
            "total": 0.0,
            "bpm": 0.0,
            "harmonic": 0.0,
            "energy": 0.0,
            "recommended_type": "—",
        },
    ]
    table = transitions_table(scores)
    assert table.title == "Transitions"
    assert table.row_count == 2


def test_transitions_table_weak_flag() -> None:
    """Transitions below 0.85 get flagged."""
    scores = [
        {
            "from_title": "A",
            "to_title": "B",
            "total": 0.60,
            "bpm": 0.7,
            "harmonic": 0.5,
            "energy": 0.6,
            "recommended_type": "drum_cut",
        },
    ]
    table = transitions_table(scores)
    assert table.row_count == 1


# ── Panel tests ──────────────────────────────────────────────────────────


def test_build_result_panel() -> None:
    panel = build_result_panel(
        set_id=1, version_id=2, track_count=15, total_score=0.89, avg_transition=0.87
    )
    assert panel.title == "Set Build Result"


def test_features_panel() -> None:
    feat = SimpleNamespace(
        track_id=42,
        bpm=133.5,
        lufs_i=-8.2,
        tempo_confidence=0.95,
        bpm_stability=0.88,
        energy_mean=0.45,
        energy_max=0.82,
        key_code=5,
        centroid_mean_hz=2500.0,
        onset_rate_mean=4.5,
        kick_prominence=0.65,
    )
    with patch("app.cli._formatting._key_code_to_camelot", return_value="4A"):
        panel = features_panel(feat, track_title="Test Track")
    assert "Audio Features" in str(panel.title)
    assert "42" in str(panel.title)


def test_features_panel_no_optional() -> None:
    """Features panel works without optional fields."""
    feat = SimpleNamespace(
        track_id=1,
        bpm=128.0,
        lufs_i=-10.0,
        tempo_confidence=0.9,
        bpm_stability=0.85,
        energy_mean=0.4,
        energy_max=0.7,
        key_code=0,
    )
    with patch("app.cli._formatting._key_code_to_camelot", return_value="1A"):
        panel = features_panel(feat)
    assert panel.title is not None
