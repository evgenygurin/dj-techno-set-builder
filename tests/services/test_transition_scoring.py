import pytest

from app.services.transition_scoring import TrackFeatures, TransitionScoringService


def test_track_features_new_fields_have_defaults():
    """Phase 2 fields should be optional with defaults."""
    tf = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
    )
    assert tf.mfcc_vector is None
    assert tf.kick_prominence == 0.5
    assert tf.hnr_db == 0.0
    assert tf.spectral_slope == 0.0


def test_score_bpm_identical():
    """Identical BPM should score 1.0"""
    service = TransitionScoringService()
    score = service.score_bpm(128.0, 128.0)
    assert score == pytest.approx(1.0)


def test_score_bpm_gaussian_decay():
    """BPM score should decay with Gaussian (sigma=8)"""
    service = TransitionScoringService()
    # At 8 BPM diff, score ≈ exp(-0.5) ≈ 0.606
    score = service.score_bpm(128.0, 136.0)
    assert 0.55 < score < 0.65

    # At 16 BPM diff, score ≈ exp(-2) ≈ 0.135
    score = service.score_bpm(128.0, 144.0)
    assert 0.10 < score < 0.20


def test_score_bpm_double_time():
    """Should handle double-time (2x BPM) as compatible"""
    service = TransitionScoringService()
    # 65 vs 130 BPM (2x) should score high
    score = service.score_bpm(65.0, 130.0)
    assert score > 0.8


def test_score_harmonic_same_key():
    """Same key without density modulation should score 1.0"""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 0): 1.0}
    score = service.score_harmonic(cam_a=0, cam_b=0, density_a=1.0, density_b=1.0)
    assert score == pytest.approx(1.0)


def test_score_harmonic_density_modulation():
    """Low harmonic density should reduce Camelot weight"""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 1): 0.9}  # Adjacent Camelot

    # High density: full Camelot weight
    score_high = service.score_harmonic(cam_a=0, cam_b=1, density_a=0.9, density_b=0.9)

    # Low density: reduced Camelot weight, closer to 0.8
    score_low = service.score_harmonic(cam_a=0, cam_b=1, density_a=0.1, density_b=0.1)

    assert score_high > score_low
    assert score_low > 0.75  # Should still be reasonable


def test_score_energy_lufs_identical():
    """Identical LUFS should score 1.0"""
    service = TransitionScoringService()
    score = service.score_energy(lufs_a=-14.0, lufs_b=-14.0)
    assert score == pytest.approx(1.0)


def test_score_energy_sigmoid_decay():
    """Energy score decays sigmoidally with LUFS difference"""
    service = TransitionScoringService()
    # 4 LUFS diff → score = 1 / (1 + 1) = 0.5
    score = service.score_energy(lufs_a=-14.0, lufs_b=-10.0)
    assert score == pytest.approx(0.5, abs=0.05)


def test_score_spectral_centroid_component():
    """Spectral score includes centroid similarity"""
    service = TransitionScoringService()

    # Identical centroids
    features_a = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
    )
    features_b = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
    )

    service.camelot_lookup = {(0, 0): 1.0}
    score = service.score_spectral(features_a, features_b)
    assert score > 0.9


def test_score_spectral_band_balance():
    """Different band balances should lower spectral score"""
    service = TransitionScoringService()

    features_a = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.6, 0.3, 0.1],
        onset_rate=5.0,  # Bass-heavy
    )
    features_b = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.1, 0.3, 0.6],
        onset_rate=5.0,  # Treble-heavy
    )

    score = service.score_spectral(features_a, features_b)
    # Should be penalized (centroid identical = 0.5, band mismatch adds penalty)
    assert score < 0.75


def test_score_groove_identical():
    """Identical onset rates should score 1.0"""
    service = TransitionScoringService()
    score = service.score_groove(onset_a=5.0, onset_b=5.0)
    assert score == pytest.approx(1.0)


def test_score_groove_relative_diff():
    """Groove score based on relative onset rate difference"""
    service = TransitionScoringService()
    # 50% difference: onset_a=4, onset_b=6 → score = 1 - 2/6 = 0.667
    score = service.score_groove(onset_a=4.0, onset_b=6.0)
    assert 0.6 < score < 0.7


def test_score_transition_weighted_composite():
    """Full transition score combines all 5 components"""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 0): 1.0}

    features_a = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.8,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
    )
    features_b = TrackFeatures(
        bpm=130,
        energy_lufs=-13,
        key_code=0,
        harmonic_density=0.8,
        centroid_hz=2100,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.2,
    )

    score = service.score_transition(features_a, features_b)

    # Should be high (near-identical tracks)
    assert score > 0.85
    assert score <= 1.0


# ── Phase 2: score_spectral with MFCC ──


def test_score_spectral_with_mfcc():
    """When MFCC vectors are present, they should contribute to spectral score."""
    service = TransitionScoringService()
    mfcc = [1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0, 9.0, -10.0, 11.0, -12.0, 13.0]
    features_a = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=mfcc,
    )
    features_b = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=mfcc,
    )
    score = service.score_spectral(features_a, features_b)
    assert score > 0.95  # Identical everything


def test_score_spectral_mfcc_different():
    """Different MFCC vectors should lower spectral score."""
    service = TransitionScoringService()
    features_a = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=[10.0] * 13,
    )
    features_b = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=[-10.0] * 13,
    )
    score = service.score_spectral(features_a, features_b)
    # Opposite MFCC → mfcc_score=0, but centroid+balance identical → 0.6
    assert score == pytest.approx(0.6, abs=0.05)


def test_score_spectral_fallback_without_mfcc():
    """Without MFCC, should use Phase 1 formula (50/50 centroid+balance)."""
    service = TransitionScoringService()
    features_a = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=None,
    )
    features_b = TrackFeatures(
        bpm=128, energy_lufs=-14, key_code=0, harmonic_density=0.5,
        centroid_hz=2000, band_ratios=[0.3, 0.5, 0.2], onset_rate=5.0,
        mfcc_vector=None,
    )
    score = service.score_spectral(features_a, features_b)
    assert score > 0.9  # Identical centroid + balance
