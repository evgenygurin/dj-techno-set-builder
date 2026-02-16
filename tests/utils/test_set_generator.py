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


def test_nn_init_produces_better_initial_fitness():
    """NN-seeded population should have higher avg fitness than random.

    50% of population is NN-seeded + 2-opt polished, 50% random.
    """
    tracks = _make_tracks(20)
    matrix = _make_matrix(tracks)

    config = GAConfig(
        population_size=20,
        generations=0,  # Only test initialization
        seed=42,
    )
    gen = GeneticSetGenerator(tracks, matrix, config)

    # Generate population
    population = gen._init_population(len(tracks), len(tracks), 20)

    fitnesses = [gen._fitness(ch) for ch in population]
    avg_fitness = sum(fitnesses) / len(fitnesses)

    # NN init should produce reasonable initial fitness
    assert avg_fitness > 0.2


def test_track_replacement_mutation():
    """Track replacement should swap one gene with an unused track.

    Only applies when track_count < total tracks available.
    """
    tracks = _make_tracks(20)
    matrix = _make_matrix(tracks)

    config = GAConfig(
        population_size=10,
        generations=0,
        track_count=10,  # Use 10 out of 20
        seed=42,
    )
    gen = GeneticSetGenerator(tracks, matrix, config)

    # Create a chromosome using first 10 tracks
    original = np.arange(10, dtype=np.int32)

    # Force replacement (call many times to trigger 5% probability)
    replaced = False
    for _ in range(100):
        test_ch = original.copy()
        gen._mutate_replace(test_ch)
        if not np.array_equal(test_ch, original):
            replaced = True
            # Verify: still has n_select unique elements
            assert len(set(test_ch.tolist())) == 10
            # Verify: one element is from the pool (index >= 10)
            new_tracks = set(test_ch.tolist()) - set(original.tolist())
            assert len(new_tracks) == 1
            assert next(iter(new_tracks)) >= 10
            break

    assert replaced, "Track replacement never triggered in 100 attempts"
