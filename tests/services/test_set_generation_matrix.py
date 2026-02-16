"""Tests for two-tier sparse matrix builder."""

import numpy as np
import pytest

from app.services.transition_scoring import (
    HardConstraints,
    TrackFeatures,
    TransitionScoringService,
)


def _make_features(**overrides: object) -> TrackFeatures:
    """Helper: create TrackFeatures with sensible defaults."""
    defaults: dict[str, object] = {
        "bpm": 128.0,
        "energy_lufs": -14.0,
        "key_code": 0,
        "harmonic_density": 0.7,
        "centroid_hz": 2000.0,
        "band_ratios": [0.3, 0.5, 0.2],
        "onset_rate": 5.0,
    }
    defaults.update(overrides)
    return TrackFeatures(**defaults)  # type: ignore[arg-type]


# ── Matrix shape and diagonal ──


def test_matrix_shape_n_by_n():
    """Matrix should be NxN for N tracks."""
    from app.services.set_generation import _build_matrix_two_tier

    features = [_make_features(bpm=125 + i * 2) for i in range(5)]
    scorer = TransitionScoringService()

    matrix = _build_matrix_two_tier(scorer, features, tier1_threshold=0.15)

    assert matrix.shape == (5, 5)


def test_matrix_diagonal_is_zero():
    """Diagonal should be all zeros (no self-transitions)."""
    from app.services.set_generation import _build_matrix_two_tier

    features = [_make_features(bpm=125 + i * 2) for i in range(4)]
    scorer = TransitionScoringService()

    matrix = _build_matrix_two_tier(scorer, features, tier1_threshold=0.15)

    for i in range(4):
        assert matrix[i, i] == 0.0


# ── No zeros off diagonal (Nina Kraviz principle) ──


def test_no_zeros_off_diagonal():
    """Every off-diagonal entry must be > 0 (no hard cutoffs)."""
    from app.services.set_generation import _build_matrix_two_tier

    # Mix of very different features to trigger both tiers
    features = [
        _make_features(bpm=70.0, key_code=0, energy_lufs=-6.0),
        _make_features(bpm=128.0, key_code=6, energy_lufs=-14.0),
        _make_features(bpm=150.0, key_code=12, energy_lufs=-20.0),
        _make_features(bpm=140.0, key_code=3, energy_lufs=-10.0),
    ]
    scorer = TransitionScoringService()

    matrix = _build_matrix_two_tier(scorer, features, tier1_threshold=0.15)

    n = len(features)
    for i in range(n):
        for j in range(n):
            if i != j:
                assert matrix[i, j] > 0.0, f"Zero found at [{i}, {j}]"


# ── Tier1 threshold behaviour ──


def test_tier1_threshold_skips_some_full_scores():
    """With tier1_threshold, some pairs get quick_score instead of full score.

    Disable hard constraints so score_transition never returns 0.0 —
    this isolates the two-tier mechanism from hard-reject fallback.
    """
    from app.services.set_generation import _build_matrix_two_tier

    features = [
        _make_features(bpm=128.0, key_code=0, energy_lufs=-14.0),
        _make_features(bpm=170.0, key_code=12, energy_lufs=-20.0),
        _make_features(bpm=130.0, key_code=1, energy_lufs=-13.0),
    ]
    no_hard = HardConstraints(
        max_bpm_diff=None,
        max_camelot_distance=None,
        max_energy_delta_lufs=None,
    )
    scorer = TransitionScoringService(hard_constraints=no_hard)

    matrix_hi = _build_matrix_two_tier(scorer, features, tier1_threshold=0.50)
    matrix_lo = _build_matrix_two_tier(scorer, features, tier1_threshold=0.0)

    # Without hard constraints, score_transition always > 0 and differs from
    # quick_score. Any pair where quick < 0.50 will produce different values.
    diff = np.abs(matrix_hi - matrix_lo)
    assert np.any(diff > 1e-6), "Matrices are identical — tier1 threshold has no effect"


def test_tier1_threshold_zero_matches_full_score():
    """tier1_threshold=0.0 → every pair gets full score_transition."""
    from app.services.set_generation import _build_matrix_two_tier

    features = [
        _make_features(bpm=128.0, key_code=0, energy_lufs=-14.0),
        _make_features(bpm=132.0, key_code=2, energy_lufs=-12.0),
    ]
    scorer = TransitionScoringService()

    matrix = _build_matrix_two_tier(scorer, features, tier1_threshold=0.0)

    # Manual full score
    full_01 = scorer.score_transition(features[0], features[1])
    full_10 = scorer.score_transition(features[1], features[0])

    # When full score is 0.0 (hard-reject), two-tier uses quick_score instead
    quick_01 = scorer.quick_score(features[0], features[1])
    quick_10 = scorer.quick_score(features[1], features[0])

    expected_01 = full_01 if full_01 > 0.0 else quick_01
    expected_10 = full_10 if full_10 > 0.0 else quick_10

    assert matrix[0, 1] == pytest.approx(expected_01, abs=1e-6)
    assert matrix[1, 0] == pytest.approx(expected_10, abs=1e-6)


# ── Performance: tier 1 should skip significant fraction ──


def test_tier1_skips_fraction_for_diverse_set():
    """With diverse features, some fraction should skip tier 2.

    Disable hard constraints to isolate two-tier mechanism.
    """
    from app.services.set_generation import _build_matrix_two_tier

    features = [
        _make_features(bpm=70.0, key_code=0, energy_lufs=-6.0),
        _make_features(bpm=90.0, key_code=4, energy_lufs=-10.0),
        _make_features(bpm=128.0, key_code=8, energy_lufs=-14.0),
        _make_features(bpm=140.0, key_code=12, energy_lufs=-18.0),
        _make_features(bpm=160.0, key_code=16, energy_lufs=-22.0),
        _make_features(bpm=100.0, key_code=20, energy_lufs=-8.0),
    ]
    no_hard = HardConstraints(
        max_bpm_diff=None,
        max_camelot_distance=None,
        max_energy_delta_lufs=None,
    )
    scorer = TransitionScoringService(hard_constraints=no_hard)

    matrix_050 = _build_matrix_two_tier(scorer, features, tier1_threshold=0.50)
    matrix_000 = _build_matrix_two_tier(scorer, features, tier1_threshold=0.0)

    # Count entries that differ (= pairs that skipped tier 2)
    n = len(features)
    total_off_diag = n * (n - 1)
    diff_count = 0
    for i in range(n):
        for j in range(n):
            if i != j and abs(matrix_050[i, j] - matrix_000[i, j]) > 1e-6:
                diff_count += 1

    skip_fraction = diff_count / total_off_diag
    assert skip_fraction >= 0.10, f"Only {skip_fraction:.1%} pairs skipped tier 2"
