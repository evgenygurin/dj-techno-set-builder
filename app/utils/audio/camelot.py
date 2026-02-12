"""Camelot Wheel utility — pure Python, no DB access.

Key encoding: key_code = pitch_class * 2 + mode
  pitch_class: 0=C, 1=C#, 2=D, ... 11=B
  mode: 0=minor (A), 1=major (B)

Camelot notation: number (1-12) + letter (A=minor, B=major).
Mapping matches the seed data in data/schema_v6.sql.
"""

from __future__ import annotations

# key_code → (camelot_number, camelot_letter)
# Derived from DDL seed: INSERT INTO keys ... VALUES ...
_KEY_CODE_TO_CAMELOT: dict[int, tuple[int, str]] = {
    0: (5, "A"),  # Cm
    1: (8, "B"),  # C
    2: (12, "A"),  # C#m
    3: (3, "B"),  # Db
    4: (7, "A"),  # Dm
    5: (10, "B"),  # D
    6: (2, "A"),  # Ebm
    7: (5, "B"),  # Eb
    8: (9, "A"),  # Em
    9: (12, "B"),  # E
    10: (4, "A"),  # Fm
    11: (7, "B"),  # F
    12: (11, "A"),  # F#m
    13: (2, "B"),  # F#
    14: (6, "A"),  # Gm
    15: (9, "B"),  # G
    16: (1, "A"),  # G#m
    17: (4, "B"),  # Ab
    18: (8, "A"),  # Am
    19: (11, "B"),  # A
    20: (3, "A"),  # Bbm
    21: (6, "B"),  # Bb
    22: (10, "A"),  # Bm
    23: (1, "B"),  # B
}


def _validate_key_code(key_code: int) -> None:
    if not 0 <= key_code <= 23:
        msg = f"key_code must be 0-23, got {key_code}"
        raise ValueError(msg)


def key_code_to_camelot(key_code: int) -> str:
    """Convert key_code (0-23) to Camelot notation (e.g. '5A')."""
    _validate_key_code(key_code)
    num, letter = _KEY_CODE_TO_CAMELOT[key_code]
    return f"{num}{letter}"


def camelot_distance(a_key_code: int, b_key_code: int) -> int:
    """Compute Camelot distance between two key_codes.

    Returns 0 for same key, 1 for compatible keys (adjacent on wheel
    or relative major/minor), up to 6 for maximally distant keys.
    """
    _validate_key_code(a_key_code)
    _validate_key_code(b_key_code)

    if a_key_code == b_key_code:
        return 0

    a_num, a_letter = _KEY_CODE_TO_CAMELOT[a_key_code]
    b_num, b_letter = _KEY_CODE_TO_CAMELOT[b_key_code]

    # Circular distance on the 1-12 wheel
    raw = abs(a_num - b_num)
    num_dist = min(raw, 12 - raw)

    if a_letter == b_letter:
        return num_dist

    # Different letter: relative major/minor at same number costs 1
    if num_dist == 0:
        return 1
    return num_dist + 1


def is_compatible(a_key_code: int, b_key_code: int, *, max_distance: int = 1) -> bool:
    """Check if two keys are harmonically compatible (Camelot distance <= max_distance)."""
    return camelot_distance(a_key_code, b_key_code) <= max_distance
