import pytest

from app.services.audio.scoring import TrackFeatures, TransitionScoringService


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
    """Same key with high density + HNR should score ~1.0"""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 0): 1.0}
    # Full density + high HNR → factor approaches 1.0
    score = service.score_harmonic(
        cam_a=0,
        cam_b=0,
        density_a=1.0,
        density_b=1.0,
        hnr_a=20.0,
        hnr_b=20.0,
    )
    assert score == pytest.approx(1.0, abs=0.01)


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
    # onset_score = 1 - 2/6 = 0.667, kick_score = 1.0 (default 0.5 vs 0.5)
    # total = 0.7*0.667 + 0.3*1.0 ≈ 0.767
    score = service.score_groove(onset_a=4.0, onset_b=6.0)
    assert 0.72 < score < 0.82


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
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
        mfcc_vector=mfcc,
    )
    features_b = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
        mfcc_vector=mfcc,
    )
    score = service.score_spectral(features_a, features_b)
    assert score > 0.95  # Identical everything


def test_score_spectral_mfcc_different():
    """Different MFCC vectors should lower spectral score."""
    service = TransitionScoringService()
    features_a = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
        mfcc_vector=[10.0] * 13,
    )
    features_b = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
        mfcc_vector=[-10.0] * 13,
    )
    score = service.score_spectral(features_a, features_b)
    # Opposite MFCC → mfcc_score=0, but centroid+balance identical → 0.6
    assert score == pytest.approx(0.6, abs=0.05)


def test_score_spectral_fallback_without_mfcc():
    """Without MFCC, should use Phase 1 formula (50/50 centroid+balance)."""
    service = TransitionScoringService()
    features_a = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
        mfcc_vector=None,
    )
    features_b = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
        mfcc_vector=None,
    )
    score = service.score_spectral(features_a, features_b)
    assert score > 0.9  # Identical centroid + balance


# ── Phase 2: score_harmonic with HNR ──


def test_score_harmonic_hnr_modulation():
    """High HNR (more harmonic content) should increase Camelot weight."""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 6): 0.5}  # Mid-distance key pair

    # High HNR = melodic = Camelot matters more
    score_high_hnr = service.score_harmonic(
        cam_a=0,
        cam_b=6,
        density_a=0.5,
        density_b=0.5,
        hnr_a=20.0,
        hnr_b=20.0,
    )

    # Low HNR = noisy/percussive = Camelot matters less
    score_low_hnr = service.score_harmonic(
        cam_a=0,
        cam_b=6,
        density_a=0.5,
        density_b=0.5,
        hnr_a=2.0,
        hnr_b=2.0,
    )

    # With bad Camelot (0.5), high HNR should produce LOWER score
    # because it weights the bad Camelot more heavily
    assert score_low_hnr > score_high_hnr


def test_score_harmonic_backward_compatible():
    """Without hnr kwargs, should still produce high score for same key."""
    service = TransitionScoringService()
    service.camelot_lookup = {(0, 0): 1.0}

    # hnr defaults to 0.0 → combined=0.6*0.8=0.48 → factor=0.636 → ~0.93
    score = service.score_harmonic(cam_a=0, cam_b=0, density_a=0.8, density_b=0.8)
    assert score > 0.9


# ── Phase 2: score_groove with kick prominence ──


def test_score_groove_with_kick_prominence():
    """Kick prominence difference should lower groove score."""
    service = TransitionScoringService()

    # Same onset rate but very different kick prominence
    score = service.score_groove(
        onset_a=5.0,
        onset_b=5.0,
        kick_a=0.9,
        kick_b=0.1,
    )
    # onset_score=1.0, kick_score=1-0.8=0.2 → 0.7*1.0 + 0.3*0.2 = 0.76
    assert 0.70 < score < 0.82


def test_score_groove_kick_identical():
    """Identical kick prominence should maximize groove score."""
    service = TransitionScoringService()
    score = service.score_groove(onset_a=5.0, onset_b=5.0, kick_a=0.8, kick_b=0.8)
    assert score > 0.95


def test_score_groove_backward_compatible():
    """Without kick kwargs, should use default 0.5 → kick_score=1.0."""
    service = TransitionScoringService()
    score = service.score_groove(onset_a=5.0, onset_b=5.0)
    # kick default 0.5 vs 0.5 → kick_score = 1.0
    # onset_score = 1.0 → total = 0.7*1.0 + 0.3*1.0 = 1.0
    assert score == pytest.approx(1.0)


# ── Phase 3: TrackFeatures extension ──


def test_track_features_phase3_fields_have_defaults():
    """Phase 3 fields should be optional with defaults."""
    tf = TrackFeatures(
        bpm=128,
        energy_lufs=-14,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2000,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.0,
    )
    assert tf.hp_ratio == 0.5
    assert tf.last_section is None
    assert tf.first_section is None


# ── Phase 3: score_structure (section-aware scoring) ──


def test_score_structure_outro_to_intro():
    """outro→intro is the ideal transition: score should be 1.0."""
    service = TransitionScoringService()
    score = service.score_structure("outro", "intro")
    assert score == pytest.approx(1.0)


def test_score_structure_drop_to_drop():
    """drop→drop is suboptimal: should score < 0.7."""
    service = TransitionScoringService()
    score = service.score_structure("drop", "drop")
    assert score < 0.7


def test_score_structure_breakdown_to_buildup():
    """breakdown→buildup is a natural flow: should score > 0.7."""
    service = TransitionScoringService()
    score = service.score_structure("breakdown", "buildup")
    assert score > 0.7


def test_score_structure_none_returns_neutral():
    """When section data is missing, return 0.5 (neutral)."""
    service = TransitionScoringService()
    assert service.score_structure(None, "intro") == pytest.approx(0.5)
    assert service.score_structure("outro", None) == pytest.approx(0.5)
    assert service.score_structure(None, None) == pytest.approx(0.5)


def test_score_structure_unknown_section_gets_fallback():
    """Unknown section names should get fallback score, not crash."""
    service = TransitionScoringService()
    score = service.score_structure("unknown_section", "intro")
    assert 0.0 <= score <= 1.0


def test_score_transition_includes_structure_when_available():
    """Full transition score should use 6 components when sections are present."""
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
        last_section="outro",
    )
    features_b = TrackFeatures(
        bpm=130,
        energy_lufs=-13,
        key_code=0,
        harmonic_density=0.8,
        centroid_hz=2100,
        band_ratios=[0.3, 0.5, 0.2],
        onset_rate=5.2,
        first_section="intro",
    )

    score = service.score_transition(features_a, features_b)
    assert score > 0.8  # Near-identical tracks + perfect section pairing
    assert score <= 1.0


# ── Two-tier optimisation: quick_score ──


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


def test_quick_score_identical_tracks_high():
    """Identical features → quick_score > 0.8."""
    service = TransitionScoringService()
    a = _make_features()
    b = _make_features()
    score = service.quick_score(a, b)
    assert score > 0.8


def test_quick_score_very_different_pair_low():
    """Widely mismatched BPM + key + energy → quick_score < 0.4."""
    service = TransitionScoringService()
    a = _make_features(bpm=128.0, key_code=0, energy_lufs=-8.0)
    b = _make_features(bpm=170.0, key_code=12, energy_lufs=-18.0)
    score = service.quick_score(a, b)
    assert score < 0.4


def test_quick_score_never_returns_zero():
    """Even the worst possible pair must get score > 0.0 (floor 0.01)."""
    service = TransitionScoringService()
    # Maximally different: extreme BPM, different key, huge energy gap
    a = _make_features(bpm=70.0, key_code=0, energy_lufs=-6.0)
    b = _make_features(bpm=170.0, key_code=12, energy_lufs=-20.0)
    score = service.quick_score(a, b)
    assert score > 0.0
    assert score >= 0.01


def test_quick_score_correlates_with_full_score():
    """quick_score ordering should correlate with score_transition ordering.

    Generate several pairs with varying BPM/key/energy diffs.
    Rank by quick_score and by full score_transition.
    Spearman rank correlation should be > 0.6.
    """
    service = TransitionScoringService()

    base = _make_features()
    variants = [
        _make_features(bpm=129.0, key_code=1, energy_lufs=-14.5),  # very close
        _make_features(bpm=132.0, key_code=3, energy_lufs=-12.0),  # moderate
        _make_features(bpm=140.0, key_code=6, energy_lufs=-9.0),  # far
        _make_features(bpm=150.0, key_code=12, energy_lufs=-6.0),  # very far
        _make_features(bpm=128.0, key_code=0, energy_lufs=-14.0),  # identical
    ]

    quick_scores = [service.quick_score(base, v) for v in variants]
    full_scores = [service.score_transition(base, v) for v in variants]

    # Compute Spearman rank correlation
    def _rank(values: list[float]) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * len(values)
        for rank, (idx, _) in enumerate(indexed):
            ranks[idx] = float(rank)
        return ranks

    qr = _rank(quick_scores)
    fr = _rank(full_scores)
    n = len(qr)
    d_sq = sum((a - b) ** 2 for a, b in zip(qr, fr, strict=True))
    spearman = 1.0 - 6.0 * d_sq / (n * (n**2 - 1))

    assert spearman > 0.6, f"Spearman correlation too low: {spearman:.3f}"


def test_quick_score_double_time_compatible():
    """Double-time pairs (64 vs 128 BPM) should score well in quick_score."""
    service = TransitionScoringService()
    a = _make_features(bpm=64.0)
    b = _make_features(bpm=128.0)
    score = service.quick_score(a, b)
    assert score > 0.7
