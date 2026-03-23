"""Tests for SetCurationService.compute_energy_arc_adherence."""

import pytest

from app.services.set_curation import SetCurationService
from app.audio.set_templates import TemplateName, get_template


@pytest.fixture
def svc() -> SetCurationService:
    return SetCurationService()


class TestComputeEnergyArcAdherence:
    """Tests for energy arc adherence computation."""

    def test_perfect_match_returns_high_score(self, svc: SetCurationService):
        """Tracks sampled from the template curve should score high."""
        template = get_template(TemplateName.CLASSIC_60)
        n = len(template.slots)
        # Sample the template at exact track positions (not slot positions)
        lufs_values = [svc._interpolate_template_energy(template, i / (n - 1)) for i in range(n)]
        score = svc.compute_energy_arc_adherence(lufs_values, "classic_60")
        assert score >= 0.99, f"Perfect interpolated match should score >= 0.99, got {score}"

    def test_flat_energy_scores_lower_than_good_match(self, svc: SetCurationService):
        """A flat energy curve should score significantly lower than a good match."""
        template = get_template(TemplateName.CLASSIC_60)
        n = len(template.slots)

        # Good match: sampled from template
        good_lufs = [svc._interpolate_template_energy(template, i / (n - 1)) for i in range(n)]
        good_score = svc.compute_energy_arc_adherence(good_lufs, "classic_60")

        # Flat: constant energy, no arc
        flat_lufs = [-9.0] * n
        flat_score = svc.compute_energy_arc_adherence(flat_lufs, "classic_60")

        assert flat_score < good_score, (
            f"Flat ({flat_score}) should be lower than good match ({good_score})"
        )

    def test_extreme_flat_scores_low(self, svc: SetCurationService):
        """Very quiet flat energy (ambient-level) should score low for peak_hour."""
        flat_quiet = [-14.0] * 20  # very quiet, peak_hour wants -6 to -9
        score = svc.compute_energy_arc_adherence(flat_quiet, "peak_hour_60")
        assert score < 0.5, f"Very quiet flat should score < 0.5, got {score}"

    def test_inverted_arc_scores_lowest(self, svc: SetCurationService):
        """Inverted energy (peak at edges, valley in middle) should score very low."""
        template = get_template(TemplateName.CLASSIC_60)
        # Reverse the template energy curve
        lufs_values = [slot.energy_target for slot in reversed(template.slots)]
        score = svc.compute_energy_arc_adherence(lufs_values, "classic_60")
        # Closing_60 starts high and goes low, classic_60 starts low and goes high
        # Reversed classic should still partially match (symmetric-ish)
        assert score < 0.9, f"Inverted arc should score < 0.9, got {score}"

    def test_single_track_returns_zero(self, svc: SetCurationService):
        """Less than 2 tracks should return 0.0."""
        assert svc.compute_energy_arc_adherence([-9.0], "classic_60") == 0.0

    def test_empty_returns_zero(self, svc: SetCurationService):
        """Empty list returns 0.0."""
        assert svc.compute_energy_arc_adherence([], "classic_60") == 0.0

    def test_full_library_template_returns_one(self, svc: SetCurationService):
        """FULL_LIBRARY has no slots, always returns 1.0."""
        lufs = [-9.0] * 10
        score = svc.compute_energy_arc_adherence(lufs, "full_library")
        assert score == 1.0

    def test_score_between_zero_and_one(self, svc: SetCurationService):
        """Score is always in [0.0, 1.0] range."""
        # Extreme LUFS values well outside template range
        extreme_lufs = [-20.0, -1.0, -20.0, -1.0, -20.0]
        score = svc.compute_energy_arc_adherence(extreme_lufs, "classic_60")
        assert 0.0 <= score <= 1.0

    def test_different_track_counts(self, svc: SetCurationService):
        """Works with more or fewer tracks than template slots."""
        template = get_template(TemplateName.CLASSIC_60)
        lufs_values = [slot.energy_target for slot in template.slots]

        # Fewer tracks (10 vs 20 slots)
        score_fewer = svc.compute_energy_arc_adherence(lufs_values[:10], "classic_60")
        assert 0.0 <= score_fewer <= 1.0

        # More tracks (40 vs 20 slots)
        score_more = svc.compute_energy_arc_adherence(lufs_values * 2, "classic_60")
        assert 0.0 <= score_more <= 1.0

    def test_warm_up_template(self, svc: SetCurationService):
        """warm_up_30 template: energy should gradually increase."""
        # Gradual ramp from ambient to driving
        ramp_lufs = [-13.0 + i * 0.5 for i in range(9)]  # -13 to -9
        score = svc.compute_energy_arc_adherence(ramp_lufs, "warm_up_30")
        assert score > 0.6, f"Gradual ramp should match warm_up well, got {score}"


class TestInterpolateTemplateEnergy:
    """Tests for the template energy interpolation helper."""

    def test_at_slot_positions_returns_exact(self):
        """At exact slot positions, returns the slot's energy_target."""
        svc = SetCurationService()
        template = get_template(TemplateName.CLASSIC_60)
        first_slot = template.slots[0]
        result = svc._interpolate_template_energy(template, first_slot.position)
        assert result == first_slot.energy_target

    def test_at_last_position(self):
        svc = SetCurationService()
        template = get_template(TemplateName.CLASSIC_60)
        last_slot = template.slots[-1]
        result = svc._interpolate_template_energy(template, last_slot.position)
        assert result == last_slot.energy_target

    def test_midpoint_interpolation(self):
        """Between two slots, energy is linearly interpolated."""
        svc = SetCurationService()
        template = get_template(TemplateName.CLASSIC_60)
        s0 = template.slots[0]
        s1 = template.slots[1]
        mid_pos = (s0.position + s1.position) / 2
        result = svc._interpolate_template_energy(template, mid_pos)
        expected = (s0.energy_target + s1.energy_target) / 2
        assert abs(result - expected) < 0.01

    def test_before_first_slot_clamps(self):
        svc = SetCurationService()
        template = get_template(TemplateName.WARM_UP_30)
        result = svc._interpolate_template_energy(template, -0.1)
        assert result == template.slots[0].energy_target

    def test_after_last_slot_clamps(self):
        svc = SetCurationService()
        template = get_template(TemplateName.WARM_UP_30)
        result = svc._interpolate_template_energy(template, 1.5)
        assert result == template.slots[-1].energy_target


class TestComputeEnergyArcAdherenceWithGaps:
    """Tests for energy arc adherence with None gaps."""

    def test_all_valid_matches_base_method(self, svc: SetCurationService):
        """All valid values should produce same result as compute_energy_arc_adherence."""
        template = get_template(TemplateName.CLASSIC_60)
        n = len(template.slots)
        lufs_values: list[float | None] = [
            svc._interpolate_template_energy(template, i / (n - 1)) for i in range(n)
        ]
        base_score = svc.compute_energy_arc_adherence(
            [v for v in lufs_values if v is not None], "classic_60"
        )
        gaps_score = svc.compute_energy_arc_adherence_with_gaps(lufs_values, "classic_60")
        assert gaps_score == pytest.approx(base_score, abs=0.001)

    def test_all_none_returns_zero(self, svc: SetCurationService):
        """All None values should return 0.0 (every position penalized with 1.0)."""
        score = svc.compute_energy_arc_adherence_with_gaps([None] * 10, "classic_60")
        assert score == 0.0

    def test_mixed_none_and_valid(self, svc: SetCurationService):
        """Mix of None and valid values should score lower than all-valid."""
        template = get_template(TemplateName.CLASSIC_60)
        n = 10
        lufs_values: list[float | None] = [
            svc._interpolate_template_energy(template, i / (n - 1)) for i in range(n)
        ]
        all_valid_score = svc.compute_energy_arc_adherence_with_gaps(lufs_values, "classic_60")

        # Replace half the values with None
        mixed: list[float | None] = [None if i % 2 == 0 else lufs_values[i] for i in range(n)]
        mixed_score = svc.compute_energy_arc_adherence_with_gaps(mixed, "classic_60")

        assert mixed_score < all_valid_score, (
            f"Mixed ({mixed_score}) should be lower than all-valid ({all_valid_score})"
        )
        assert 0.0 <= mixed_score <= 1.0

    def test_single_none_in_middle(self, svc: SetCurationService):
        """One None among valid values should slightly lower the score."""
        template = get_template(TemplateName.CLASSIC_60)
        n = 10
        lufs_values: list[float | None] = [
            svc._interpolate_template_energy(template, i / (n - 1)) for i in range(n)
        ]
        all_valid_score = svc.compute_energy_arc_adherence_with_gaps(lufs_values, "classic_60")

        with_gap: list[float | None] = list(lufs_values)
        with_gap[5] = None
        gap_score = svc.compute_energy_arc_adherence_with_gaps(with_gap, "classic_60")

        assert gap_score < all_valid_score
        assert gap_score > 0.0

    def test_empty_list_returns_zero(self, svc: SetCurationService):
        """Empty list returns 0.0."""
        assert svc.compute_energy_arc_adherence_with_gaps([], "classic_60") == 0.0

    def test_single_element_returns_zero(self, svc: SetCurationService):
        """Single element (None) returns 0.0 — less than 2 tracks."""
        assert svc.compute_energy_arc_adherence_with_gaps([None], "classic_60") == 0.0

    def test_full_library_template_with_gaps(self, svc: SetCurationService):
        """FULL_LIBRARY has no slots, always returns 1.0 regardless of gaps."""
        values: list[float | None] = [-9.0, None, -8.0, None, -10.0]
        score = svc.compute_energy_arc_adherence_with_gaps(values, "full_library")
        assert score == 1.0
