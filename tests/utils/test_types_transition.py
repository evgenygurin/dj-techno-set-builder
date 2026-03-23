"""Tests for TransitionType enum and TransitionRecommendation dataclass."""

from app.audio._types import TransitionRecommendation, TransitionType


def test_transition_type_is_str_enum():
    """TransitionType values should be lowercase strings."""
    assert TransitionType.DRUM_CUT == "drum_cut"
    assert TransitionType.DRUM_SWAP == "drum_swap"
    assert TransitionType.HARMONIC_SUSTAIN == "harmonic_sustain"
    assert TransitionType.VOCAL_SUSTAIN == "vocal_sustain"
    assert TransitionType.NEURAL_ECHO_OUT == "neural_echo_out"
    assert TransitionType.NEURAL_FADE == "neural_fade"
    assert TransitionType.EQ == "eq"
    assert TransitionType.FILTER == "filter"
    assert TransitionType.ECHO == "echo"
    assert TransitionType.FADE == "fade"


def test_transition_type_has_10_members():
    """Should have exactly 10 transition types."""
    assert len(TransitionType) == 10


def test_transition_recommendation_frozen():
    """TransitionRecommendation should be a frozen dataclass."""
    rec = TransitionRecommendation(
        transition_type=TransitionType.DRUM_CUT,
        confidence=0.85,
        reason="Both tracks are drum-heavy",
    )
    assert rec.transition_type == TransitionType.DRUM_CUT
    assert rec.confidence == 0.85
    assert rec.reason == "Both tracks are drum-heavy"
    assert rec.alt_type is None


def test_transition_recommendation_with_alt():
    """TransitionRecommendation should support alt_type."""
    rec = TransitionRecommendation(
        transition_type=TransitionType.DRUM_CUT,
        confidence=0.85,
        reason="Both drum-heavy",
        alt_type=TransitionType.EQ,
    )
    assert rec.alt_type == TransitionType.EQ
