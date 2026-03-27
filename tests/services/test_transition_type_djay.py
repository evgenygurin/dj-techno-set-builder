"""Tests for djay Pro AI Crossfader FX transition types."""

from app.utils.audio._types import TransitionType


def test_transition_type_has_all_16_djay_cfx():
    """TransitionType must match exact djay Pro AI Crossfader FX names."""
    expected = {
        # Classic FX
        "Fade",
        "Filter",
        "EQ",
        "Echo",
        "Dissolve",
        "Tremolo",
        "Lunar Echo",
        "Riser",
        "Shuffle",
        # Neural Mix FX
        "Neural Mix (Fade)",
        "Neural Mix (Echo Out)",
        "Neural Mix (Vocal Sustain)",
        "Neural Mix (Harmonic Sustain)",
        "Neural Mix (Drum Swap)",
        "Neural Mix (Vocal Cut)",
        "Neural Mix (Drum Cut)",
    }
    actual = {member.value for member in TransitionType}
    assert actual == expected, f"Missing: {expected - actual}, Extra: {actual - expected}"


def test_transition_type_enum_names():
    """Enum attribute names must be valid Python identifiers."""
    assert TransitionType.FADE == "Fade"
    assert TransitionType.FILTER == "Filter"
    assert TransitionType.EQ == "EQ"
    assert TransitionType.ECHO == "Echo"
    assert TransitionType.DISSOLVE == "Dissolve"
    assert TransitionType.TREMOLO == "Tremolo"
    assert TransitionType.LUNAR_ECHO == "Lunar Echo"
    assert TransitionType.RISER == "Riser"
    assert TransitionType.SHUFFLE == "Shuffle"
    assert TransitionType.NM_FADE == "Neural Mix (Fade)"
    assert TransitionType.NM_ECHO_OUT == "Neural Mix (Echo Out)"
    assert TransitionType.NM_VOCAL_SUSTAIN == "Neural Mix (Vocal Sustain)"
    assert TransitionType.NM_HARMONIC_SUSTAIN == "Neural Mix (Harmonic Sustain)"
    assert TransitionType.NM_DRUM_SWAP == "Neural Mix (Drum Swap)"
    assert TransitionType.NM_VOCAL_CUT == "Neural Mix (Vocal Cut)"
    assert TransitionType.NM_DRUM_CUT == "Neural Mix (Drum Cut)"


def test_transition_recommendation_has_djay_fields():
    from app.utils.audio._types import TransitionRecommendation

    rec = TransitionRecommendation(
        transition_type=TransitionType.NM_DRUM_SWAP,
        confidence=0.9,
        reason="test",
        djay_bars=8,
        djay_bpm_mode="Sync",
    )
    assert rec.djay_bars == 8
    assert rec.djay_bpm_mode == "Sync"
    assert rec.transition_type == "Neural Mix (Drum Swap)"


# ── Additional tests for recommend_transition logic ──────────────────────────

from app.services.transition_scoring import TrackFeatures  # noqa: E402
from app.services.transition_type import recommend_transition  # noqa: E402


def _make_features(**overrides) -> TrackFeatures:
    """Helper to create TrackFeatures with techno defaults."""
    defaults = dict(
        bpm=130.0,
        energy_lufs=-8.0,
        key_code=0,
        harmonic_density=0.5,
        centroid_hz=2500.0,
        band_ratios=[0.3, 0.4, 0.3],
        onset_rate=4.0,
        kick_prominence=0.75,
        hnr_db=5.0,
        spectral_slope=-0.02,
    )
    defaults.update(overrides)
    return TrackFeatures(**defaults)


class TestNeuralMixDrumSwap:
    """NM Drum Swap: strong kicks + close BPM + close key."""

    def test_strong_kicks_close_bpm_key(self):
        a = _make_features(kick_prominence=0.85, bpm=128.0)
        b = _make_features(kick_prominence=0.80, bpm=129.0)
        rec = recommend_transition(
            a, b, camelot_dist=1, set_position=0.5, energy_direction="stable"
        )
        assert rec.transition_type == TransitionType.NM_DRUM_SWAP


class TestFilter:
    """Filter: Camelot conflict (dist >= 3)."""

    def test_camelot_conflict(self):
        a = _make_features()
        b = _make_features()
        rec = recommend_transition(
            a, b, camelot_dist=4, set_position=0.5, energy_direction="stable"
        )
        assert rec.transition_type in (TransitionType.FILTER, TransitionType.EQ)


class TestEQ:
    """EQ: strong kicks + stable energy (driving/peak sections)."""

    def test_driving_section(self):
        a = _make_features(kick_prominence=0.80, centroid_hz=2800.0)
        b = _make_features(kick_prominence=0.82, centroid_hz=2900.0)
        rec = recommend_transition(
            a,
            b,
            camelot_dist=1,
            set_position=0.6,
            energy_direction="stable",
        )
        assert rec.transition_type in (TransitionType.EQ, TransitionType.NM_DRUM_SWAP)


class TestRiser:
    """Riser: energy going up in pre-peak position."""

    def test_pre_peak_energy_up(self):
        a = _make_features(kick_prominence=0.50)
        b = _make_features(kick_prominence=0.50)
        rec = recommend_transition(
            a,
            b,
            camelot_dist=1,
            set_position=0.72,
            energy_direction="up",
        )
        assert rec.transition_type == TransitionType.RISER


class TestNMDrumCut:
    """NM Drum Cut: breakdown moment, energy dropping."""

    def test_breakdown_energy_down(self):
        a = _make_features(kick_prominence=0.80)
        b = _make_features(kick_prominence=0.70, centroid_hz=2000.0)
        rec = recommend_transition(
            a,
            b,
            camelot_dist=1,
            set_position=0.55,
            energy_direction="down",
        )
        assert rec.transition_type in (
            TransitionType.NM_DRUM_CUT,
            TransitionType.ECHO,
            TransitionType.NM_ECHO_OUT,
        )


class TestLunarEcho:
    """Lunar Echo / Echo: atmospheric tracks or closing."""

    def test_closing_position(self):
        a = _make_features(hp_ratio=3.0, centroid_hz=1800.0)
        b = _make_features(hp_ratio=2.8, centroid_hz=1900.0)
        rec = recommend_transition(
            a,
            b,
            camelot_dist=1,
            set_position=0.95,
            energy_direction="down",
        )
        assert rec.transition_type in (
            TransitionType.LUNAR_ECHO,
            TransitionType.ECHO,
            TransitionType.FADE,
            TransitionType.DISSOLVE,
            TransitionType.NM_FADE,
        )


class TestFallbackFade:
    """Fade is the ultimate fallback."""

    def test_generic_tracks(self):
        a = _make_features(kick_prominence=0.40, centroid_hz=2500.0)
        b = _make_features(kick_prominence=0.40, centroid_hz=2500.0)
        rec = recommend_transition(
            a,
            b,
            camelot_dist=1,
            set_position=0.3,
            energy_direction="stable",
        )
        assert rec.transition_type in TransitionType
        assert 0.0 <= rec.confidence <= 1.0
        assert rec.djay_bars in (4, 8, 16, 32)
