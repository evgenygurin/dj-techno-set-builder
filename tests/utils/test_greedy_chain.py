"""Tests for the greedy chain builder."""

from __future__ import annotations

from app.utils.audio.greedy_chain import GreedyChainResult, build_greedy_chain
from app.utils.audio.set_generator import TrackData


def _make_tracks(count: int) -> list[TrackData]:
    """Create a pool of synthetic tracks with varied BPM, energy, and key."""
    tracks: list[TrackData] = []
    for i in range(count):
        tracks.append(
            TrackData(
                track_id=80000 + i,
                bpm=125.0 + (i % 8) * 0.5,  # 125..128.5 BPM range
                energy=0.3 + (i % 10) * 0.06,  # 0.30..0.84 energy range
                key_code=i % 24,  # cycle through all keys
            )
        )
    return tracks


def test_greedy_chain_basic():
    """30-track pool, select 10 — verify count and reasonable quality."""
    tracks = _make_tracks(30)
    result = build_greedy_chain(tracks, track_count=10, energy_arc="classic")

    assert isinstance(result, GreedyChainResult)
    assert len(result.track_ids) == 10
    assert len(result.scores) == 9  # n-1 transitions
    assert result.avg_score > 0.5
    # All track IDs should be unique
    assert len(set(result.track_ids)) == 10


def test_greedy_chain_single_track():
    """1-track pool — returns 1 track, no scores."""
    tracks = [TrackData(track_id=1, bpm=130.0, energy=0.5, key_code=0)]
    result = build_greedy_chain(tracks, track_count=5)

    assert result.track_ids == [1]
    assert result.scores == []
    assert result.avg_score == 0.0
    assert result.min_score == 0.0


def test_greedy_chain_respects_count():
    """Pool of 50 tracks, request 15 — verify exactly 15 selected."""
    tracks = _make_tracks(50)
    result = build_greedy_chain(tracks, track_count=15, energy_arc="progressive")

    assert len(result.track_ids) == 15
    assert len(result.scores) == 14
    assert len(set(result.track_ids)) == 15  # all unique


def test_greedy_chain_count_capped_by_pool():
    """Request more tracks than available — returns all."""
    tracks = _make_tracks(5)
    result = build_greedy_chain(tracks, track_count=20)

    assert len(result.track_ids) == 5


def test_greedy_chain_all_energy_arcs():
    """All four energy arc types produce valid results."""
    tracks = _make_tracks(30)
    for arc in ("classic", "progressive", "roller", "wave"):
        result = build_greedy_chain(tracks, track_count=10, energy_arc=arc)
        assert len(result.track_ids) == 10, f"Failed for arc={arc}"
        assert result.avg_score >= 0.0
