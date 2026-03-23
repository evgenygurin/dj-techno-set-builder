"""Tests for GA performance optimizations: _relocate_worst + adaptive 2-opt.

The core issue: _two_opt() with full fitness is O(n³) per call, and calling it
on every child in every generation (19,650 times for 214 tracks) takes 73,000+ seconds.

Solution: _relocate_worst() is O(n) per call, replaces _two_opt in the GA loop.
Full 2-opt is reserved for final polish on the single best solution.
"""

import time

import numpy as np
import pytest

from app.audio.set_generator import (
    GAConfig,
    GeneticSetGenerator,
    TrackData,
)


def _make_tracks(n: int = 10, seed: int = 42) -> list[TrackData]:
    """Create N test tracks with realistic techno BPMs."""
    rng = np.random.default_rng(seed)
    return [
        TrackData(
            track_id=i,
            bpm=126.0 + rng.random() * 24.0,  # 126-150 BPM range
            energy=0.3 + rng.random() * 0.6,
            key_code=int(rng.integers(0, 24)),
        )
        for i in range(n)
    ]


def _make_matrix(tracks: list[TrackData], seed: int = 42) -> np.ndarray:
    """Build a transition matrix with BPM-proximity scoring."""
    n = len(tracks)
    matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(n):
            if i != j:
                diff = abs(tracks[i].bpm - tracks[j].bpm)
                matrix[i, j] = max(0.01, 1.0 - diff / 30.0)
    return matrix


# ── _relocate_worst tests ──


def test_relocate_worst_maintains_valid_permutation():
    """After relocation, chromosome must contain same tracks, no duplicates."""
    tracks = _make_tracks(20)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    ch = np.arange(20, dtype=np.int32)
    np.random.default_rng(42).shuffle(ch)
    original_set = set(ch.tolist())

    gen._relocate_worst(ch)

    assert set(ch.tolist()) == original_set
    assert len(ch) == 20


def test_relocate_worst_never_worsens_transition_sum():
    """Relocation should not decrease total transition quality."""
    tracks = _make_tracks(30)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    ch = np.arange(30, dtype=np.int32)
    np.random.default_rng(7).shuffle(ch)

    # Sum of transition scores before
    sum_before = sum(matrix[ch[k], ch[k + 1]] for k in range(len(ch) - 1))

    gen._relocate_worst(ch)

    sum_after = sum(matrix[ch[k], ch[k + 1]] for k in range(len(ch) - 1))
    assert sum_after >= sum_before - 1e-9


def test_relocate_worst_improves_worst_edge():
    """The worst transition should improve or the track should move."""
    tracks = _make_tracks(15)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    # Build a chromosome with an obviously bad transition in the middle
    ch = np.array([0, 1, 2, 3, 14, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], dtype=np.int32)

    # Worst transition should be around track 14 (BPM ~150 between BPM ~127 tracks)
    worst_before = min(matrix[ch[k], ch[k + 1]] for k in range(len(ch) - 1))

    gen._relocate_worst(ch)

    worst_after = min(matrix[ch[k], ch[k + 1]] for k in range(len(ch) - 1))
    assert worst_after >= worst_before


def test_relocate_worst_no_op_for_tiny_chromosome():
    """Chromosomes with < 3 tracks should not be modified."""
    tracks = _make_tracks(5)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    ch = np.array([0, 1], dtype=np.int32)
    original = ch.copy()
    gen._relocate_worst(ch)

    np.testing.assert_array_equal(ch, original)


def test_relocate_worst_is_fast():
    """Single _relocate_worst call should be < 1ms for 214 tracks."""
    tracks = _make_tracks(214)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    ch = np.arange(214, dtype=np.int32)
    np.random.default_rng(42).shuffle(ch)

    t0 = time.perf_counter()
    for _ in range(100):
        gen._relocate_worst(ch)
    elapsed_ms = (time.perf_counter() - t0) / 100 * 1000

    assert elapsed_ms < 1.0, f"_relocate_worst took {elapsed_ms:.2f}ms (should be < 1ms)"


# ── _two_opt max_passes tests ──


def test_two_opt_max_passes_limits_iterations():
    """max_passes should cap the number of improvement passes."""
    tracks = _make_tracks(20)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    ch = np.arange(20, dtype=np.int32)
    np.random.default_rng(7).shuffle(ch)

    # With max_passes=1, should do at most 1 full pass
    ch1 = ch.copy()
    gen._two_opt(ch1, max_passes=1)
    fitness_1pass = gen._fitness(ch1)

    # With max_passes=None (unlimited), should converge further
    ch_full = ch.copy()
    gen._two_opt(ch_full)
    fitness_full = gen._fitness(ch_full)

    # Both should improve, but unlimited should be >= 1-pass
    assert fitness_full >= fitness_1pass - 1e-9


def test_two_opt_max_passes_zero_is_noop():
    """max_passes=0 should not modify the chromosome."""
    tracks = _make_tracks(15)
    matrix = _make_matrix(tracks)
    gen = GeneticSetGenerator(tracks, matrix, GAConfig(seed=42))

    ch = np.arange(15, dtype=np.int32)
    np.random.default_rng(7).shuffle(ch)
    original = ch.copy()

    gen._two_opt(ch, max_passes=0)

    np.testing.assert_array_equal(ch, original)


# ── Adaptive strategy: large sets skip per-child 2-opt ──


@pytest.mark.slow
def test_large_set_ga_completes_in_time():
    """214 tracks with GA should complete in < 30s (was 73,000+ seconds)."""
    tracks = _make_tracks(214)
    matrix = _make_matrix(tracks)

    config = GAConfig(
        population_size=50,
        generations=50,
        seed=42,
    )
    gen = GeneticSetGenerator(tracks, matrix, config)

    t0 = time.perf_counter()
    result = gen.run()
    elapsed = time.perf_counter() - t0

    assert elapsed < 30.0, f"GA took {elapsed:.1f}s (must be < 30s)"
    assert result.score > 0.0
    assert len(result.track_ids) == 214


def test_small_set_still_uses_two_opt():
    """Sets with ≤ 40 tracks should still use 2-opt (quality matters)."""
    tracks = _make_tracks(15)
    matrix = _make_matrix(tracks)

    config = GAConfig(
        population_size=20,
        generations=10,
        seed=42,
    )
    gen = GeneticSetGenerator(tracks, matrix, config)
    result = gen.run()

    # Quality should be good for small sets
    assert result.score > 0.3


@pytest.mark.slow
def test_ga_result_quality_large_set():
    """Large set should still produce a reasonable fitness score."""
    tracks = _make_tracks(100)
    matrix = _make_matrix(tracks)

    config = GAConfig(
        population_size=30,
        generations=30,
        seed=42,
    )
    gen = GeneticSetGenerator(tracks, matrix, config)
    result = gen.run()

    # Should find a reasonable solution even with fast local search
    assert result.score > 0.1
    assert len(result.track_ids) == 100
    # All unique
    assert len(set(result.track_ids)) == 100
