"""Tests for GA set generator enhancements (Phase 3b)."""

import numpy as np

from app.utils.audio.set_generator import (
    GAConfig,
    GeneticSetGenerator,
    TrackData,
)


def _make_tracks(n: int = 10) -> list[TrackData]:
    """Create N test tracks with varying features."""
    return [
        TrackData(
            track_id=i,
            bpm=125.0 + i * 0.5,
            energy=0.3 + (i / n) * 0.6,  # Rising energy
            key_code=i % 12,
        )
        for i in range(n)
    ]


def _make_matrix(tracks: list[TrackData]) -> np.ndarray:
    """Build a simple transition matrix based on BPM proximity."""
    n = len(tracks)
    matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(n):
            if i != j:
                diff = abs(tracks[i].bpm - tracks[j].bpm)
                matrix[i, j] = max(0.0, 1.0 - diff / 10.0)
    return matrix


def test_two_opt_uses_full_fitness():
    """Full-fitness 2-opt should improve energy arc, not just transitions.

    Regression test: old 2-opt only optimized transition matrix.
    New 2-opt should improve composite fitness (transition + arc + bpm).
    """
    tracks = _make_tracks(15)
    matrix = _make_matrix(tracks)

    # Run with seed for reproducibility
    config = GAConfig(
        population_size=20,
        generations=5,
        seed=42,
    )
    gen = GeneticSetGenerator(tracks, matrix, config)

    # Create a deliberately bad chromosome
    bad_order = np.array(list(reversed(range(15))), dtype=np.int32)
    fitness_before = gen._fitness(bad_order)

    # Apply full-fitness 2-opt
    improved = bad_order.copy()
    gen._two_opt(improved)
    fitness_after = gen._fitness(improved)

    assert fitness_after >= fitness_before
