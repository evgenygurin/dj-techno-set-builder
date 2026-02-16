"""Tests for section-aware mix point selection (Phase 1C).

Verifies that MixPointService correctly selects transition cue points
based on track section data, following the priority matrix from
professional DJ practice.
"""

from __future__ import annotations

from app.models.enums import SectionType
from app.services.mix_points import (
    MixPoint,
    SectionInfo,
    TransitionMixPoints,
    select_mix_points,
)


def _sec(
    section_id: int,
    section_type: SectionType,
    start_ms: int,
    end_ms: int,
) -> SectionInfo:
    """Shorthand for creating SectionInfo."""
    return SectionInfo(
        section_id=section_id,
        section_type=section_type.value,
        start_ms=start_ms,
        end_ms=end_ms,
    )


# ═══════════════════════════════════════════════════════════
# Priority matrix tests
# ═══════════════════════════════════════════════════════════


class TestMixPointPriority:
    """Verify the priority matrix selects correct section pairs."""

    def test_ideal_outro_to_intro(self) -> None:
        """Outro→Intro is highest priority (1)."""
        out_sections = [
            _sec(1, SectionType.DROP, 0, 120_000),
            _sec(2, SectionType.OUTRO, 240_000, 300_000),
        ]
        in_sections = [
            _sec(3, SectionType.INTRO, 0, 60_000),
            _sec(4, SectionType.DROP, 60_000, 180_000),
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_out.section_id == 2  # outro
        assert result.mix_in.section_id == 3  # intro

    def test_breakdown_to_intro(self) -> None:
        """Breakdown→Intro is priority 2."""
        out_sections = [
            _sec(1, SectionType.DROP, 0, 120_000),
            _sec(2, SectionType.BREAKDOWN, 120_000, 180_000),
        ]
        in_sections = [
            _sec(3, SectionType.INTRO, 0, 60_000),
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_out.section_id == 2  # breakdown
        assert result.mix_in.section_id == 3  # intro

    def test_outro_to_buildup(self) -> None:
        """Outro→Buildup is priority 2."""
        out_sections = [
            _sec(1, SectionType.OUTRO, 240_000, 300_000),
        ]
        in_sections = [
            _sec(2, SectionType.BUILDUP, 30_000, 60_000),
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_out.section_id == 1
        assert result.mix_in.section_id == 2

    def test_breakdown_to_buildup(self) -> None:
        """Breakdown→Buildup is priority 3."""
        out_sections = [
            _sec(1, SectionType.BREAKDOWN, 180_000, 210_000),
        ]
        in_sections = [
            _sec(2, SectionType.BUILDUP, 30_000, 60_000),
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_out.section_id == 1
        assert result.mix_in.section_id == 2

    def test_prefers_higher_priority(self) -> None:
        """When both outro→intro and breakdown→buildup available, pick outro→intro."""
        out_sections = [
            _sec(1, SectionType.BREAKDOWN, 120_000, 150_000),
            _sec(2, SectionType.OUTRO, 240_000, 300_000),
        ]
        in_sections = [
            _sec(3, SectionType.INTRO, 0, 30_000),
            _sec(4, SectionType.BUILDUP, 30_000, 60_000),
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        # Outro→Intro (priority 1) should win over Breakdown→Buildup (priority 3)
        assert result.mix_out.section_id == 2  # outro
        assert result.mix_in.section_id == 3  # intro


class TestMixPointSectionSelection:
    """Verify section selection within a type (last out, first in)."""

    def test_last_outro_selected(self) -> None:
        """When multiple outros exist, pick the one closest to the end."""
        out_sections = [
            _sec(1, SectionType.OUTRO, 100_000, 130_000),  # early outro
            _sec(2, SectionType.OUTRO, 250_000, 300_000),  # late outro (better)
        ]
        in_sections = [
            _sec(3, SectionType.INTRO, 0, 30_000),
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_out.section_id == 2  # should pick the later outro

    def test_first_intro_selected(self) -> None:
        """When multiple intros exist (unusual), pick the earliest one."""
        out_sections = [
            _sec(1, SectionType.OUTRO, 250_000, 300_000),
        ]
        in_sections = [
            _sec(2, SectionType.INTRO, 0, 30_000),  # first (better)
            _sec(3, SectionType.INTRO, 200_000, 230_000),  # later
        ]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_in.section_id == 2  # should pick the earlier intro


class TestMixPointFallback:
    """Verify fallback behaviour when no matching sections found."""

    def test_empty_sections_fallback(self) -> None:
        """No sections at all → use bar-based fallback."""
        result = select_mix_points([], [], 300_000, 300_000)
        assert result.mix_out.section_id is None
        assert result.mix_in.section_id is None
        assert "Fallback" in result.mix_out.reason
        assert "Fallback" in result.mix_in.reason

    def test_no_matching_pair_fallback(self) -> None:
        """Sections exist but no matching pair in priority matrix."""
        out_sections = [
            _sec(1, SectionType.DROP, 60_000, 180_000),
        ]
        in_sections = [
            _sec(2, SectionType.DROP, 60_000, 180_000),
        ]
        # DROP→DROP is not in the priority matrix
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert result.mix_out.section_id is None
        assert result.mix_in.section_id is None

    def test_fallback_position_calculation(self) -> None:
        """Fallback should place mix_out near end of outgoing track."""
        result = select_mix_points([], [], 300_000, 300_000, default_bars=16, bpm=130.0)
        # At 130 BPM, 1 bar = 60000/130*4 = ~1846ms, 16 bars = ~29538ms
        # mix_out = 300000 - 29538 ≈ 270462
        assert result.mix_out.position_ms > 250_000
        assert result.mix_out.position_ms < 300_000
        assert result.mix_in.position_ms == 0

    def test_fallback_respects_bpm(self) -> None:
        """Different BPM should change the fallback overlap length."""
        fast = select_mix_points([], [], 300_000, 300_000, bpm=160.0)
        slow = select_mix_points([], [], 300_000, 300_000, bpm=100.0)
        # Faster BPM → shorter bars → mix_out closer to end
        assert fast.mix_out.position_ms > slow.mix_out.position_ms


class TestMixPointDataclasses:
    """Verify dataclass structure and immutability."""

    def test_mix_point_immutable(self) -> None:
        mp = MixPoint(section_id=1, position_ms=10000, reason="test")
        try:
            mp.position_ms = 20000  # type: ignore[misc]
            msg = "Should be frozen"
            raise AssertionError(msg)
        except AttributeError:
            pass

    def test_transition_mix_points_structure(self) -> None:
        result = select_mix_points([], [], 300_000, 300_000)
        assert isinstance(result, TransitionMixPoints)
        assert isinstance(result.mix_out, MixPoint)
        assert isinstance(result.mix_in, MixPoint)

    def test_reasons_are_descriptive(self) -> None:
        """Mix point reasons should mention the section type or 'Fallback'."""
        out_sections = [_sec(1, SectionType.OUTRO, 240_000, 300_000)]
        in_sections = [_sec(2, SectionType.INTRO, 0, 30_000)]
        result = select_mix_points(out_sections, in_sections, 300_000, 300_000)
        assert "OUTRO" in result.mix_out.reason
        assert "INTRO" in result.mix_in.reason
