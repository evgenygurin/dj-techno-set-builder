"""Tests for CLI setbuilder sub-command helpers."""

from __future__ import annotations

from app.cli.setbuilder import _recommend_type


def test_recommend_type_blend() -> None:
    """High BPM + harmonic → blend."""
    result = _recommend_type({"bpm": 0.98, "harmonic": 0.90, "energy": 0.7})
    assert result == "blend"


def test_recommend_type_eq() -> None:
    """High BPM, low harmonic → EQ mix."""
    result = _recommend_type({"bpm": 0.92, "harmonic": 0.50, "energy": 0.7})
    assert result == "eq"


def test_recommend_type_drum_swap() -> None:
    """Low BPM, high energy → drum swap."""
    result = _recommend_type({"bpm": 0.70, "harmonic": 0.50, "energy": 0.85})
    assert result == "drum_swap"


def test_recommend_type_drum_cut_fallback() -> None:
    """Low everything → drum cut."""
    result = _recommend_type({"bpm": 0.50, "harmonic": 0.30, "energy": 0.40})
    assert result == "drum_cut"


def test_recommend_type_empty_dict() -> None:
    """Missing keys default to 0."""
    result = _recommend_type({})
    assert result == "drum_cut"
