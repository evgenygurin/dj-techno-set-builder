from __future__ import annotations

import pytest

from app.utils.audio.camelot import (
    camelot_distance,
    is_compatible,
    key_code_to_camelot,
)


class TestKeyCodeToCamelot:
    """Verify mapping matches the DDL seed data."""

    @pytest.mark.parametrize(
        ("key_code", "expected"),
        [
            (0, "5A"),  # Cm
            (1, "8B"),  # C
            (4, "7A"),  # Dm (not 2A!)
            (16, "1A"),  # G#m
            (18, "8A"),  # Am
            (23, "1B"),  # B
        ],
    )
    def test_mapping(self, key_code: int, expected: str) -> None:
        assert key_code_to_camelot(key_code) == expected

    def test_all_24_keys_unique(self) -> None:
        codes = [key_code_to_camelot(i) for i in range(24)]
        assert len(set(codes)) == 24


class TestCamelotDistance:
    def test_same_key_zero(self) -> None:
        assert camelot_distance(0, 0) == 0  # Cm → Cm

    def test_relative_major_minor(self) -> None:
        # Cm (5A) ↔ Eb (5B) — same number, different letter
        assert camelot_distance(0, 7) == 1

    def test_adjacent_same_letter(self) -> None:
        # Cm (5A) ↔ Fm (4A) — adjacent numbers, same letter
        assert camelot_distance(0, 10) == 1

    def test_distant_keys(self) -> None:
        # Cm (5A) ↔ F#m (11A) — 6 steps on the wheel
        assert camelot_distance(0, 12) == 6

    def test_symmetric(self) -> None:
        for a in range(24):
            for b in range(24):
                assert camelot_distance(a, b) == camelot_distance(b, a)


class TestIsCompatible:
    def test_same_key_compatible(self) -> None:
        assert is_compatible(0, 0)

    def test_relative_compatible(self) -> None:
        assert is_compatible(0, 7)  # 5A ↔ 5B

    def test_distant_not_compatible(self) -> None:
        assert not is_compatible(0, 12)  # 5A ↔ 11A
