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
        flux_std=60.0,
        energy_std=0.2,
        crest_factor_db=14.0,
        lra_lu=8.0,
    )
    assert result.mood == TrackMood.HARD_TECHNO


def test_industrial_high_centroid_high_onset():
    result = classify_track(
        bpm=138.0,  # Higher BPM, outside driving range
        lufs_i=-7.5,
        kick_prominence=0.35,  # Not optimal for driving
        spectral_centroid_mean=5500.0,  # Very high centroid
        onset_rate=11.0,  # Very busy
        hp_ratio=0.25,
        flux_std=85.0,
        energy_std=0.27,
        crest_factor_db=17.0,
        lra_lu=11.0,
    )
    assert result.mood == TrackMood.INDUSTRIAL


def test_ambient_dub_low_bpm_low_lufs_sustained():
    result = classify_track(
        bpm=118.0,  # Very low BPM
        lufs_i=-14.0,  # Very quiet
        kick_prominence=0.25,
        spectral_centroid_mean=1400.0,
        onset_rate=2.5,  # Very sparse
        hp_ratio=0.65,
        flux_std=25.0,
        energy_std=0.08,
        crest_factor_db=9.0,  # Very low crest = sustained energy
        lra_lu=3.0,
    )
    assert result.mood == TrackMood.AMBIENT_DUB


def test_dub_techno_moderate_tempo_rhythmic():
    result = classify_track(
        bpm=124.0,
        lufs_i=-9.0,
        kick_prominence=0.45,
        spectral_centroid_mean=2000.0,
        onset_rate=5.5,
        hp_ratio=0.5,
        flux_std=45.0,
        energy_std=0.14,
        crest_factor_db=12.0,  # Moderate crest
        lra_lu=8.0,  # Controlled dynamics
    )
    assert result.mood == TrackMood.DUB_TECHNO


def test_peak_time_high_kick_high_lufs():
    result = classify_track(
        bpm=130.0,
        lufs_i=-6.5,
        kick_prominence=0.7,
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.4,
        flux_std=55.0,
        energy_std=0.18,
        crest_factor_db=15.0,
        lra_lu=9.0,
    )
    assert result.mood == TrackMood.PEAK_TIME


def test_melodic_deep_high_hp_low_centroid():
    result = classify_track(
        bpm=126.0,
        lufs_i=-9.5,
        kick_prominence=0.28,
        spectral_centroid_mean=1600.0,  # Very warm/low centroid
        onset_rate=3.5,  # Sparse (not in minimal's flux/energy range)
        hp_ratio=0.75,  # Very harmonic
        flux_std=55.0,  # Higher flux (not minimal)
        energy_std=0.18,  # Higher energy variance (not minimal)
        crest_factor_db=11.0,
        lra_lu=6.0,
    )
    assert result.mood == TrackMood.MELODIC_DEEP


def test_minimal_sparse_low_flux():
    result = classify_track(
        bpm=126.0,
        lufs_i=-10.0,
        kick_prominence=0.35,
        spectral_centroid_mean=1900.0,
        onset_rate=4.0,  # Sparse onsets
        hp_ratio=0.5,
        flux_std=35.0,  # Low flux variance
        energy_std=0.10,  # Low energy variance
        crest_factor_db=11.0,
        lra_lu=5.0,
    )
    assert result.mood == TrackMood.MINIMAL


def test_hypnotic_regular_repetitive():
    result = classify_track(
        bpm=136.5,  # Just outside driving range
        lufs_i=-10.0,  # Not in driving loudness range
        kick_prominence=0.42,  # Not optimal for driving
        spectral_centroid_mean=2100.0,  # Not in driving centroid range
        onset_rate=6.0,  # Regular onset pattern
        hp_ratio=0.4,
        flux_std=25.0,  # Very low flux = repetitive motifs
        energy_std=0.07,  # Very low energy variance = strict regularity
        crest_factor_db=13.0,
        lra_lu=7.0,
    )
    assert result.mood == TrackMood.HYPNOTIC


def test_driving_balanced_moderate_bpm():
    result = classify_track(
        bpm=130.0,
        lufs_i=-8.5,
        kick_prominence=0.5,  # Balanced kick
        spectral_centroid_mean=2500.0,  # Mid-range
        onset_rate=6.0,  # Moderate
        hp_ratio=0.5,
        flux_std=50.0,
        energy_std=0.16,
        crest_factor_db=13.0,
        lra_lu=8.0,
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
        flux_std=60.0,
        energy_std=0.2,
        crest_factor_db=14.0,
        lra_lu=8.0,
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
        flux_std=50.0,
        energy_std=0.15,
        crest_factor_db=13.0,
        lra_lu=8.0,
    )
    assert isinstance(result, MoodClassification)


def test_mood_energy_order():
    """TrackMood.energy_order() returns moods sorted by intensity."""
    order = TrackMood.energy_order()
    assert order == [
        TrackMood.AMBIENT_DUB,
        TrackMood.DUB_TECHNO,
        TrackMood.MELODIC_DEEP,
        TrackMood.MINIMAL,
        TrackMood.HYPNOTIC,
        TrackMood.DRIVING,
        TrackMood.PEAK_TIME,
        TrackMood.INDUSTRIAL,
        TrackMood.HARD_TECHNO,
    ]


def test_mood_intensity_value():
    assert TrackMood.AMBIENT_DUB.intensity == 1
    assert TrackMood.HARD_TECHNO.intensity == 9
    assert TrackMood.DUB_TECHNO.intensity == 2
    assert TrackMood.MINIMAL.intensity == 4
    assert TrackMood.HYPNOTIC.intensity == 5


def test_priority_hard_techno_over_industrial():
    """HARD_TECHNO (bpm>=140, kick>0.6) takes priority over INDUSTRIAL via scoring."""
    result = classify_track(
        bpm=145.0,
        lufs_i=-7.0,
        kick_prominence=0.8,
        spectral_centroid_mean=5000.0,
        onset_rate=10.0,
        hp_ratio=0.3,
        flux_std=80.0,
        energy_std=0.25,
        crest_factor_db=16.0,
        lra_lu=10.0,
    )
    assert result.mood == TrackMood.HARD_TECHNO


def test_priority_industrial_over_ambient():
    """INDUSTRIAL takes priority over AMBIENT_DUB via scoring."""
    result = classify_track(
        bpm=125.0,
        lufs_i=-13.0,
        kick_prominence=0.3,
        spectral_centroid_mean=5500.0,  # Very harsh
        onset_rate=11.0,  # Very busy
        hp_ratio=0.25,
        flux_std=85.0,
        energy_std=0.27,
        crest_factor_db=16.0,
        lra_lu=10.0,
    )
    assert result.mood == TrackMood.INDUSTRIAL


def test_minimal_vs_hypnotic_discrimination():
    """Minimal has sparse onsets, Hypnotic has regular onsets."""
    # Minimal: sparse + low flux
    minimal = classify_track(
        bpm=126.0,
        lufs_i=-10.0,
        kick_prominence=0.35,
        spectral_centroid_mean=1900.0,
        onset_rate=3.5,  # Sparse
        hp_ratio=0.5,
        flux_std=40.0,
        energy_std=0.12,
        crest_factor_db=11.0,
        lra_lu=5.0,
    )
    assert minimal.mood == TrackMood.MINIMAL

    # Hypnotic: regular + very low flux + higher BPM
    hypnotic = classify_track(
        bpm=136.5,  # Just outside driving range
        lufs_i=-10.0,  # Not in driving loudness range
        kick_prominence=0.42,  # Not optimal for driving
        spectral_centroid_mean=2100.0,  # Not in driving centroid range
        onset_rate=6.0,  # Regular, not sparse
        hp_ratio=0.4,
        flux_std=25.0,  # Very low = repetitive
        energy_std=0.07,  # Very low = strict regularity
        crest_factor_db=13.0,
        lra_lu=7.0,
    )
    assert hypnotic.mood == TrackMood.HYPNOTIC


def test_dub_techno_vs_ambient_dub_discrimination():
    """Dub techno has more rhythmic structure than ambient dub."""
    # Ambient dub: sustained energy, sparse onsets
    ambient = classify_track(
        bpm=118.0,  # Very low BPM
        lufs_i=-14.0,  # Very quiet
        kick_prominence=0.25,
        spectral_centroid_mean=1400.0,
        onset_rate=2.5,  # Very sparse
        hp_ratio=0.65,
        flux_std=25.0,
        energy_std=0.08,
        crest_factor_db=9.0,  # Very low = sustained
        lra_lu=3.0,
    )
    assert ambient.mood == TrackMood.AMBIENT_DUB

    # Dub techno: moderate rhythmic structure
    dub = classify_track(
        bpm=124.0,
        lufs_i=-9.5,
        kick_prominence=0.45,  # More prominent kick
        spectral_centroid_mean=2000.0,
        onset_rate=5.5,  # Moderate rhythmic activity
        hp_ratio=0.5,
        flux_std=45.0,
        energy_std=0.14,
        crest_factor_db=12.0,  # Moderate = some transients
        lra_lu=8.0,  # More dynamic
    )
    assert dub.mood == TrackMood.DUB_TECHNO


def test_confidence_low_margin():
    """Confidence is low when best and second-best scores are close."""
    # Track with ambiguous features (could be driving or peak_time)
    result = classify_track(
        bpm=130.0,
        lufs_i=-8.0,  # Borderline
        kick_prominence=0.6,  # Borderline
        spectral_centroid_mean=2500.0,
        onset_rate=5.5,
        hp_ratio=0.5,
        flux_std=50.0,
        energy_std=0.16,
        crest_factor_db=13.0,
        lra_lu=8.0,
    )
    # Should have lower confidence due to ambiguity
    assert result.confidence < 0.6


def test_confidence_high_margin():
    """Confidence is high when best score is much better than second-best."""
    # Unambiguous hard techno
    result = classify_track(
        bpm=150.0,  # Very high
        lufs_i=-7.0,
        kick_prominence=0.85,  # Very high
        spectral_centroid_mean=3000.0,
        onset_rate=6.0,
        hp_ratio=0.3,
        flux_std=60.0,
        energy_std=0.2,
        crest_factor_db=14.0,
        lra_lu=8.0,
    )
    # Should have high confidence due to clear match
    assert result.confidence > 0.7


def test_adversarial_all_features_moderate():
    """Track with all moderate features should be classified with reasonable confidence."""
    result = classify_track(
        bpm=130.0,
        lufs_i=-9.0,
        kick_prominence=0.5,
        spectral_centroid_mean=2500.0,
        onset_rate=5.5,
        hp_ratio=0.5,
        flux_std=50.0,
        energy_std=0.15,
        crest_factor_db=13.0,
        lra_lu=8.0,
    )
    # Should classify as driving (most balanced profile)
    assert result.mood == TrackMood.DRIVING
    assert 0.0 <= result.confidence <= 1.0


def test_adversarial_conflicting_features():
    """Track with conflicting features (high kick + low BPM)."""
    result = classify_track(
        bpm=120.0,  # Low (ambient-like)
        lufs_i=-7.0,
        kick_prominence=0.75,  # High (peak-time-like)
        spectral_centroid_mean=2500.0,
        onset_rate=5.0,
        hp_ratio=0.4,
        flux_std=50.0,
        energy_std=0.16,
        crest_factor_db=13.0,
        lra_lu=8.0,
    )
    # Classifier should handle conflicting features gracefully
    assert result.mood in [TrackMood.PEAK_TIME, TrackMood.DUB_TECHNO, TrackMood.DRIVING]
    assert 0.0 <= result.confidence <= 1.0


def test_adversarial_extreme_values():
    """Track with extreme feature values."""
    result = classify_track(
        bpm=180.0,  # Very high
        lufs_i=-3.0,  # Very loud
        kick_prominence=0.95,  # Very high
        spectral_centroid_mean=8000.0,  # Very bright
        onset_rate=20.0,  # Very busy
        hp_ratio=0.1,  # Very percussive
        flux_std=120.0,  # High variance
        energy_std=0.35,  # High dynamics
        crest_factor_db=20.0,  # High transients
        lra_lu=15.0,  # Wide range
    )
    # Should classify into one of the high-energy categories
    assert result.mood in [TrackMood.HARD_TECHNO, TrackMood.INDUSTRIAL]
    assert 0.0 <= result.confidence <= 1.0
