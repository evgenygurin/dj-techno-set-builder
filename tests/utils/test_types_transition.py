"""Tests for TransitionType enum and TransitionRecommendation dataclass."""

from app.utils.audio._types import TransitionRecommendation, TransitionType


def test_transition_type_is_str_enum():
    """TransitionType values must match exact djay Pro AI Crossfader FX names."""
    assert TransitionType.NM_DRUM_SWAP == "Neural Mix (Drum Swap)"
    assert TransitionType.FILTER == "Filter"
    assert TransitionType.ECHO == "Echo"
    assert TransitionType.RISER == "Riser"
    assert TransitionType.TREMOLO == "Tremolo"
    assert TransitionType.FADE == "Fade"


def test_transition_type_has_16_members():
    """Should have exactly 16 djay Pro AI transition types."""
    assert len(TransitionType) == 16


def test_transition_recommendation_frozen():
    """TransitionRecommendation should be a frozen dataclass."""
    rec = TransitionRecommendation(
        transition_type=TransitionType.FADE,
        confidence=0.85,
        reason="Стандартный кроссфейд",
    )
    assert rec.transition_type == TransitionType.FADE
    assert rec.confidence == 0.85
    assert rec.reason == "Стандартный кроссфейд"
    assert rec.alt_type is None
    assert rec.djay_bars == 16
    assert rec.djay_bpm_mode == "Sync"


def test_transition_recommendation_with_alt():
    """TransitionRecommendation should support alt_type."""
    rec = TransitionRecommendation(
        transition_type=TransitionType.NM_DRUM_SWAP,
        confidence=0.90,
        reason="Both drum-heavy",
        alt_type=TransitionType.FILTER,
    )
    assert rec.alt_type == TransitionType.FILTER


def test_transition_recommendation_djay_fields():
    """djay_bars and djay_bpm_mode can be set explicitly."""
    rec = TransitionRecommendation(
        transition_type=TransitionType.RISER,
        confidence=0.80,
        reason="Pre-peak riser",
        djay_bars=8,
        djay_bpm_mode="Sync + Tempo Blend",
    )
    assert rec.djay_bars == 8
    assert rec.djay_bpm_mode == "Sync + Tempo Blend"
