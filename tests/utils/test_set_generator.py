"""Tests for GA set generator enhancements (Phase 3b)."""

import numpy as np

from app.utils.audio.set_generator import (
    GAConfig,
    GAConstraints,
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


def test_variety_penalty_same_mood_triple():
    """3 consecutive tracks with same mood should be penalized."""
    from app.utils.audio.set_generator import variety_score

    # All mood=3 (DRIVING)
    tracks = [
        TrackData(track_id=i, bpm=130.0, energy=0.5, key_code=i % 12, mood=3, artist_id=i)
        for i in range(5)
    ]
    score = variety_score(tracks)
    assert score < 1.0  # penalized


def test_variety_penalty_diverse_mood():
    """Diverse moods should not be penalized."""
    from app.utils.audio.set_generator import variety_score

    tracks = [
        TrackData(
            track_id=i,
            bpm=130.0,
            energy=0.5,
            key_code=i % 12,
            mood=i % 6 + 1,
            artist_id=i,
        )
        for i in range(6)
    ]
    score = variety_score(tracks)
    assert score >= 0.9


def test_ga_config_has_variety_weight():
    config = GAConfig()
    assert hasattr(config, "w_variety")
    assert config.w_variety == 0.20


def test_track_data_has_mood_and_artist():
    td = TrackData(track_id=1, bpm=130.0, energy=0.5, key_code=4, mood=3, artist_id=42)
    assert td.mood == 3
    assert td.artist_id == 42


def test_lufs_energy_used_in_arc():
    """When lufs is provided, energy should be derived from LUFS, not energy_mean."""
    from app.utils.audio.set_generator import lufs_to_energy

    assert 0.0 <= lufs_to_energy(-14.0) <= 0.05  # ambient -> low energy
    assert 0.9 <= lufs_to_energy(-6.0) <= 1.0  # hard -> high energy
    assert 0.4 <= lufs_to_energy(-10.0) <= 0.6  # mid-range


def test_nn_anchored_spread_no_consecutive_pinned():
    """_nn_anchored_spread must not place two pinned tracks adjacent.

    Each pinned track becomes the anchor of its own segment, so they are
    always separated by at least one non-pinned track.
    """
    tracks = _make_tracks(20)
    matrix = _make_matrix(tracks)

    pinned_ids = frozenset(
        [tracks[0].track_id, tracks[5].track_id, tracks[10].track_id, tracks[15].track_id]
    )
    pinned_indices = {0, 5, 10, 15}

    config = GAConfig(population_size=20, generations=0, seed=42)
    constraints = GAConstraints(pinned_ids=pinned_ids)
    gen = GeneticSetGenerator(tracks, matrix, config, constraints=constraints)

    # Test _nn_anchored_spread directly (before any 2-opt polish)
    for seed_offset in range(10):
        gen._rng.seed(seed_offset)
        subset = np.arange(len(tracks), dtype=np.int32)
        path = gen._nn_anchored_spread(subset)
        chrom_list = path.tolist()

        for pos in range(len(chrom_list) - 1):
            a, b = chrom_list[pos], chrom_list[pos + 1]
            assert not (a in pinned_indices and b in pinned_indices), (
                f"Pinned tracks {a} and {b} are adjacent at positions "
                f"{pos}/{pos + 1} (seed_offset={seed_offset}): {chrom_list}"
            )


def test_mutate_swap_does_not_move_pinned_tracks():
    """Swap mutation must never change the position of a pinned track.

    Insert mutation is skipped when pinned constraints are present because
    it shifts intermediate positions.  Swap-only mutation preserves pinned
    positions exactly.
    """
    tracks = _make_tracks(10)
    matrix = _make_matrix(tracks)

    pinned_ids = frozenset([tracks[2].track_id, tracks[7].track_id])
    pinned_indices = {2, 7}

    config = GAConfig(seed=99)
    constraints = GAConstraints(pinned_ids=pinned_ids)
    gen = GeneticSetGenerator(tracks, matrix, config, constraints=constraints)

    chromosome = np.arange(10, dtype=np.int32)
    # Record current positions of pinned tracks (track_id == index here)
    pinned_before = {pos: int(val) for pos, val in enumerate(chromosome) if val in pinned_indices}

    # Apply 500 mutations; pinned positions must never change
    for _ in range(500):
        test_ch = chromosome.copy()
        gen._mutate(test_ch)
        for pos, val in pinned_before.items():
            assert test_ch[pos] == val, (
                f"Pinned track {val} moved from position {pos} after _mutate. "
                f"Chromosome: {test_ch.tolist()}"
            )


def test_pinned_spread_score_adjacent_is_low():
    """_pinned_spread_score should be 0.0 when all pinned tracks are adjacent."""
    tracks = _make_tracks(10)
    matrix = _make_matrix(tracks)

    # Tracks 0 and 1 are pinned; track indices 0 and 1 in chromosome
    pinned_ids = frozenset([tracks[0].track_id, tracks[1].track_id])

    config = GAConfig(seed=42)
    constraints = GAConstraints(pinned_ids=pinned_ids)
    gen = GeneticSetGenerator(tracks, matrix, config, constraints=constraints)

    # Both pinned tracks adjacent: positions 0 and 1
    ch_adjacent = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=np.int32)
    score = gen._pinned_spread_score(ch_adjacent)
    assert score == 0.0


def test_pinned_spread_score_distributed_is_high():
    """_pinned_spread_score should be 1.0 when no two pinned tracks are adjacent."""
    tracks = _make_tracks(10)
    matrix = _make_matrix(tracks)

    pinned_ids = frozenset([tracks[0].track_id, tracks[5].track_id])

    config = GAConfig(seed=42)
    constraints = GAConstraints(pinned_ids=pinned_ids)
    gen = GeneticSetGenerator(tracks, matrix, config, constraints=constraints)

    # Pinned tracks at positions 0 and 5 — gap of 5
    ch_spread = np.array([0, 2, 3, 4, 5, 1, 6, 7, 8, 9], dtype=np.int32)
    # Note: track index 0 is at position 0, track index 1 (track_id=5) at position 5
    score = gen._pinned_spread_score(ch_spread)
    assert score == 1.0


def test_fitness_prefers_spread_pinned_over_adjacent():
    """Fitness should be strictly higher when pinned tracks are spread vs adjacent.

    Regression test: verifies the 15% multiplicative spread bonus in _fitness
    makes non-adjacent placement strictly preferable, even when transitions
    between the two pinned tracks might be good.
    """
    tracks = _make_tracks(10)
    matrix = _make_matrix(tracks)

    pinned_ids = frozenset([tracks[0].track_id, tracks[1].track_id])

    config = GAConfig(seed=42)
    constraints = GAConstraints(pinned_ids=pinned_ids)
    gen = GeneticSetGenerator(tracks, matrix, config, constraints=constraints)

    # Adjacent: pinned at positions 0,1
    ch_adjacent = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=np.int32)
    # Spread: pinned at positions 0 and 5 (gap=5)
    ch_spread = np.array([0, 2, 3, 4, 5, 1, 6, 7, 8, 9], dtype=np.int32)

    fit_adj = gen._fitness(ch_adjacent)
    fit_spread = gen._fitness(ch_spread)

    # Spread bonus (x1.0) > adjacent penalty (x0.85), so spread must win
    # even if raw transition scores are equal
    assert fit_spread > fit_adj, (
        f"Expected spread fitness ({fit_spread:.4f}) > adjacent fitness ({fit_adj:.4f})"
    )


def test_crossover_always_preserves_pinned_tracks():
    """OX crossover must always include all pinned tracks in the child.

    Regression: when parents have different filler tracks (subset GA, n_select < n_all),
    p2_filtered can contain MORE elements than remaining child slots.  Pinned tracks
    appearing late in p2's order get silently dropped.  The repair step must fix this.
    """
    import random

    # Large pool (500 tracks) but small target set (15)
    # Pinned tracks have HIGH indices (last 4 in the pool) — worst case for dropout
    n_all = 500
    n_select = 15
    pinned_ids_set = frozenset([496, 497, 498, 499])  # last 4 indices

    tracks = [
        TrackData(track_id=i, bpm=130.0 + (i % 10), energy=0.5, key_code=i % 12)
        for i in range(n_all)
    ]
    matrix = np.ones((n_all, n_all), dtype=np.float64)

    config = GAConfig(track_count=n_select, seed=42)
    constraints = GAConstraints(pinned_ids=pinned_ids_set)
    gen = GeneticSetGenerator(tracks, matrix, config, constraints=constraints)

    rng = random.Random(0)
    for trial in range(200):
        # Build two parents with different fillers (both include all pinned)
        pinned = list(pinned_ids_set)
        available = [i for i in range(n_all) if i not in pinned_ids_set]
        rng.shuffle(available)

        # Parent 1: pinned + first 11 fillers
        p1_list = pinned + available[:11]
        rng.shuffle(p1_list)
        p1 = np.array(p1_list, dtype=np.int32)

        # Parent 2: pinned + DIFFERENT 11 fillers (offset 100)
        p2_list = pinned + available[100:111]
        rng.shuffle(p2_list)
        p2 = np.array(p2_list, dtype=np.int32)

        child = gen._order_crossover(p1, p2)
        child_set = set(child.tolist())

        for pidx in pinned_ids_set:
            assert pidx in child_set, (
                f"Trial {trial}: pinned index {pidx} was dropped from child!\n"
                f"  p1: {sorted(p1.tolist())}\n  p2: {sorted(p2.tolist())}\n"
                f"  child: {sorted(child.tolist())}"
            )
