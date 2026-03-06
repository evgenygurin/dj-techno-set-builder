"""Tests for rule-based mood classifier."""

from app.utils.audio.mood_classifier import (
    MoodClassification,
    TrackMood,
    classify_track,
)


def test_hard_techno_high_bpm_high_kick():
    result = classify_track(
        bpm=142.0,
        lufs_i=-7.0,
        kick_prominence=0.8,
        spectral_centroid_mean=3000.0,
        onset_rate=6.0,
        hp_ratio=0.3,
    )
    assert result.mood == TrackMood.HARD_TECHNO


def test_industrial_high_centroid_high_onset():
    result = classify_track(
        bpm=132.0,
        lufs_i=-8.0,
        kick_prominence=0.4,
        spectral_centroid_mean=5000.0,
        onset_rate=10.0,
        hp_ratio=0.3,
    )
    assert result.mood == TrackMood.INDUSTRIAL


def test_ambient_dub_low_bpm_low_lufs():
    result = classify_track(
        bpm=122.0,
        lufs_i=-13.0,
        kick_prominence=0.3,
        spectral_centroid_mean=1500.0,
        onset_rate=3.0,
        hp_ratio=0.6,
    )
    assert result.mood == TrackMood.AMBIENT_DUB


def test_peak_time_high_kick_high_lufs():
    result = classify_track(
        bpm=130.0,
        lufs_i=-6.5,
        kick_prominence=0.7,
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.4,
    )
    assert result.mood == TrackMood.PEAK_TIME


def test_melodic_deep_high_hp_low_centroid():
    result = classify_track(
        bpm=128.0,
        lufs_i=-9.0,
        kick_prominence=0.3,
        spectral_centroid_mean=1800.0,
        onset_rate=4.0,
        hp_ratio=0.7,
    )
    assert result.mood == TrackMood.MELODIC_DEEP


def test_driving_default_category():
    result = classify_track(
        bpm=130.0,
        lufs_i=-9.0,
        kick_prominence=0.5,
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.5,
    )
    assert result.mood == TrackMood.DRIVING


def test_classification_has_confidence():
    result = classify_track(
        bpm=142.0,
        lufs_i=-7.0,
        kick_prominence=0.8,
        spectral_centroid_mean=3000.0,
        onset_rate=6.0,
        hp_ratio=0.3,
    )
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.features_used) > 0


def test_classify_track_returns_frozen_dataclass():
    result = classify_track(
        bpm=130.0,
        lufs_i=-9.0,
        kick_prominence=0.5,
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.5,
    )
    assert isinstance(result, MoodClassification)


def test_mood_energy_order():
    """TrackMood.energy_order() returns moods sorted by intensity."""
    order = TrackMood.energy_order()
    assert order == [
        TrackMood.AMBIENT_DUB,
        TrackMood.MELODIC_DEEP,
        TrackMood.DRIVING,
        TrackMood.PEAK_TIME,
        TrackMood.INDUSTRIAL,
        TrackMood.HARD_TECHNO,
    ]


def test_mood_intensity_value():
    assert TrackMood.AMBIENT_DUB.intensity == 1
    assert TrackMood.HARD_TECHNO.intensity == 6


def test_priority_hard_techno_over_industrial():
    """HARD_TECHNO (bpm>=140, kick>0.6) takes priority over INDUSTRIAL."""
    result = classify_track(
        bpm=145.0,
        lufs_i=-7.0,
        kick_prominence=0.8,
        spectral_centroid_mean=5000.0,
        onset_rate=10.0,
        hp_ratio=0.3,
    )
    assert result.mood == TrackMood.HARD_TECHNO


def test_priority_industrial_over_ambient():
    """INDUSTRIAL takes priority over AMBIENT_DUB."""
    result = classify_track(
        bpm=125.0,
        lufs_i=-13.0,
        kick_prominence=0.3,
        spectral_centroid_mean=5000.0,
        onset_rate=10.0,
        hp_ratio=0.3,
    )
    assert result.mood == TrackMood.INDUSTRIAL


# ====================================================================
# Adversarial/Anti-confusion Tests
# ====================================================================


def test_adversarial_raw_not_hard_techno():
    """Raw techno (135 BPM, moderate kick) should NOT become HARD_TECHNO.

    Raw techno: 135-138 BPM, kick 0.5-0.6, high energy but NOT hard_techno.
    HARD_TECHNO requires bpm>=140 AND kick>0.6.
    """
    result = classify_track(
        bpm=135.0,
        lufs_i=-7.5,
        kick_prominence=0.58,  # Below 0.6 threshold
        spectral_centroid_mean=2800.0,
        onset_rate=5.5,
        hp_ratio=0.35,
    )
    assert result.mood != TrackMood.HARD_TECHNO, (
        f"Raw techno (135 BPM, kick=0.58) misclassified as {result.mood}"
    )
    # Should be DRIVING (default) since it doesn't match other specific rules
    assert result.mood == TrackMood.DRIVING


def test_adversarial_melodic_deep_not_detroit():
    """Melodic/deep techno should NOT become DETROIT (if it existed).

    Melodic deep: 125-128 BPM, hp_ratio>0.6, warm centroid<2000.
    This is a test that melodic characteristics are preserved.
    """
    result = classify_track(
        bpm=126.0,
        lufs_i=-9.5,
        kick_prominence=0.4,
        spectral_centroid_mean=1700.0,  # Warm
        onset_rate=4.2,
        hp_ratio=0.72,  # High harmonic content
    )
    assert result.mood == TrackMood.MELODIC_DEEP, (
        f"Melodic deep track misclassified as {result.mood}"
    )


def test_adversarial_hypnotic_not_minimal():
    """Hypnotic techno (mid-tempo, repetitive) should NOT become MINIMAL.

    Hypnotic: ~128 BPM, moderate features, should default to DRIVING.
    """
    result = classify_track(
        bpm=128.0,
        lufs_i=-9.0,
        kick_prominence=0.52,
        spectral_centroid_mean=2300.0,
        onset_rate=4.8,
        hp_ratio=0.48,
    )
    assert result.mood == TrackMood.DRIVING, (
        f"Hypnotic techno misclassified as {result.mood}"
    )


def test_adversarial_dub_techno_not_ambient_dub():
    """Dub techno (128 BPM, moderate loudness) should NOT become AMBIENT_DUB.

    AMBIENT_DUB requires bpm<128 AND lufs_i<-11.
    Dub techno at 128 BPM with -10 LUFS should be DRIVING or MELODIC_DEEP.
    """
    result = classify_track(
        bpm=128.0,  # At boundary, NOT <128
        lufs_i=-10.0,  # NOT <-11
        kick_prominence=0.45,
        spectral_centroid_mean=1900.0,
        onset_rate=4.0,
        hp_ratio=0.58,
    )
    assert result.mood != TrackMood.AMBIENT_DUB, (
        f"Dub techno (128 BPM, -10 LUFS) misclassified as {result.mood}"
    )
    # Should be DRIVING since it doesn't match MELODIC_DEEP (hp_ratio not >0.6)
    assert result.mood == TrackMood.DRIVING


def test_adversarial_peak_time_not_raw():
    """PEAK_TIME (heavy kick, loud) should NOT become RAW.

    Peak time: 128-132 BPM, kick>0.6, lufs>-8 → PEAK_TIME.
    """
    result = classify_track(
        bpm=130.0,
        lufs_i=-6.8,  # Loud, triggers PEAK_TIME
        kick_prominence=0.75,  # Heavy kick
        spectral_centroid_mean=2600.0,
        onset_rate=5.2,
        hp_ratio=0.42,
    )
    assert result.mood == TrackMood.PEAK_TIME, (
        f"Peak-time track misclassified as {result.mood}"
    )


def test_adversarial_acid_not_raw():
    """Acid techno (303 bassline, 130-135 BPM) should NOT become RAW.

    Acid: moderate BPM, moderate kick, should be DRIVING or MELODIC_DEEP.
    """
    result = classify_track(
        bpm=133.0,
        lufs_i=-8.5,
        kick_prominence=0.55,  # Below PEAK_TIME and HARD_TECHNO thresholds
        spectral_centroid_mean=2400.0,
        onset_rate=5.0,
        hp_ratio=0.5,
    )
    assert result.mood != TrackMood.HARD_TECHNO, (
        f"Acid techno misclassified as {result.mood}"
    )
    assert result.mood == TrackMood.DRIVING


def test_adversarial_industrial_not_raw():
    """INDUSTRIAL (harsh, busy) should NOT become RAW/HARD_TECHNO unless it meets criteria.

    Industrial with moderate BPM (132) and kick (0.5) should stay INDUSTRIAL.
    """
    result = classify_track(
        bpm=132.0,  # Below 140
        lufs_i=-8.2,
        kick_prominence=0.5,  # Below 0.6
        spectral_centroid_mean=5200.0,  # Harsh, >4000
        onset_rate=9.5,  # Busy, >8
        hp_ratio=0.28,
    )
    assert result.mood == TrackMood.INDUSTRIAL, (
        f"Industrial track misclassified as {result.mood}"
    )


# ====================================================================
# Confidence Mechanics Tests
# ====================================================================


def test_confidence_low_when_borderline():
    """Confidence should be LOW when features are at decision boundaries.

    When best score ≈ second-best score → confidence < 0.5.
    """
    # HARD_TECHNO borderline: bpm=140 (exactly at threshold), kick=0.61 (barely above 0.6)
    result = classify_track(
        bpm=140.0,  # Exactly at threshold
        lufs_i=-8.0,
        kick_prominence=0.61,  # Barely above 0.6
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.4,
    )
    assert result.mood == TrackMood.HARD_TECHNO
    # Confidence formula: min(1.0, (140-140)/10*0.5 + 0.61*0.5) = min(1.0, 0.305) = 0.305
    assert result.confidence < 0.5, (
        f"Borderline HARD_TECHNO should have low confidence, got {result.confidence:.2f}"
    )


def test_confidence_high_when_strong_match():
    """Confidence should be HIGH when features strongly exceed thresholds.

    When best score >> second-best → confidence > 0.7.
    """
    # Strong HARD_TECHNO: bpm=148, kick=0.9
    result = classify_track(
        bpm=148.0,  # Well above 140
        lufs_i=-7.0,
        kick_prominence=0.9,  # Well above 0.6
        spectral_centroid_mean=3000.0,
        onset_rate=6.5,
        hp_ratio=0.3,
    )
    assert result.mood == TrackMood.HARD_TECHNO
    # Confidence: min(1.0, (148-140)/10*0.5 + 0.9*0.5) = min(1.0, 0.4 + 0.45) = 0.85
    assert result.confidence > 0.7, (
        f"Strong HARD_TECHNO should have high confidence, got {result.confidence:.2f}"
    )


def test_confidence_moderate_for_default_driving():
    """DRIVING (default fallback) should have moderate fixed confidence = 0.5."""
    result = classify_track(
        bpm=130.0,
        lufs_i=-9.0,
        kick_prominence=0.5,
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.5,
    )
    assert result.mood == TrackMood.DRIVING
    assert result.confidence == 0.5, (
        f"Default DRIVING should have confidence=0.5, got {result.confidence:.2f}"
    )


def test_confidence_not_artificially_high_for_weak_matches():
    """When all features are weak, confidence should NOT be artificially high.

    Confidence should reflect actual feature strength, not just category assignment.
    """
    # Weak AMBIENT_DUB: bpm=127.5 (barely <128), lufs=-11.5 (barely <-11)
    result = classify_track(
        bpm=127.5,  # Just under 128
        lufs_i=-11.5,  # Just under -11
        kick_prominence=0.4,
        spectral_centroid_mean=2000.0,
        onset_rate=4.0,
        hp_ratio=0.5,
    )
    assert result.mood == TrackMood.AMBIENT_DUB
    # Confidence: min(1.0, (128-127.5)/10*0.5 + (-11-(-11.5))/5*0.5) = min(1.0, 0.025 + 0.05) = 0.075
    assert result.confidence < 0.3, (
        f"Weak AMBIENT_DUB should have low confidence, got {result.confidence:.2f}"
    )


# ====================================================================
# Borderline Stability Tests
# ====================================================================


def test_borderline_stability_bpm_variation():
    """Same track with ±5% BPM variation should NOT flip classification.

    Test stability at decision boundaries.
    """
    # Base: MELODIC_DEEP (hp_ratio=0.7, centroid=1800)
    base_features = {
        "bpm": 128.0,
        "lufs_i": -9.0,
        "kick_prominence": 0.35,
        "spectral_centroid_mean": 1800.0,
        "onset_rate": 4.0,
        "hp_ratio": 0.7,
    }
    base_result = classify_track(**base_features)

    # +5% BPM variation (128 * 1.05 = 134.4)
    high_bpm = base_features.copy()
    high_bpm["bpm"] = 134.4
    high_bpm_result = classify_track(**high_bpm)

    # -5% BPM variation (128 * 0.95 = 121.6)
    low_bpm = base_features.copy()
    low_bpm["bpm"] = 121.6
    low_bpm_result = classify_track(**low_bpm)

    # All three should be MELODIC_DEEP (or at least stable)
    assert base_result.mood == TrackMood.MELODIC_DEEP
    assert high_bpm_result.mood == base_result.mood, (
        f"BPM +5% caused flip: {base_result.mood} → {high_bpm_result.mood}"
    )
    assert low_bpm_result.mood == base_result.mood, (
        f"BPM -5% caused flip: {base_result.mood} → {low_bpm_result.mood}"
    )


def test_borderline_stability_kick_prominence_variation():
    """±5% kick_prominence variation should NOT flip classification."""
    # Base: PEAK_TIME (kick=0.7, lufs=-7)
    base_features = {
        "bpm": 130.0,
        "lufs_i": -7.0,
        "kick_prominence": 0.7,
        "spectral_centroid_mean": 2500.0,
        "onset_rate": 5.0,
        "hp_ratio": 0.4,
    }
    base_result = classify_track(**base_features)

    # +5% kick (0.7 * 1.05 = 0.735)
    high_kick = base_features.copy()
    high_kick["kick_prominence"] = 0.735
    high_kick_result = classify_track(**high_kick)

    # -5% kick (0.7 * 0.95 = 0.665)
    low_kick = base_features.copy()
    low_kick["kick_prominence"] = 0.665
    low_kick_result = classify_track(**low_kick)

    assert base_result.mood == TrackMood.PEAK_TIME
    assert high_kick_result.mood == base_result.mood, (
        f"Kick +5% caused flip: {base_result.mood} → {high_kick_result.mood}"
    )
    assert low_kick_result.mood == base_result.mood, (
        f"Kick -5% caused flip: {base_result.mood} → {low_kick_result.mood}"
    )


def test_borderline_stability_spectral_centroid_variation():
    """±5% spectral_centroid variation should NOT flip classification."""
    # Base: INDUSTRIAL (centroid=5000, onset=9)
    base_features = {
        "bpm": 132.0,
        "lufs_i": -8.0,
        "kick_prominence": 0.4,
        "spectral_centroid_mean": 5000.0,
        "onset_rate": 9.0,
        "hp_ratio": 0.3,
    }
    base_result = classify_track(**base_features)

    # +5% centroid (5000 * 1.05 = 5250)
    high_centroid = base_features.copy()
    high_centroid["spectral_centroid_mean"] = 5250.0
    high_centroid_result = classify_track(**high_centroid)

    # -5% centroid (5000 * 0.95 = 4750)
    low_centroid = base_features.copy()
    low_centroid["spectral_centroid_mean"] = 4750.0
    low_centroid_result = classify_track(**low_centroid)

    assert base_result.mood == TrackMood.INDUSTRIAL
    assert high_centroid_result.mood == base_result.mood, (
        f"Centroid +5% caused flip: {base_result.mood} → {high_centroid_result.mood}"
    )
    assert low_centroid_result.mood == base_result.mood, (
        f"Centroid -5% caused flip: {base_result.mood} → {low_centroid_result.mood}"
    )
