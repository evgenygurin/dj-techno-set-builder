"""Tests for rule-based mood classifier with 15 techno subgenres.

Test values are calibrated against REAL data percentiles (N=1539 tracks):
  BPM 122-149, LUFS -17..-5, hp_ratio 0.66-17.25, centroid 782-5235 Hz,
  onset_rate 3.2-8.3, flux_mean 0.06-0.32, energy_mean 0.06-0.56.

Each prototypical test uses extreme values for the subgenre's key
discriminative features while keeping other features near the dataset median.
"""

import pytest

from app.utils.audio.mood_classifier import (
    MoodClassification,
    TrackMood,
    classify_track,
)

# Median values for "neutral" features (P50 from real data)
_MEDIAN = dict(
    bpm=128.0,
    lufs_i=-8.9,
    kick_prominence=0.84,
    spectral_centroid_mean=2616.0,
    onset_rate=5.34,
    hp_ratio=1.95,
    flux_mean=0.185,
    flux_std=0.124,
    energy_std=0.150,
    energy_mean=0.201,
    lra_lu=5.7,
    crest_factor_db=9.9,
    flatness_mean=0.049,
)


# -- Tests for each subgenre with prototypical features ----------------------


def test_ambient_dub_classification():
    """Ambient Dub: slow (122 BPM), very quiet, dark, spacious."""
    result = classify_track(
        bpm=122.0,
        lufs_i=-14.0,
        kick_prominence=0.50,
        spectral_centroid_mean=1400.0,
        onset_rate=3.5,
        hp_ratio=1.6,
        lra_lu=10.0,
        energy_mean=0.10,
    )
    assert result.mood == TrackMood.AMBIENT_DUB
    assert result.confidence > 0.05


def test_dub_techno_classification():
    """Dub Techno: slow, very high LRA from reverb/delay tails."""
    result = classify_track(
        bpm=124.0,
        lufs_i=-11.0,
        kick_prominence=0.65,
        spectral_centroid_mean=1900.0,
        onset_rate=4.0,
        hp_ratio=2.0,
        lra_lu=13.0,
    )
    assert result.mood == TrackMood.DUB_TECHNO
    assert result.confidence > 0.05


def test_minimal_classification():
    """Minimal: sparse, stable, low flux, low onset rate."""
    result = classify_track(
        bpm=126.0,
        lufs_i=-9.5,
        kick_prominence=0.65,
        spectral_centroid_mean=2300.0,
        onset_rate=4.0,
        hp_ratio=1.7,
        energy_std=0.10,
        flux_mean=0.13,
    )
    assert result.mood == TrackMood.MINIMAL
    assert result.confidence > 0.05


def test_detroit_classification():
    """Detroit: high hp_ratio (>2.5), warm centroid, moderate BPM."""
    result = classify_track(
        bpm=128.0,
        lufs_i=-8.5,
        kick_prominence=0.75,
        spectral_centroid_mean=2500.0,
        onset_rate=5.3,
        hp_ratio=3.2,
        energy_mean=0.25,
    )
    assert result.mood == TrackMood.DETROIT
    assert result.confidence > 0.05


def test_melodic_deep_classification():
    """Melodic Deep: harmonic but darker (low centroid), slower."""
    result = classify_track(
        bpm=125.0,
        lufs_i=-10.5,
        kick_prominence=0.60,
        spectral_centroid_mean=1700.0,
        onset_rate=4.8,
        hp_ratio=2.5,
        energy_mean=0.15,
    )
    assert result.mood == TrackMood.MELODIC_DEEP
    assert result.confidence > 0.05


def test_progressive_classification():
    """Progressive: high energy_std and flux_mean (dynamic, evolving)."""
    result = classify_track(
        bpm=128.0,
        lufs_i=-8.5,
        kick_prominence=0.80,
        spectral_centroid_mean=2600.0,
        onset_rate=5.5,
        hp_ratio=2.0,
        energy_std=0.21,
        flux_mean=0.27,
        lra_lu=9.0,
    )
    assert result.mood == TrackMood.PROGRESSIVE
    assert result.confidence > 0.05


def test_hypnotic_classification():
    """Hypnotic: very low flux_std and energy_std (stable, trance-like)."""
    result = classify_track(
        bpm=128.0,
        lufs_i=-8.5,
        kick_prominence=0.90,
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=1.8,
        flux_std=0.08,
        energy_std=0.09,
        flux_mean=0.13,
    )
    assert result.mood == TrackMood.HYPNOTIC
    assert result.confidence > 0.01


def test_driving_classification():
    """Driving: standard 4/4, ~129 BPM, solid kick, moderate everything."""
    result = classify_track(
        bpm=129.0,
        lufs_i=-8.5,
        kick_prominence=0.92,
        spectral_centroid_mean=2600.0,
        onset_rate=5.5,
        hp_ratio=1.9,
        energy_mean=0.22,
    )
    assert result.mood == TrackMood.DRIVING
    assert result.confidence > 0.01


def test_tribal_classification():
    """Tribal: very high onset rate (>6.5), percussive, moderate kick."""
    result = classify_track(
        bpm=130.0,
        lufs_i=-8.0,
        kick_prominence=0.70,
        spectral_centroid_mean=2700.0,
        onset_rate=7.5,
        hp_ratio=1.4,
    )
    assert result.mood == TrackMood.TRIBAL
    assert result.confidence > 0.01


def test_breakbeat_classification():
    """Breakbeat: very low kick (<0.3), moderate onset, broken beats."""
    result = classify_track(
        bpm=133.0,
        lufs_i=-8.0,
        kick_prominence=0.20,
        spectral_centroid_mean=2700.0,
        onset_rate=6.0,
        hp_ratio=1.5,
        energy_mean=0.25,
    )
    assert result.mood == TrackMood.BREAKBEAT
    assert result.confidence > 0.01


def test_peak_time_classification():
    """Peak Time: loud, dominant kick, high energy, high onset."""
    result = classify_track(
        bpm=132.0,
        lufs_i=-6.8,
        kick_prominence=0.95,
        spectral_centroid_mean=2800.0,
        onset_rate=6.5,
        hp_ratio=1.7,
        energy_mean=0.38,
    )
    assert result.mood == TrackMood.PEAK_TIME
    assert result.confidence > 0.05


def test_acid_classification():
    """Acid: high flux (303 filter sweeps), bright centroid, fast."""
    result = classify_track(
        bpm=136.0,
        lufs_i=-8.0,
        kick_prominence=0.80,
        spectral_centroid_mean=3600.0,
        onset_rate=5.5,
        hp_ratio=1.5,
        flux_mean=0.29,
        flux_std=0.18,
    )
    assert result.mood == TrackMood.ACID
    assert result.confidence > 0.05


def test_raw_classification():
    """Raw: very loud, heavily compressed (low crest), dominant kick."""
    result = classify_track(
        bpm=136.0,
        lufs_i=-5.5,
        kick_prominence=0.95,
        spectral_centroid_mean=2800.0,
        onset_rate=5.5,
        hp_ratio=1.5,
        crest_factor_db=7.0,
        energy_mean=0.40,
    )
    assert result.mood == TrackMood.RAW
    assert result.confidence > 0.01


def test_industrial_classification():
    """Industrial: very high centroid (>4000), high flatness (noisy), fast."""
    result = classify_track(
        bpm=138.0,
        lufs_i=-7.0,
        kick_prominence=0.80,
        spectral_centroid_mean=4800.0,
        onset_rate=7.0,
        hp_ratio=1.3,
        flatness_mean=0.14,
        flux_mean=0.15,  # low flux to suppress Acid
        flux_std=0.09,
    )
    assert result.mood == TrackMood.INDUSTRIAL
    assert result.confidence > 0.01


def test_hard_techno_classification():
    """Hard Techno: very fast (>145 BPM), loud, dominant kick."""
    result = classify_track(
        bpm=146.0,
        lufs_i=-5.5,
        kick_prominence=0.95,
        spectral_centroid_mean=3200.0,
        onset_rate=6.5,
        hp_ratio=1.3,
        energy_mean=0.40,
    )
    assert result.mood == TrackMood.HARD_TECHNO
    assert result.confidence > 0.01


# -- Edge cases and boundary tests -------------------------------------------


def test_borderline_minimal_vs_hypnotic():
    """Both sparse and stable — minimal has lower onset, hypnotic lower flux."""
    result = classify_track(
        bpm=127.0,
        lufs_i=-9.0,
        kick_prominence=0.75,
        spectral_centroid_mean=2400.0,
        onset_rate=4.5,
        hp_ratio=1.8,
        flux_std=0.10,
        energy_std=0.12,
        flux_mean=0.15,
    )
    assert result.mood in [TrackMood.MINIMAL, TrackMood.HYPNOTIC]


def test_borderline_peak_time_vs_raw():
    """Both loud with strong kick — raw is more compressed."""
    result = classify_track(
        bpm=134.0,
        lufs_i=-6.5,
        kick_prominence=0.93,
        spectral_centroid_mean=2800.0,
        onset_rate=6.0,
        hp_ratio=1.5,
        energy_mean=0.35,
        crest_factor_db=8.5,
    )
    assert result.mood in [TrackMood.PEAK_TIME, TrackMood.RAW]


def test_borderline_detroit_vs_melodic_deep():
    """Both harmonic — Detroit brighter centroid, Melodic Deep darker."""
    result = classify_track(
        bpm=126.5,
        lufs_i=-9.5,
        kick_prominence=0.65,
        spectral_centroid_mean=2100.0,
        onset_rate=5.0,
        hp_ratio=2.4,
        energy_mean=0.18,
    )
    assert result.mood in [TrackMood.DETROIT, TrackMood.MELODIC_DEEP]


# -- Confidence scoring tests ------------------------------------------------


def test_high_confidence_for_clear_classification():
    """Hard Techno at 148 BPM should be very clear."""
    result = classify_track(
        bpm=148.0,
        lufs_i=-5.0,
        kick_prominence=0.98,
        spectral_centroid_mean=3200.0,
        onset_rate=6.5,
        hp_ratio=1.2,
        energy_mean=0.45,
    )
    assert result.mood == TrackMood.HARD_TECHNO
    assert result.confidence > 0.1


def test_lower_confidence_for_ambiguous_classification():
    """Median-range features should result in moderate confidence."""
    result = classify_track(**_MEDIAN)
    # Should still classify something but confidence shouldn't be extreme
    assert 0.0 <= result.confidence <= 0.8


# -- Backward compatibility and API tests ------------------------------------


def test_backward_compatibility_with_original_params():
    """Can call with just the original 6 parameters (defaults for rest)."""
    result = classify_track(
        bpm=145.0,
        lufs_i=-7.0,
        kick_prominence=0.80,
        spectral_centroid_mean=3000.0,
        onset_rate=6.0,
        hp_ratio=1.5,
    )
    assert isinstance(result, MoodClassification)
    assert result.mood in TrackMood
    assert 0.0 <= result.confidence <= 1.0


def test_classify_track_returns_frozen_dataclass():
    """Result is immutable."""
    result = classify_track(**_MEDIAN)
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
        hp_ratio=1.5,
    )
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.features_used) >= 3


# -- Intensity and ordering tests --------------------------------------------


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
    order = TrackMood.energy_order()
    intensities = [m.intensity for m in order]
    assert intensities == sorted(intensities)
    assert intensities == list(range(1, 16))


# -- Subgenre-specific discriminative feature tests --------------------------


def test_breakbeat_requires_low_kick_prominence():
    """Breakbeat is distinguished by LOW kick prominence (no 4/4)."""
    low_kick_result = classify_track(
        bpm=133.0,
        lufs_i=-8.0,
        kick_prominence=0.20,
        spectral_centroid_mean=2700.0,
        onset_rate=6.0,
        hp_ratio=1.5,
        energy_mean=0.25,
    )
    assert low_kick_result.mood == TrackMood.BREAKBEAT

    # Same but HIGH kick should NOT be breakbeat
    high_kick_result = classify_track(
        bpm=133.0,
        lufs_i=-8.0,
        kick_prominence=0.90,
        spectral_centroid_mean=2700.0,
        onset_rate=6.0,
        hp_ratio=1.5,
        energy_mean=0.25,
    )
    assert high_kick_result.mood != TrackMood.BREAKBEAT


def test_dub_techno_requires_high_lra():
    """Dub techno is distinguished by wide loudness range (reverb/delay)."""
    result = classify_track(
        bpm=124.0,
        lufs_i=-11.0,
        kick_prominence=0.65,
        spectral_centroid_mean=1900.0,
        onset_rate=4.0,
        hp_ratio=2.0,
        lra_lu=13.0,
    )
    assert result.mood == TrackMood.DUB_TECHNO


def test_acid_requires_high_flux():
    """Acid is distinguished by high spectral flux (changing timbre)."""
    result = classify_track(
        bpm=136.0,
        lufs_i=-8.0,
        kick_prominence=0.80,
        spectral_centroid_mean=3600.0,
        onset_rate=5.5,
        hp_ratio=1.5,
        flux_mean=0.29,
        flux_std=0.18,
    )
    assert result.mood == TrackMood.ACID


def test_raw_requires_low_crest_factor():
    """Raw is distinguished by heavy compression (low crest factor)."""
    result = classify_track(
        bpm=136.0,
        lufs_i=-5.5,
        kick_prominence=0.95,
        spectral_centroid_mean=2800.0,
        onset_rate=5.5,
        hp_ratio=1.5,
        crest_factor_db=7.0,
        energy_mean=0.40,
    )
    assert result.mood == TrackMood.RAW


def test_detroit_requires_high_hp_ratio():
    """Detroit is distinguished by high hp_ratio (harmonic content)."""
    # High hp_ratio -> Detroit
    harmonic_result = classify_track(
        bpm=128.0,
        lufs_i=-8.5,
        kick_prominence=0.75,
        spectral_centroid_mean=2500.0,
        onset_rate=5.3,
        hp_ratio=3.2,
        energy_mean=0.25,
    )
    assert harmonic_result.mood == TrackMood.DETROIT

    # Low hp_ratio with same features -> NOT Detroit
    percussive_result = classify_track(
        bpm=128.0,
        lufs_i=-8.5,
        kick_prominence=0.75,
        spectral_centroid_mean=2500.0,
        onset_rate=5.3,
        hp_ratio=1.3,
        energy_mean=0.25,
    )
    assert percussive_result.mood != TrackMood.DETROIT


def test_industrial_requires_high_centroid():
    """Industrial is distinguished by harsh, bright timbre."""
    result = classify_track(
        bpm=138.0,
        lufs_i=-7.0,
        kick_prominence=0.80,
        spectral_centroid_mean=4800.0,
        onset_rate=7.0,
        hp_ratio=1.3,
        flatness_mean=0.14,
        flux_mean=0.15,
        flux_std=0.09,
    )
    assert result.mood == TrackMood.INDUSTRIAL
