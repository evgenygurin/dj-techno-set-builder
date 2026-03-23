"""Section-aware mix point selection for DJ set transitions.

Determines optimal cue-in and cue-out timestamps for each transition
based on track section boundaries (intro, outro, breakdown, buildup).

The selection follows a priority matrix derived from professional DJ practice:
1. **outro→intro**: Ideal — both tracks designed for mixing (priority 1).
2. **breakdown→intro** or **outro→buildup**: Good overlaps (priority 2).
3. **outro→drop** or **breakdown→buildup**: Usable (priority 3).
4. **Fallback**: Last 16 bars of outgoing track, first 16 bars of incoming.

Pure computation — no DB or ORM dependencies.

References:
- Schwarz et al. (DAFX 2009): Section-aware transition selection
- Kim et al. (ISMIR 2020): Professional DJs use structural boundaries 94% of the time
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models.enums import SectionType

# ── Types ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SectionInfo:
    """Lightweight section representation (no ORM dependency)."""

    section_id: int
    section_type: int  # SectionType enum value
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class MixPoint:
    """Selected mix point for a single track in a transition.

    Attributes:
        section_id: The section used for the mix point (None if fallback).
        position_ms: The cue timestamp in milliseconds.
        reason: Human-readable explanation of why this point was chosen.
    """

    section_id: int | None
    position_ms: int
    reason: str


@dataclass(frozen=True, slots=True)
class TransitionMixPoints:
    """Mix points for a pair of tracks (outgoing → incoming).

    Attributes:
        mix_out: Where to start fading out the outgoing track.
        mix_in: Where to start fading in the incoming track.
    """

    mix_out: MixPoint
    mix_in: MixPoint


# ── Priority matrix ────────────────────────────────────────
#
# (out_section_type, in_section_type) → priority (lower = better)
# Based on professional DJ practice analysis.

_TRANSITION_PRIORITIES: list[tuple[int, int, int]] = [
    # (out_type, in_type, priority)
    (SectionType.OUTRO, SectionType.INTRO, 1),  # ideal
    (SectionType.BREAKDOWN, SectionType.INTRO, 2),
    (SectionType.OUTRO, SectionType.BUILDUP, 2),
    (SectionType.BREAKDOWN, SectionType.BUILDUP, 3),
    (SectionType.OUTRO, SectionType.DROP, 3),
    (SectionType.OUTRO, SectionType.VERSE, 4),
    (SectionType.BREAKDOWN, SectionType.DROP, 4),
    (SectionType.BREAK, SectionType.INTRO, 4),
    (SectionType.BREAK, SectionType.BUILDUP, 5),
]


# ── Service ────────────────────────────────────────────────


def select_mix_points(
    out_sections: list[SectionInfo],
    in_sections: list[SectionInfo],
    out_duration_ms: int,
    in_duration_ms: int,
    *,
    default_bars: int = 16,
    bpm: float = 130.0,
) -> TransitionMixPoints:
    """Select optimal mix points for a transition between two tracks.

    Args:
        out_sections: Sections of the outgoing track (sorted by start_ms).
        in_sections: Sections of the incoming track (sorted by start_ms).
        out_duration_ms: Total duration of outgoing track.
        in_duration_ms: Total duration of incoming track.
        default_bars: Fallback overlap length in bars.
        bpm: BPM for bar-to-ms conversion (used in fallback).

    Returns:
        TransitionMixPoints with selected out/in cue points.
    """
    # Try section-based pairing
    best_pair = _find_best_section_pair(out_sections, in_sections)
    if best_pair is not None:
        out_sec, in_sec = best_pair
        return TransitionMixPoints(
            mix_out=MixPoint(
                section_id=out_sec.section_id,
                position_ms=out_sec.start_ms,
                reason=f"Section {SectionType(out_sec.section_type).name} start",
            ),
            mix_in=MixPoint(
                section_id=in_sec.section_id,
                position_ms=in_sec.start_ms,
                reason=f"Section {SectionType(in_sec.section_type).name} start",
            ),
        )

    # Fallback: last N bars of outgoing, first N bars of incoming
    bar_ms = int(60_000 / bpm * 4)  # 4 beats per bar
    overlap_ms = default_bars * bar_ms

    mix_out_ms = max(0, out_duration_ms - overlap_ms)
    mix_in_ms = 0  # Start from beginning of incoming track

    return TransitionMixPoints(
        mix_out=MixPoint(
            section_id=None,
            position_ms=mix_out_ms,
            reason=f"Fallback: last {default_bars} bars",
        ),
        mix_in=MixPoint(
            section_id=None,
            position_ms=mix_in_ms,
            reason=f"Fallback: first {default_bars} bars",
        ),
    )


def _find_best_section_pair(
    out_sections: list[SectionInfo],
    in_sections: list[SectionInfo],
) -> tuple[SectionInfo, SectionInfo] | None:
    """Find the best (out_section, in_section) pair by priority matrix.

    Returns None if no matching pair found.
    """
    # Index sections by type
    out_by_type: dict[int, list[SectionInfo]] = {}
    for s in out_sections:
        out_by_type.setdefault(s.section_type, []).append(s)

    in_by_type: dict[int, list[SectionInfo]] = {}
    for s in in_sections:
        in_by_type.setdefault(s.section_type, []).append(s)

    # Walk priority matrix (sorted by priority)
    for out_type, in_type, _priority in _TRANSITION_PRIORITIES:
        out_candidates = out_by_type.get(out_type, [])
        in_candidates = in_by_type.get(in_type, [])
        if out_candidates and in_candidates:
            # Prefer the LAST matching out section (closest to end of track)
            # and the FIRST matching in section (closest to start of track)
            best_out = max(out_candidates, key=lambda s: s.start_ms)
            best_in = min(in_candidates, key=lambda s: s.start_ms)
            return (best_out, best_in)

    return None
