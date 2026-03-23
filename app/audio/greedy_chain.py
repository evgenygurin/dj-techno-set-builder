"""Greedy chain builder for DJ set track selection.

Builds a DJ set by greedily picking the best next track at each step,
considering BPM compatibility, harmonic (Camelot) distance, energy fit,
and adherence to an energy arc.

O(n*k) where n=pool size, k=target track count.
Much faster than GA for large pools (300+ tracks).

Pure computation — no DB or ORM dependencies.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from app.audio.camelot import camelot_distance, key_code_to_camelot
from app.audio.set_generator import EnergyArcType, TrackData


@dataclass(frozen=True, slots=True)
class GreedyChainResult:
    """Result of a greedy chain build."""

    track_ids: list[int]
    scores: list[float]  # compatibility score for each consecutive pair
    avg_score: float
    min_score: float


def _camelot_neighbors(key_code: int) -> set[str]:
    """Return set of Camelot keys at distance 0 or 1 from the given key_code."""
    camelot = key_code_to_camelot(key_code)
    num = int(camelot[:-1])
    letter = camelot[-1]
    neighbors = {camelot}
    # Relative major/minor (same number, different letter)
    neighbors.add(f"{num}{'B' if letter == 'A' else 'A'}")
    # Adjacent on the wheel (same letter, +-1)
    neighbors.add(f"{(num % 12) + 1}{letter}")
    neighbors.add(f"{((num - 2) % 12) + 1}{letter}")
    return neighbors


def _quick_score(a: TrackData, b: TrackData, bpm_tolerance: float) -> float:
    """Fast compatibility score between two tracks.

    Returns 0.0 if BPM or key incompatible. Otherwise returns a weighted
    combination of BPM closeness (0.40), harmonic match (0.35 base),
    and energy similarity (0.25).
    """
    bpm_diff = abs(a.bpm - b.bpm)
    if bpm_diff > bpm_tolerance:
        return 0.0

    bpm_s = max(0.0, 1.0 - (bpm_diff / (bpm_tolerance * 2)) ** 2)

    # Camelot compatibility check (distance <= 1)
    cam_dist = camelot_distance(a.key_code, b.key_code)
    if cam_dist > 1:
        return 0.0

    # Energy similarity based on the 0-1 energy field
    energy_diff = abs(a.energy - b.energy)
    energy_s = max(0.0, 1.0 - energy_diff / 0.5)

    return bpm_s * 0.4 + 0.35 + energy_s * 0.25


# ── Energy arc functions ──────────────────────────────────────
# Each maps (step_index, total_count) -> target_energy in [0, 1].


def _arc_classic(i: int, n: int) -> float:
    """Symmetric bell curve: warm-up -> peak -> cooldown."""
    return 0.15 + 0.85 * (1 - abs(2 * i / max(n - 1, 1) - 1))


def _arc_progressive(i: int, n: int) -> float:
    """Linear rise from 0.2 to 0.9."""
    return 0.2 + 0.7 * (i / max(n - 1, 1))


def _arc_roller(i: int, n: int) -> float:
    """Sustained high energy with gentle sine oscillation."""
    return 0.7 + 0.15 * math.sin(i / max(n - 1, 1) * math.pi * 2)


def _arc_wave(i: int, n: int) -> float:
    """Multiple peaks and troughs."""
    return 0.5 + 0.3 * math.sin(i / max(n - 1, 1) * math.pi * 2)


_ENERGY_ARCS: dict[str, Callable[[int, int], float]] = {
    "classic": _arc_classic,
    "progressive": _arc_progressive,
    "roller": _arc_roller,
    "wave": _arc_wave,
}


def build_greedy_chain(
    tracks: list[TrackData],
    track_count: int = 20,
    energy_arc: EnergyArcType | str = EnergyArcType.CLASSIC,
    bpm_tolerance: float = 4.0,
) -> GreedyChainResult:
    """Build a DJ set by greedily picking the best next track.

    At each step, picks the unused track with the highest combined score
    of transition compatibility (65%) and energy arc fit (35%).

    Falls back to best energy-fit track if no compatible candidate exists.

    Args:
        tracks: Pool of available tracks with audio features.
        track_count: Target number of tracks to select.
        energy_arc: Energy arc shape for the set.
        bpm_tolerance: Maximum BPM difference for compatibility.

    Returns:
        GreedyChainResult with ordered track IDs and transition scores.
    """
    if len(tracks) < 2:
        ids = [t.track_id for t in tracks]
        return GreedyChainResult(track_ids=ids, scores=[], avg_score=0.0, min_score=0.0)

    arc_key = energy_arc.value if isinstance(energy_arc, EnergyArcType) else str(energy_arc)
    arc_fn = _ENERGY_ARCS.get(arc_key, _ENERGY_ARCS["classic"])

    # Compute energy range for arc mapping
    energy_vals = [t.energy for t in tracks]
    energy_lo, energy_hi = min(energy_vals), max(energy_vals)
    energy_range = energy_hi - energy_lo or 1.0

    target_count = min(track_count, len(tracks))

    # Start: pick track closest to arc(0) energy target
    target_energy_0 = energy_lo + arc_fn(0, target_count) * energy_range
    start = min(tracks, key=lambda t: abs(t.energy - target_energy_0))

    used: set[int] = {start.track_id}
    chain: list[TrackData] = [start]

    for step in range(1, target_count):
        current = chain[-1]
        target_energy = energy_lo + arc_fn(step, target_count) * energy_range

        best_track: TrackData | None = None
        best_total = -1.0

        for candidate in tracks:
            if candidate.track_id in used:
                continue
            compat = _quick_score(current, candidate, bpm_tolerance)
            if compat < 0.3:
                continue
            energy_fit = max(
                0.0,
                1.0 - abs(candidate.energy - target_energy) / (energy_range * 0.4),
            )
            total = compat * 0.65 + energy_fit * 0.35
            if total > best_total:
                best_total = total
                best_track = candidate

        if best_track is None:
            # Fallback: any unused track with best energy fit
            for candidate in tracks:
                if candidate.track_id in used:
                    continue
                energy_fit = max(
                    0.0,
                    1.0 - abs(candidate.energy - target_energy) / energy_range,
                )
                if energy_fit > best_total:
                    best_total = energy_fit
                    best_track = candidate

        if best_track:
            chain.append(best_track)
            used.add(best_track.track_id)

    # Score all transitions
    scores = [_quick_score(chain[i], chain[i + 1], bpm_tolerance) for i in range(len(chain) - 1)]
    avg = sum(scores) / len(scores) if scores else 0.0
    mn = min(scores) if scores else 0.0

    return GreedyChainResult(
        track_ids=[t.track_id for t in chain],
        scores=scores,
        avg_score=avg,
        min_score=mn,
    )
