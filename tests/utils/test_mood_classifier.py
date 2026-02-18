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
