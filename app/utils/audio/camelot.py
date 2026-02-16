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


# ── Pitch-class overlap scoring ─────────────────────────────
#
# Research-validated harmonic compatibility scores based on
# pitch-class set overlap between keys on the Camelot wheel.
#
# Adjacent Camelot keys share 6/7 notes, ±2 share 5/7, etc.
# Tritone (±6) has maximum dissonance with ~1/7 overlap.
#
# Score table:
#   same key             → 1.00  (7/7 overlap)
#   ±1 same ring         → 0.90  (6/7, adjacent Camelot)
#   relative major/minor → 0.85  (6/7, A↔B same number)
#   diagonal ±1 cross    → 0.70  (5/7, adjacent + mode change)
#   ±2 same ring         → 0.60  (5/7, energy boost)
#   ±7 semitone shift    → 0.50  (4/7)
#   ±3 same ring         → 0.40  (4/7)
#   ±4 same ring         → 0.30  (3/7)
#   ±5 same ring         → 0.20  (3/7)
#   ±6 tritone           → 0.05  (1/7, max dissonance)

# Scores indexed by (same_ring, num_distance)
# same_ring=True when letters match; False when they differ.
_PITCH_CLASS_SCORES_SAME_RING: dict[int, float] = {
    0: 1.00,  # same key
    1: 0.90,  # adjacent
    2: 0.60,  # energy boost
    3: 0.40,
    4: 0.30,
    5: 0.20,
    6: 0.05,  # tritone
}

_PITCH_CLASS_SCORES_CROSS_RING: dict[int, float] = {
    0: 0.85,  # relative major/minor (same number, different letter)
    1: 0.70,  # diagonal ±1
    2: 0.50,  # ±7 semitone equivalent
    3: 0.35,
    4: 0.25,
    5: 0.15,
    6: 0.05,  # tritone + mode switch
}


def camelot_score(a_key_code: int, b_key_code: int) -> float:
    """Pitch-class overlap harmonic compatibility score.

    Returns a value in ``[0.05, 1.0]`` based on how many pitch-classes
    the two keys share on the Camelot wheel.

    This is strictly superior to the linear ``1 - dist/6`` formula
    because it reflects actual pitch-class overlap ratios.
    """
    _validate_key_code(a_key_code)
    _validate_key_code(b_key_code)

    if a_key_code == b_key_code:
        return 1.0

    a_num, a_letter = _KEY_CODE_TO_CAMELOT[a_key_code]
    b_num, b_letter = _KEY_CODE_TO_CAMELOT[b_key_code]

    # Circular distance on the 1-12 wheel
    raw = abs(a_num - b_num)
    num_dist = min(raw, 12 - raw)

    if a_letter == b_letter:
        return _PITCH_CLASS_SCORES_SAME_RING.get(num_dist, 0.05)
    return _PITCH_CLASS_SCORES_CROSS_RING.get(num_dist, 0.05)


def build_pitch_class_lookup() -> dict[tuple[int, int], float]:
    """Build full 24x24 Camelot compatibility lookup using pitch-class overlap.

    Returns:
        Dict mapping ``(from_key_code, to_key_code)`` → score ``[0.05, 1.0]``.
    """
    return {(i, j): camelot_score(i, j) for i in range(24) for j in range(24)}
