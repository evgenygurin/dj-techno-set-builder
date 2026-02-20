from __future__ import annotations

import pytest

from app.utils.audio.camelot import (
    build_pitch_class_lookup,
    camelot_distance,
    camelot_score,
    camelot_to_key_code,
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


class TestCamelotToKeyCode:
    """Verify reverse mapping: Camelot notation → key_code."""

    @pytest.mark.parametrize(
        ("camelot", "expected"),
        [
            ("5A", 0),   # Cm
            ("8B", 1),   # C
            ("7A", 4),   # Dm
            ("1A", 16),  # G#m
            ("8A", 18),  # Am
            ("1B", 23),  # B
        ],
    )
    def test_reverse_mapping(self, camelot: str, expected: int) -> None:
        assert camelot_to_key_code(camelot) == expected

    def test_all_24_roundtrip(self) -> None:
        """key_code → Camelot → key_code roundtrip for all 24 keys."""
        for kc in range(24):
            cam = key_code_to_camelot(kc)
            assert camelot_to_key_code(cam) == kc

    def test_unknown_returns_none(self) -> None:
        assert camelot_to_key_code("99Z") is None

    def test_case_insensitive(self) -> None:
        assert camelot_to_key_code("5a") == 0
        assert camelot_to_key_code("8b") == 1


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


class TestKeyCodeValidation:
    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="0-23"):
            key_code_to_camelot(-1)

    def test_rejects_too_large(self) -> None:
        with pytest.raises(ValueError, match="0-23"):
            key_code_to_camelot(24)

    def test_distance_rejects_invalid(self) -> None:
        with pytest.raises(ValueError, match="0-23"):
            camelot_distance(-1, 0)
        with pytest.raises(ValueError, match="0-23"):
            camelot_distance(0, 25)


class TestIsCompatible:
    def test_same_key_compatible(self) -> None:
        assert is_compatible(0, 0)

    def test_relative_compatible(self) -> None:
        assert is_compatible(0, 7)  # 5A ↔ 5B

    def test_distant_not_compatible(self) -> None:
        assert not is_compatible(0, 12)  # 5A ↔ 11A


class TestCamelotScore:
    """Verify pitch-class overlap scoring returns research-validated values."""

    def test_same_key_perfect(self) -> None:
        for k in range(24):
            assert camelot_score(k, k) == 1.0

    def test_adjacent_same_ring(self) -> None:
        # Cm (5A) → Fm (4A) — adjacent, same letter
        assert camelot_score(0, 10) == 0.9

    def test_relative_major_minor(self) -> None:
        # Cm (5A) ↔ Eb (5B) — same number, different letter
        assert camelot_score(0, 7) == 0.85

    def test_diagonal_cross_ring(self) -> None:
        # Cm (5A) → F (7B) — ±2 numbers + mode change → num_dist=2
        # Actually, 5A → 7B: num_dist=2, cross-ring → 0.50
        # Let's use 5A → 4B (Eb→Ab): 5→4=1, cross-ring → 0.70
        # Cm (5A, key_code=0) → Ab (4B, key_code=17): num_dist=1, cross
        assert camelot_score(0, 17) == 0.70

    def test_energy_boost(self) -> None:
        # ±2 same ring: Cm (5A) → Gm (6A): num_dist=1 → 0.9
        # Actually ±2: Cm (5A) → Bbm (3A, key_code=20): num_dist=2 → 0.6
        assert camelot_score(0, 20) == 0.6

    def test_tritone_same_ring(self) -> None:
        # Cm (5A) ↔ F#m (11A) — 6 steps, same letter
        assert camelot_score(0, 12) == 0.05

    def test_tritone_cross_ring(self) -> None:
        # Cm (5A) → B (1B, key_code=23): num_dist=|5-1|=4, cross → 0.25
        # F#m (11A) ↔ Eb (5B): num_dist=6, cross → 0.05
        assert camelot_score(12, 7) == 0.05

    def test_symmetry(self) -> None:
        for a in range(24):
            for b in range(24):
                assert camelot_score(a, b) == camelot_score(b, a)

    def test_all_values_in_range(self) -> None:
        for a in range(24):
            for b in range(24):
                s = camelot_score(a, b)
                assert 0.05 <= s <= 1.0, f"score({a},{b})={s}"


class TestBuildPitchClassLookup:
    """Verify the full 24x24 lookup table."""

    def test_completeness(self) -> None:
        lookup = build_pitch_class_lookup()
        assert len(lookup) == 576  # 24 x 24

    def test_diagonal_is_one(self) -> None:
        lookup = build_pitch_class_lookup()
        for k in range(24):
            assert lookup[(k, k)] == 1.0

    def test_matches_camelot_score(self) -> None:
        lookup = build_pitch_class_lookup()
        for i in range(24):
            for j in range(24):
                assert lookup[(i, j)] == camelot_score(i, j)
