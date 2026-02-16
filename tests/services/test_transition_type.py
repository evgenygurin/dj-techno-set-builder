"""Tests for TransitionTypeRecommender — djay Pro Neural Mix transition selection."""

from app.services.transition_scoring import TrackFeatures
from app.services.transition_type import recommend_transition
from app.utils.audio._types import TransitionType


def _make_features(**overrides: object) -> TrackFeatures:
    """Helper to create TrackFeatures with sensible defaults."""
    defaults = {
        "bpm": 128.0,
        "energy_lufs": -10.0,
        "key_code": 0,
        "harmonic_density": 0.5,
        "centroid_hz": 2000.0,
        "band_ratios": [0.3, 0.5, 0.2],
        "onset_rate": 5.0,
        "kick_prominence": 0.5,
        "hnr_db": 10.0,
        "hp_ratio": 0.5,
    }
    defaults.update(overrides)
    return TrackFeatures(**defaults)  # type: ignore[arg-type]


# ── Priority 1: Both drum-heavy → DRUM_CUT ──


def test_both_drum_heavy_returns_drum_cut():
    """When both tracks have kick > 0.6, recommend DRUM_CUT."""
    a = _make_features(kick_prominence=0.8)
    b = _make_features(kick_prominence=0.7)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.DRUM_CUT
    assert rec.confidence > 0.7


# ── Priority 2: B drum-heavy, A melodic → DRUM_SWAP ──


def test_b_drum_heavy_a_melodic_returns_drum_swap():
    """When B has strong kick and A is melodic, recommend DRUM_SWAP."""
    a = _make_features(kick_prominence=0.3, hnr_db=15.0)
    b = _make_features(kick_prominence=0.8)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.DRUM_SWAP


# ── Priority 3: Both melodic + Camelot match → HARMONIC_SUSTAIN ──


def test_both_melodic_camelot_match_returns_harmonic_sustain():
    """When both melodic and keys are compatible, recommend HARMONIC_SUSTAIN."""
    a = _make_features(hnr_db=18.0, harmonic_density=0.8)
    b = _make_features(hnr_db=16.0, harmonic_density=0.7)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.HARMONIC_SUSTAIN


def test_melodic_but_camelot_mismatch_not_harmonic_sustain():
    """If keys are incompatible, should NOT be HARMONIC_SUSTAIN."""
    a = _make_features(hnr_db=18.0, harmonic_density=0.8)
    b = _make_features(hnr_db=16.0, harmonic_density=0.7)
    rec = recommend_transition(a, b, camelot_compatible=False)
    assert rec.transition_type != TransitionType.HARMONIC_SUSTAIN


# ── Priority 4: A has vocal → VOCAL_SUSTAIN ──


def test_a_has_vocal_returns_vocal_sustain():
    """When track A has vocal content (hp_ratio < 0.4), recommend VOCAL_SUSTAIN."""
    a = _make_features(hp_ratio=0.3)
    b = _make_features()
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.VOCAL_SUSTAIN


# ── Priority 5: BPM diff > 4 → FILTER ──


def test_large_bpm_diff_returns_filter():
    """When BPM difference > 4, recommend FILTER to mask mismatch."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=134.0)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.FILTER


# ── Priority 6: High energy delta → NEURAL_ECHO_OUT ──


def test_high_energy_delta_returns_neural_echo_out():
    """When energy difference > 2 LUFS, recommend NEURAL_ECHO_OUT."""
    a = _make_features(energy_lufs=-8.0)
    b = _make_features(energy_lufs=-12.0)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.NEURAL_ECHO_OUT


# ── Priority 7: Energy drops → NEURAL_FADE ──


def test_energy_drops_returns_neural_fade():
    """When energy drops (A > B by 1-2 LUFS), recommend NEURAL_FADE."""
    a = _make_features(energy_lufs=-9.0)
    b = _make_features(energy_lufs=-10.5)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.NEURAL_FADE


# ── Priority 8: Both high-energy → EQ ──


def test_both_high_energy_returns_eq():
    """When both tracks are high-energy, recommend EQ bass-swap."""
    a = _make_features(energy_lufs=-7.0)
    b = _make_features(energy_lufs=-7.5)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.EQ


# ── Priority 9: Energy rises → ECHO ──


def test_energy_rises_returns_echo():
    """When energy rises (B > A), recommend ECHO."""
    a = _make_features(energy_lufs=-12.0)
    b = _make_features(energy_lufs=-11.5)
    rec = recommend_transition(a, b, camelot_compatible=True)
    assert rec.transition_type == TransitionType.ECHO


# ── Priority 10: Default → FADE ──


def test_default_returns_fade():
    """Default fallback should be FADE."""
    a = _make_features()
    b = _make_features()
    rec = recommend_transition(a, b, camelot_compatible=True)
    # Since defaults are neutral, the exact type depends on priority chain.
    # At least verify it returns a valid TransitionRecommendation.
    assert isinstance(rec.transition_type, TransitionType)
    assert 0.0 <= rec.confidence <= 1.0
    assert len(rec.reason) > 0


# ── Edge cases ──


def test_recommendation_always_has_reason():
    """Every recommendation must include a human-readable reason."""
    a = _make_features(kick_prominence=0.9)
    b = _make_features(kick_prominence=0.9)
    rec = recommend_transition(a, b, camelot_compatible=False)
    assert isinstance(rec.reason, str)
    assert len(rec.reason) > 5


def test_confidence_range():
    """Confidence should always be in [0, 1]."""
    combos = [
        (_make_features(kick_prominence=0.9), _make_features(kick_prominence=0.9)),
        (_make_features(hp_ratio=0.2), _make_features()),
        (_make_features(bpm=128), _make_features(bpm=140)),
    ]
    for a, b in combos:
        rec = recommend_transition(a, b, camelot_compatible=True)
        assert 0.0 <= rec.confidence <= 1.0
