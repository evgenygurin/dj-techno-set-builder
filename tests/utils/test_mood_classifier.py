"""Tests for rule-based mood classifier with 15 techno subgenres."""

import pytest

from app.utils.audio.mood_classifier import (
    MoodClassification,
    TrackMood,
    classify_track,
)

# ── Tests for each subgenre with prototypical features ─────────────


def test_ambient_dub_classification():
    """Ambient Dub: slow (122 BPM), quiet (-13 LUFS), deep bass, smooth."""
    result = classify_track(
        bpm=122.0,
        lufs_i=-13.0,
        kick_prominence=0.35,
        spectral_centroid_mean=1500.0,
        onset_rate=3.0,
        hp_ratio=0.45,
        sub_energy=0.40,
    )
    assert result.mood == TrackMood.AMBIENT_DUB
    assert result.confidence > 0.4


def test_dub_techno_classification():
    """Dub Techno: reverb-heavy (high LRA), deep bass, dark timbre."""
    result = classify_track(
        bpm=124.0,
        lufs_i=-11.0,
        kick_prominence=0.50,
        spectral_centroid_mean=1400.0,
        onset_rate=4.0,
        hp_ratio=0.50,
        sub_energy=0.45,
        lra_lu=10.0,
    )
    assert result.mood == TrackMood.DUB_TECHNO
    assert result.confidence > 0.4


def test_minimal_classification():
    """Minimal: sparse, stable timbre, tight grid, subtle."""
    result = classify_track(
        bpm=127.5,
        lufs_i=-9.5,
        kick_prominence=0.55,
        spectral_centroid_mean=1800.0,
        onset_rate=4.5,
        hp_ratio=0.50,
        pulse_clarity=0.80,
        flux_std=0.25,
        energy_std=0.12,
    )
    assert result.mood == TrackMood.MINIMAL
    assert result.confidence > 0.4


def test_detroit_classification():
    """Detroit: soulful, harmonic (high hp_ratio), warm, chords."""
    result = classify_track(
        bpm=125.0,
        lufs_i=-9.0,
        kick_prominence=0.50,
        spectral_centroid_mean=2200.0,
        onset_rate=5.0,
        hp_ratio=0.70,
        chroma_entropy=0.70,
    )
    assert result.mood == TrackMood.DETROIT
    assert result.confidence > 0.4


def test_melodic_deep_classification():
    """Melodic Deep: harmonic, warm, balanced."""
    result = classify_track(
        bpm=126.0,
        lufs_i=-9.5,
        kick_prominence=0.50,
        spectral_centroid_mean=1800.0,
        onset_rate=5.0,
        hp_ratio=0.70,
    )
    assert result.mood == TrackMood.MELODIC_DEEP
    assert result.confidence > 0.4


def test_progressive_classification():
    """Progressive: building energy, evolving, dynamic."""
    result = classify_track(
        bpm=127.5,
        lufs_i=-9.0,
        kick_prominence=0.55,
        spectral_centroid_mean=2500.0,
        onset_rate=6.0,
        hp_ratio=0.55,
        energy_slope_mean=0.10,
        flux_mean=0.60,
        energy_std=0.25,
    )
    assert result.mood == TrackMood.PROGRESSIVE
    assert result.confidence > 0.4


def test_hypnotic_classification():
    """Hypnotic: repetitive, stable, tight grid, trance-inducing."""
    result = classify_track(
        bpm=134.0,
        lufs_i=-8.5,
        kick_prominence=0.65,
        spectral_centroid_mean=2300.0,
        onset_rate=5.5,
        hp_ratio=0.50,
        flux_std=0.20,
        pulse_clarity=0.85,
        energy_std=0.12,
    )
    assert result.mood == TrackMood.HYPNOTIC
    assert result.confidence > 0.4


def test_driving_classification():
    """Driving: standard 4/4, moderate energy, balanced."""
    result = classify_track(
        bpm=129.0,
        lufs_i=-9.0,
        kick_prominence=0.58,
        spectral_centroid_mean=2500.0,
        onset_rate=5.5,
        hp_ratio=0.50,
        energy_std=0.15,
    )
    assert result.mood == TrackMood.DRIVING
    assert result.confidence > 0.3


def test_tribal_classification():
    """Tribal: heavy percussion, lots of transients, busy."""
    result = classify_track(
        bpm=130.0,
        lufs_i=-8.5,
        kick_prominence=0.55,
        spectral_centroid_mean=2400.0,
        onset_rate=10.0,
        hp_ratio=0.45,
        contrast_mean_db=16.0,
    )
    assert result.mood == TrackMood.TRIBAL
    assert result.confidence > 0.4


def test_breakbeat_classification():
    """Breakbeat: LOW kick prominence (no 4/4), busy, disrupted grid."""
    result = classify_track(
        bpm=132.0,
        lufs_i=-8.0,
        kick_prominence=0.35,  # Key: low kick (no 4-on-floor)
        spectral_centroid_mean=2800.0,
        onset_rate=11.0,
        hp_ratio=0.45,
        pulse_clarity=0.50,
        contrast_mean_db=17.0,
    )
    assert result.mood == TrackMood.BREAKBEAT
    assert result.confidence > 0.4


def test_peak_time_classification():
    """Peak Time: heavy kick, loud, high energy, dancefloor."""
    result = classify_track(
        bpm=131.0,
        lufs_i=-6.5,
        kick_prominence=0.75,
        spectral_centroid_mean=2600.0,
        onset_rate=6.0,
        hp_ratio=0.45,
        energy_mean=0.75,
    )
    assert result.mood == TrackMood.PEAK_TIME
    assert result.confidence > 0.5


def test_acid_classification():
    """Acid: TB-303 squelchy, high flux (changing timbre), bright."""
    result = classify_track(
        bpm=140.0,
        lufs_i=-7.5,
        kick_prominence=0.60,
        spectral_centroid_mean=2800.0,
        onset_rate=6.5,
        hp_ratio=0.50,
        flux_mean=0.70,
        flux_std=0.50,
        chroma_entropy=0.75,
    )
    assert result.mood == TrackMood.ACID
    assert result.confidence > 0.4


def test_raw_classification():
    """Raw: aggressive, compressed (low crest), loud, dominant kick."""
    result = classify_track(
        bpm=136.0,
        lufs_i=-6.0,
        kick_prominence=0.80,
        spectral_centroid_mean=2700.0,
        onset_rate=6.0,
        hp_ratio=0.40,
        crest_factor_db=10.0,
        energy_mean=0.80,
    )
    assert result.mood == TrackMood.RAW
    assert result.confidence > 0.5


def test_industrial_classification():
    """Industrial: harsh (high centroid), noisy (high flatness), busy."""
    result = classify_track(
        bpm=135.0,
        lufs_i=-7.0,
        kick_prominence=0.55,
        spectral_centroid_mean=5000.0,
        onset_rate=10.0,
        hp_ratio=0.35,
        flatness_mean=0.50,
    )
    assert result.mood == TrackMood.INDUSTRIAL
    assert result.confidence > 0.5


def test_hard_techno_classification():
    """Hard Techno: fast (145+ BPM), very dominant kick, very loud."""
    result = classify_track(
        bpm=145.0,
        lufs_i=-6.0,
        kick_prominence=0.85,
        spectral_centroid_mean=3000.0,
        onset_rate=6.5,
        hp_ratio=0.35,
        energy_mean=0.85,
    )
    assert result.mood == TrackMood.HARD_TECHNO
    assert result.confidence > 0.5


# ── Edge cases and boundary tests ──────────────────────────────────


def test_borderline_minimal_vs_hypnotic():
    """Borderline between minimal (127 BPM) and hypnotic (134 BPM)."""
    result = classify_track(
        bpm=130.5,  # Between minimal and hypnotic
        lufs_i=-9.0,
        kick_prominence=0.60,
        spectral_centroid_mean=2000.0,
        onset_rate=5.0,
        hp_ratio=0.50,
        pulse_clarity=0.80,
        flux_std=0.25,
        energy_std=0.12,
    )
    # Should classify as one or the other with moderate confidence
    assert result.mood in [TrackMood.MINIMAL, TrackMood.HYPNOTIC, TrackMood.DRIVING]
    assert 0.2 <= result.confidence <= 0.8


def test_borderline_peak_time_vs_raw():
    """Both have high kick and loudness, but raw is more compressed."""
    result = classify_track(
        bpm=132.0,
        lufs_i=-6.5,
        kick_prominence=0.75,
        spectral_centroid_mean=2600.0,
        onset_rate=6.0,
        hp_ratio=0.45,
        energy_mean=0.75,
        crest_factor_db=11.0,  # Moderate compression
    )
    assert result.mood in [TrackMood.PEAK_TIME, TrackMood.RAW]
    assert result.confidence > 0.3


def test_borderline_detroit_vs_melodic_deep():
    """Both harmonic, warm - detroit has more melodic richness."""
    result = classify_track(
        bpm=126.0,
        lufs_i=-9.5,
        kick_prominence=0.50,
        spectral_centroid_mean=2000.0,
        onset_rate=5.0,
        hp_ratio=0.68,  # High but not extreme
        chroma_entropy=0.65,
    )
    assert result.mood in [TrackMood.DETROIT, TrackMood.MELODIC_DEEP]
    assert result.confidence > 0.3


# ── Confidence scoring tests ───────────────────────────────────────


def test_high_confidence_for_clear_classification():
    """Prototypical hard techno should have high confidence."""
    result = classify_track(
        bpm=150.0,  # Very fast
        lufs_i=-5.5,  # Very loud
        kick_prominence=0.90,  # Extremely dominant kick
        spectral_centroid_mean=3000.0,
        onset_rate=7.0,
        hp_ratio=0.30,
        energy_mean=0.90,
    )
    assert result.mood == TrackMood.HARD_TECHNO
    assert result.confidence > 0.7  # High confidence


def test_lower_confidence_for_ambiguous_classification():
    """Generic features should result in lower confidence."""
    result = classify_track(
        bpm=128.0,  # Middle BPM
        lufs_i=-9.0,  # Middle loudness
        kick_prominence=0.55,  # Middle kick
        spectral_centroid_mean=2500.0,  # Middle centroid
        onset_rate=5.5,
        hp_ratio=0.50,  # Middle hp_ratio
    )
    # Likely DRIVING but confidence shouldn't be too high
    assert 0.2 <= result.confidence <= 0.7


# ── Backward compatibility and API tests ───────────────────────────


def test_backward_compatibility_with_original_params():
    """Can call with just the original 6 parameters (defaults for rest)."""
    result = classify_track(
        bpm=145.0,
        lufs_i=-7.0,
        kick_prominence=0.80,
        spectral_centroid_mean=3000.0,
        onset_rate=6.0,
        hp_ratio=0.35,
    )
    assert isinstance(result, MoodClassification)
    assert result.mood in TrackMood
    assert 0.0 <= result.confidence <= 1.0


def test_classify_track_returns_frozen_dataclass():
    """Result is immutable."""
    result = classify_track(
        bpm=130.0,
        lufs_i=-9.0,
        kick_prominence=0.55,
        spectral_centroid_mean=2500.0,
        onset_rate=5.5,
        hp_ratio=0.50,
    )
    assert isinstance(result, MoodClassification)
    with pytest.raises(AttributeError):
        result.confidence = 0.9  # type: ignore[misc]


def test_classification_has_confidence_and_features():
    """All classifications must have confidence and features_used."""
    result = classify_track(
        bpm=142.0,
        lufs_i=-7.0,
        kick_prominence=0.80,
        spectral_centroid_mean=3000.0,
        onset_rate=6.0,
        hp_ratio=0.35,
    )
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.features_used) >= 3  # At least 3 key features


# ── Intensity and ordering tests ───────────────────────────────────


def test_mood_energy_order():
    """TrackMood.energy_order() returns all 15 moods sorted by intensity."""
    order = TrackMood.energy_order()
    assert len(order) == 15
    assert order == [
        TrackMood.AMBIENT_DUB,
        TrackMood.DUB_TECHNO,
        TrackMood.MINIMAL,
        TrackMood.DETROIT,
        TrackMood.MELODIC_DEEP,
        TrackMood.PROGRESSIVE,
        TrackMood.HYPNOTIC,
        TrackMood.DRIVING,
        TrackMood.TRIBAL,
        TrackMood.BREAKBEAT,
        TrackMood.PEAK_TIME,
        TrackMood.ACID,
        TrackMood.RAW,
        TrackMood.INDUSTRIAL,
        TrackMood.HARD_TECHNO,
    ]


def test_mood_intensity_values():
    """Intensity values are correctly mapped 1-15."""
    assert TrackMood.AMBIENT_DUB.intensity == 1
    assert TrackMood.DUB_TECHNO.intensity == 2
    assert TrackMood.MINIMAL.intensity == 3
    assert TrackMood.DETROIT.intensity == 4
    assert TrackMood.MELODIC_DEEP.intensity == 5
    assert TrackMood.PROGRESSIVE.intensity == 6
    assert TrackMood.HYPNOTIC.intensity == 7
    assert TrackMood.DRIVING.intensity == 8
    assert TrackMood.TRIBAL.intensity == 9
    assert TrackMood.BREAKBEAT.intensity == 10
    assert TrackMood.PEAK_TIME.intensity == 11
    assert TrackMood.ACID.intensity == 12
    assert TrackMood.RAW.intensity == 13
    assert TrackMood.INDUSTRIAL.intensity == 14
    assert TrackMood.HARD_TECHNO.intensity == 15


def test_intensity_is_monotonic():
    """Intensity values are strictly increasing in energy_order."""
    # Verify the energy_order is strictly increasing
    order = TrackMood.energy_order()
    intensities = [m.intensity for m in order]
    assert intensities == sorted(intensities)
    assert intensities == list(range(1, 16))


# ── Subgenre-specific discriminative feature tests ─────────────────


def test_breakbeat_requires_low_kick_prominence():
    """Breakbeat is distinguished by LOW kick prominence (no 4/4)."""
    # High onset but LOW kick should be breakbeat
    low_kick_result = classify_track(
        bpm=132.0,
        lufs_i=-8.0,
        kick_prominence=0.30,  # LOW
        spectral_centroid_mean=2800.0,
        onset_rate=12.0,
        hp_ratio=0.45,
        pulse_clarity=0.50,
        contrast_mean_db=18.0,
    )
    assert low_kick_result.mood == TrackMood.BREAKBEAT

    # Same features but HIGH kick should NOT be breakbeat
    high_kick_result = classify_track(
        bpm=132.0,
        lufs_i=-8.0,
        kick_prominence=0.75,  # HIGH
        spectral_centroid_mean=2800.0,
        onset_rate=12.0,
        hp_ratio=0.45,
        pulse_clarity=0.70,
        contrast_mean_db=18.0,
    )
    assert high_kick_result.mood != TrackMood.BREAKBEAT


def test_dub_techno_requires_high_lra():
    """Dub techno is distinguished by wide loudness range (reverb/delay)."""
    result_high_lra = classify_track(
        bpm=124.0,
        lufs_i=-11.0,
        kick_prominence=0.50,
        spectral_centroid_mean=1400.0,
        onset_rate=4.0,
        hp_ratio=0.50,
        sub_energy=0.45,
        lra_lu=11.0,  # High LRA
    )
    assert result_high_lra.mood == TrackMood.DUB_TECHNO


def test_acid_requires_high_flux():
    """Acid is distinguished by high spectral flux (changing timbre)."""
    result = classify_track(
        bpm=140.0,
        lufs_i=-7.5,
        kick_prominence=0.60,
        spectral_centroid_mean=2800.0,
        onset_rate=6.5,
        hp_ratio=0.50,
        flux_mean=0.75,  # High flux
        flux_std=0.55,  # High variance
        chroma_entropy=0.75,
    )
    assert result.mood == TrackMood.ACID


def test_raw_requires_low_crest_factor():
    """Raw is distinguished by heavy compression (low crest factor)."""
    result = classify_track(
        bpm=136.0,
        lufs_i=-6.0,
        kick_prominence=0.80,
        spectral_centroid_mean=2700.0,
        onset_rate=6.0,
        hp_ratio=0.40,
        crest_factor_db=9.0,  # Low crest = compressed
        energy_mean=0.80,
    )
    assert result.mood == TrackMood.RAW


def test_progressive_requires_positive_energy_slope():
    """Progressive is distinguished by building energy over time."""
    result = classify_track(
        bpm=127.5,
        lufs_i=-9.0,
        kick_prominence=0.55,
        spectral_centroid_mean=2500.0,
        onset_rate=6.0,
        hp_ratio=0.55,
        energy_slope_mean=0.12,  # Positive slope (building)
        flux_mean=0.60,
        energy_std=0.25,
    )
    assert result.mood == TrackMood.PROGRESSIVE
