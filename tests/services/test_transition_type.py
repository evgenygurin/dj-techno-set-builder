"""Tests for TransitionTypeRecommender — djay Pro AI Crossfader FX selection."""

from app.services.transition_scoring import TrackFeatures
from app.services.transition_type import recommend_transition
from app.utils.audio._types import TransitionType


def _make_features(**overrides: object) -> TrackFeatures:
    """Helper to create TrackFeatures with sensible defaults."""
    defaults: dict[str, object] = {
        "bpm": 128.0,
        "energy_lufs": -10.0,
        "key_code": 0,
        "harmonic_density": 0.5,
        "centroid_hz": 2500.0,
        "band_ratios": [0.3, 0.5, 0.2],
        "onset_rate": 4.0,
        "kick_prominence": 0.5,
        "hnr_db": 10.0,
        "hp_ratio": 1.0,
    }
    defaults.update(overrides)
    return TrackFeatures(**defaults)  # type: ignore[arg-type]


# ── Rule 1: Neural Mix ──


def test_neural_mix_both_drum_heavy_close_bpm_compatible_key():
    """Neural Mix when both tracks have strong kick, close BPM, and compatible key."""
    a = _make_features(kick_prominence=0.82)
    b = _make_features(kick_prominence=0.88)
    rec = recommend_transition(a, b, camelot_dist=1)
    assert rec.transition_type == TransitionType.NEURAL_MIX
    assert rec.djay_bars == 16
    assert rec.djay_bpm_mode == "Sync"
    assert rec.confidence >= 0.75


def test_neural_mix_not_when_bpm_too_far():
    """No Neural Mix when BPM diff > 4."""
    a = _make_features(bpm=128.0, kick_prominence=0.82)
    b = _make_features(bpm=133.0, kick_prominence=0.88)
    rec = recommend_transition(a, b, camelot_dist=1)
    assert rec.transition_type != TransitionType.NEURAL_MIX


def test_neural_mix_not_when_camelot_too_far():
    """No Neural Mix when Camelot distance > 2."""
    a = _make_features(kick_prominence=0.82)
    b = _make_features(kick_prominence=0.88)
    rec = recommend_transition(a, b, camelot_dist=3)
    assert rec.transition_type != TransitionType.NEURAL_MIX


# ── Rule 2: Techno ──


def test_techno_stable_energy_close_bpm():
    """Techno for close BPM with stable energy direction."""
    a = _make_features(bpm=128.0, kick_prominence=0.4)
    b = _make_features(bpm=130.0, kick_prominence=0.4)
    rec = recommend_transition(a, b, camelot_dist=1, energy_direction="stable")
    assert rec.transition_type == TransitionType.TECHNO
    assert rec.djay_bars == 16


def test_techno_sync_when_bpm_diff_le_3():
    """BPM mode is Sync when diff <= 3."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=130.0)  # diff = 2
    rec = recommend_transition(a, b, camelot_dist=1, energy_direction="stable")
    assert rec.transition_type == TransitionType.TECHNO
    assert rec.djay_bpm_mode == "Sync"


def test_techno_tempo_blend_when_bpm_diff_gt_3():
    """BPM mode is Sync + Tempo Blend when diff > 3."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=132.5)  # diff = 4.5
    rec = recommend_transition(a, b, camelot_dist=1, energy_direction="up")
    assert rec.transition_type == TransitionType.TECHNO
    assert rec.djay_bpm_mode == "Sync + Tempo Blend"


def test_techno_not_when_energy_drops():
    """No Techno when energy is going down."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=129.0)
    rec = recommend_transition(a, b, camelot_dist=1, energy_direction="down")
    assert rec.transition_type != TransitionType.TECHNO


# ── Rule 3: Riser ──


def test_riser_mid_set_energy_rising():
    """Riser when energy is up and set_position is in pre-peak zone."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=134.0)  # bpm_diff=6, no Techno (energy up is ok)
    # But bpm_diff=6 → Techno rule matches first if energy_up. Use bpm_diff > 6
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=135.0)  # bpm_diff=7
    rec = recommend_transition(a, b, camelot_dist=1, set_position=0.6, energy_direction="up")
    assert rec.transition_type == TransitionType.RISER
    assert rec.djay_bars == 8


def test_riser_not_outside_position_range():
    """No Riser outside 0.4-0.75 set_position."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=135.0)
    rec = recommend_transition(a, b, camelot_dist=1, set_position=0.9, energy_direction="up")
    assert rec.transition_type != TransitionType.RISER


# ── Rule 4: Filter ──


def test_filter_camelot_conflict():
    """Filter for Camelot distance >= 3."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=135.0)
    rec = recommend_transition(a, b, camelot_dist=4)
    assert rec.transition_type == TransitionType.FILTER
    assert rec.djay_bars == 8


def test_filter_bpm_mode_based_on_diff():
    """Filter BPM mode: Sync if diff<=4, Sync+Blend if diff>4."""
    a = _make_features(bpm=128.0)
    b = _make_features(bpm=133.0, centroid_hz=2500.0)  # diff=5 > 4
    rec = recommend_transition(a, b, camelot_dist=4, energy_direction="down")
    assert rec.transition_type == TransitionType.FILTER
    assert rec.djay_bpm_mode == "Sync + Tempo Blend"


# ── Rule 5: Echo ──


def test_echo_atmospheric_track():
    """Echo when track A has high hp_ratio (melodic/atmospheric)."""
    a = _make_features(hp_ratio=3.0)
    b = _make_features()
    rec = recommend_transition(a, b, camelot_dist=2, energy_direction="stable")
    # bpm_diff<=6 + stable → Techno hits first, but hp_ratio only evaluated after
    # Need bpm_diff > 6 so Techno doesn't trigger
    a = _make_features(bpm=128.0, hp_ratio=3.0)
    b = _make_features(bpm=136.0)  # diff=8
    rec = recommend_transition(a, b, camelot_dist=2, energy_direction="down")
    assert rec.transition_type == TransitionType.ECHO
    assert rec.djay_bars == 16


def test_echo_at_end_of_set():
    """Echo when set_position > 0.85 (closing section)."""
    a = _make_features(bpm=128.0, centroid_hz=2500.0)
    b = _make_features(bpm=136.0)
    rec = recommend_transition(a, b, camelot_dist=2, set_position=0.9, energy_direction="down")
    assert rec.transition_type == TransitionType.ECHO


# ── Rule 6: Repeater ──


def test_repeater_high_onset_mid_set():
    """Repeater for high onset rate + strong kick in mid-set."""
    a = _make_features(bpm=128.0, onset_rate=6.0, kick_prominence=0.85, centroid_hz=2500.0)
    b = _make_features(bpm=136.0)  # bpm_diff=8 → Riser needs energy_up which we won't set
    rec = recommend_transition(a, b, camelot_dist=2, set_position=0.5, energy_direction="stable")
    # Filter applies first (camelot_dist=2 < 3, so no), Echo (hp_ratio=1.0 < 2.5, pos < 0.85, centroid 2500>2200)
    # → Repeater should fire
    assert rec.transition_type == TransitionType.REPEATER
    assert rec.djay_bars == 8


# ── Rule 7: Beat Match (fallback) ──


def test_beat_match_fallback():
    """Beat Match is the default fallback."""
    # high bpm_diff → no Techno, low onset/kick → no Repeater, no camelot issue
    a = _make_features(bpm=128.0, centroid_hz=2500.0, kick_prominence=0.5, onset_rate=3.0)
    b = _make_features(bpm=136.0, centroid_hz=2500.0)  # bpm_diff=8
    rec = recommend_transition(a, b, camelot_dist=2, set_position=0.5, energy_direction="stable")
    assert rec.transition_type == TransitionType.BEAT_MATCH
    assert rec.djay_bpm_mode == "Automatic"
    assert rec.djay_bars == 16


# ── Edge cases ──


def test_recommendation_always_has_reason():
    """Every recommendation must include a human-readable reason."""
    a = _make_features(kick_prominence=0.9)
    b = _make_features(kick_prominence=0.9)
    rec = recommend_transition(a, b, camelot_dist=0)
    assert isinstance(rec.reason, str)
    assert len(rec.reason) > 5


def test_confidence_range():
    """Confidence should always be in [0, 1]."""
    combos = [
        (_make_features(kick_prominence=0.9), _make_features(kick_prominence=0.9), 1),
        (_make_features(hp_ratio=3.5), _make_features(), 2),
        (_make_features(bpm=128), _make_features(bpm=136), 4),
    ]
    for a, b, cd in combos:
        rec = recommend_transition(a, b, camelot_dist=cd)
        assert 0.0 <= rec.confidence <= 1.0


def test_djay_bars_valid_values():
    """djay_bars should always be in {4, 8, 16, 32}."""
    valid_bars = {4, 8, 16, 32}
    cases = [
        (_make_features(kick_prominence=0.9), _make_features(kick_prominence=0.9), 1, "stable"),
        (_make_features(bpm=128), _make_features(bpm=130), 0, "stable"),
        (_make_features(bpm=128), _make_features(bpm=140), 4, "stable"),
    ]
    for a, b, cd, ed in cases:
        rec = recommend_transition(a, b, camelot_dist=cd, energy_direction=ed)
        assert rec.djay_bars in valid_bars
