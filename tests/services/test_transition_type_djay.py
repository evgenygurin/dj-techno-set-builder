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
