from __future__ import annotations

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal  # noqa: E402
from app.utils.audio._types import SectionResult  # noqa: E402
from app.utils.audio.structure import (  # noqa: E402
    _compute_section_pulse_clarity,
    segment_structure,
)

SR = 44100


@pytest.fixture
def techno_structure() -> AudioSignal:
    """30-second signal simulating intro(low) → buildup(rising) → drop(high) → outro(falling).

    0-8s:   quiet (intro)
    8-14s:  rising energy (buildup)
    14-22s: loud (drop)
    22-30s: falling energy (outro)
    """
    duration = 30.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)

    # Envelope: 0→0.2 (intro), 0.2→0.8 (buildup), 0.8 (drop), 0.8→0.1 (outro)
    envelope = np.piecewise(
        t,
        [t < 8, (t >= 8) & (t < 14), (t >= 14) & (t < 22), t >= 22],
        [
            lambda x: 0.15 + 0.05 * np.sin(2 * np.pi * 0.5 * x),
            lambda x: 0.2 + (x - 8) / 6 * 0.6,
            lambda x: np.full_like(x, 0.8),
            lambda x: 0.8 - (x - 22) / 8 * 0.7,
        ],
    )

    # Carrier: mix of kick (50Hz) + noise for texture
    rng = np.random.default_rng(42)
    carrier = (
        0.5 * np.sin(2 * np.pi * 50 * t)
        + 0.3 * np.sin(2 * np.pi * 200 * t)
        + 0.2 * rng.standard_normal(len(t))
    )

    samples = (envelope * carrier).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


class TestSegmentStructure:
    def test_returns_list_of_sections(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        assert isinstance(sections, list)
        assert all(isinstance(s, SectionResult) for s in sections)

    def test_at_least_two_sections(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        assert len(sections) >= 2

    def test_sections_cover_full_duration(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        assert sections[0].start_s < 2.0  # starts near beginning
        assert sections[-1].end_s > techno_structure.duration_s - 1.0

    def test_sections_non_overlapping(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for i in range(len(sections) - 1):
            # small tolerance
            assert sections[i].end_s <= sections[i + 1].start_s + 0.1

    def test_section_type_valid(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for s in sections:
            assert 0 <= s.section_type <= 11

    def test_energy_fields_range(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for s in sections:
            assert 0.0 <= s.energy_mean <= 1.0
            assert 0.0 <= s.energy_max <= 1.0
            assert 0.0 <= s.boundary_confidence <= 1.0

    def test_duration_positive(self, techno_structure: AudioSignal) -> None:
        sections = segment_structure(techno_structure)
        for s in sections:
            assert s.duration_s > 0

    def test_drop_section_has_high_energy(self, techno_structure: AudioSignal) -> None:
        """The loudest section should be labeled as DROP (2) or have high energy."""
        sections = segment_structure(techno_structure)
        loudest = max(sections, key=lambda s: s.energy_mean)
        # Either labeled as drop or has energy > 0.5
        assert loudest.section_type == 2 or loudest.energy_mean > 0.5

    def test_with_beats_sets_onset_rate_and_pulse(self, techno_structure: AudioSignal) -> None:
        beat_times = np.arange(0.5, techno_structure.duration_s, 0.5, dtype=np.float32)
        sections = segment_structure(
            techno_structure,
            beat_times=beat_times,
            track_pulse_clarity=0.8,
        )
        assert all(s.onset_rate is not None for s in sections)
        assert all(s.pulse_clarity is not None for s in sections)
        assert all(0.0 <= s.pulse_clarity <= 1.0 for s in sections if s.pulse_clarity is not None)


class TestSectionPulseClarity:
    def test_regular_beats_high_clarity(self) -> None:
        beats = np.array([0.0, 0.5, 1.0, 1.5, 2.0], dtype=np.float32)
        clarity = _compute_section_pulse_clarity(beats, track_pulse_clarity=None)
        assert clarity == pytest.approx(1.0)

    def test_irregular_beats_blends_with_track_clarity(self) -> None:
        beats = np.array([0.0, 0.5, 1.3, 2.4, 3.0], dtype=np.float32)
        local = _compute_section_pulse_clarity(beats, track_pulse_clarity=None)
        blended = _compute_section_pulse_clarity(beats, track_pulse_clarity=0.2)
        expected = float(np.clip(0.7 * local + 0.3 * 0.2, 0.0, 1.0))
        assert blended == pytest.approx(expected)

    def test_short_section_falls_back_to_track_or_zero(self) -> None:
        beats = np.array([0.2, 0.8], dtype=np.float32)
        assert _compute_section_pulse_clarity(
            beats,
            track_pulse_clarity=0.6,
        ) == pytest.approx(0.6)
        assert _compute_section_pulse_clarity(
            beats,
            track_pulse_clarity=None,
        ) == pytest.approx(0.0)
