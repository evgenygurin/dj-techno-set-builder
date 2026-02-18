"""Tests for template_slot_fit in GA fitness."""

from __future__ import annotations

import numpy as np

from app.utils.audio.mood_classifier import TrackMood
from app.utils.audio.set_generator import (
    GAConfig,
    GeneticSetGenerator,
    TrackData,
    template_slot_fit,
)
from app.utils.audio.set_templates import SetSlot, TemplateName, get_template


def _make_track(
    track_id: int,
    bpm: float = 130.0,
    energy: float = 0.5,
    key_code: int = 1,
    mood: int = 3,
) -> TrackData:
    return TrackData(
        track_id=track_id,
        bpm=bpm,
        energy=energy,
        key_code=key_code,
        mood=mood,
    )


class TestTemplateSlotFit:
    """Tests for the template_slot_fit scoring function."""

    def test_perfect_match_scores_high(self):
        """Track matching slot mood+energy+BPM should score > 0.8."""
        slot = SetSlot(
            position=0.5,
            mood=TrackMood.DRIVING,
            energy_target=-8.0,
            bpm_range=(128.0, 132.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        # mood=DRIVING(3), energy maps -8 LUFS -> 0.75, bpm in range
        track = _make_track(1, bpm=130.0, energy=0.75, mood=3)
        score = template_slot_fit([track], [slot])
        assert score > 0.8

    def test_wrong_mood_scores_low(self):
        """Track with wrong mood should score < 0.5."""
        slot = SetSlot(
            position=0.5,
            mood=TrackMood.AMBIENT_DUB,
            energy_target=-12.0,
            bpm_range=(122.0, 126.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        # mood=HARD_TECHNO(6) for ambient slot
        track = _make_track(1, bpm=135.0, energy=0.9, mood=6)
        score = template_slot_fit([track], [slot])
        assert score < 0.5

    def test_empty_slots_returns_neutral(self):
        """No slots (FULL_LIBRARY) -> returns 0.5 (neutral)."""
        score = template_slot_fit([_make_track(1)], [])
        assert score == 0.5

    def test_multiple_slots_averaged(self):
        """Score is mean of per-slot scores."""
        slot_good = SetSlot(
            position=0.0,
            mood=TrackMood.DRIVING,
            energy_target=-8.0,
            bpm_range=(128.0, 132.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        slot_bad = SetSlot(
            position=1.0,
            mood=TrackMood.AMBIENT_DUB,
            energy_target=-12.0,
            bpm_range=(122.0, 126.0),
            duration_target_s=180,
            flexibility=0.3,
        )
        t_good = _make_track(1, bpm=130.0, energy=0.75, mood=3)
        t_bad = _make_track(2, bpm=130.0, energy=0.75, mood=3)
        score = template_slot_fit([t_good, t_bad], [slot_good, slot_bad])
        # First track perfect, second bad -> average
        assert 0.3 < score < 0.8


class TestGAWithTemplate:
    """Test GA uses template_slot_fit when slots provided."""

    def test_ga_config_has_template_weight(self):
        """GAConfig should have w_template field."""
        cfg = GAConfig(w_template=0.25)
        assert cfg.w_template == 0.25

    def test_fitness_includes_template(self):
        """Fitness with template slots should differ from without."""
        tracks = [_make_track(i, bpm=125 + i, mood=i % 6 + 1) for i in range(5)]
        matrix = np.ones((5, 5), dtype=np.float64) * 0.5
        np.fill_diagonal(matrix, 0.0)

        template = get_template(TemplateName.CLASSIC_60)
        slots = list(template.slots)[:5]  # first 5 slots

        gen_no_tmpl = GeneticSetGenerator(
            tracks,
            matrix,
            GAConfig(
                w_template=0.0,
                track_count=5,
                generations=1,
                population_size=10,
            ),
        )
        gen_with_tmpl = GeneticSetGenerator(
            tracks,
            matrix,
            GAConfig(
                w_template=0.25,
                track_count=5,
                generations=1,
                population_size=10,
            ),
            template_slots=slots,
        )

        # Should produce different fitness values
        ch = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        f1 = gen_no_tmpl._fitness(ch)
        f2 = gen_with_tmpl._fitness(ch)
        assert f1 != f2
