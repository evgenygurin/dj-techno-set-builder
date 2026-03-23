"""Energy arc definitions and utilities for DJ set generation.

Provides predefined energy arc shapes (classic, progressive, roller, wave)
as piecewise-linear breakpoint curves, plus LUFS-to-energy mapping.

Pure computation — no DB or framework dependencies.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from numpy.typing import NDArray


class EnergyArcType(StrEnum):
    """Predefined energy arc shapes for techno sets."""

    CLASSIC = "classic"  # intro → buildup → peak → breakdown → peak2 → outro
    PROGRESSIVE = "progressive"  # slow linear rise to a single peak, then drop
    ROLLER = "roller"  # sustained high energy with minimal valleys
    WAVE = "wave"  # multiple peaks and troughs


def _interpolate_breakpoints(
    n: int, breakpoints: list[tuple[float, float]]
) -> NDArray[np.float64]:
    """Linearly interpolate breakpoints into an array of length *n*.

    Args:
        n: Output array length (>=1).
        breakpoints: List of (position, energy) pairs where
            position in [0, 1] and energy in [0, 1].

    Returns:
        Piecewise-linear energy curve of length *n*, values in [0, 1].
    """
    bp_x = np.array([p for p, _ in breakpoints], dtype=np.float64)
    bp_y = np.array([e for _, e in breakpoints], dtype=np.float64)
    t = np.linspace(0.0, 1.0, n, dtype=np.float64)
    return np.clip(np.interp(t, bp_x, bp_y), 0.0, 1.0)


# ── Breakpoint definitions for each arc type ────────────────
#
# Each list is a sequence of (normalised_position, energy_level)
# tuples modelling a real techno DJ set structure.
#
# Validated against:
#   - Cliff (CMJ 2000): tension/release arcs in DJ mixes
#   - Kim et al. (ISMIR 2020): energy trajectory analysis of 300+ DJ sets
#   - Professional DJ set analysis (Objective 7 of research report)

_CLASSIC_BREAKPOINTS: list[tuple[float, float]] = [
    (0.00, 0.25),
    (0.10, 0.40),
    (0.25, 0.70),
    (0.40, 0.95),
    (0.55, 0.45),
    (0.65, 0.75),
    (0.80, 1.00),
    (0.90, 0.80),
    (1.00, 0.30),
]

_PROGRESSIVE_BREAKPOINTS: list[tuple[float, float]] = [
    (0.00, 0.20),
    (0.20, 0.30),
    (0.40, 0.50),
    (0.60, 0.70),
    (0.80, 1.00),
    (0.90, 0.60),
    (1.00, 0.25),
]

_ROLLER_BREAKPOINTS: list[tuple[float, float]] = [
    (0.00, 0.50),
    (0.10, 0.80),
    (0.30, 0.90),
    (0.50, 0.85),
    (0.70, 0.95),
    (0.90, 0.85),
    (1.00, 0.55),
]

_WAVE_BREAKPOINTS: list[tuple[float, float]] = [
    (0.00, 0.30),
    (0.12, 0.70),
    (0.25, 0.35),
    (0.40, 0.85),
    (0.55, 0.40),
    (0.72, 1.00),
    (0.85, 0.50),
    (1.00, 0.25),
]

_ARC_BREAKPOINTS: dict[EnergyArcType, list[tuple[float, float]]] = {
    EnergyArcType.CLASSIC: _CLASSIC_BREAKPOINTS,
    EnergyArcType.PROGRESSIVE: _PROGRESSIVE_BREAKPOINTS,
    EnergyArcType.ROLLER: _ROLLER_BREAKPOINTS,
    EnergyArcType.WAVE: _WAVE_BREAKPOINTS,
}


def target_energy_curve(n: int, arc_type: EnergyArcType) -> NDArray[np.float64]:
    """Generate a target energy array of length *n* for the given arc type.

    Uses piecewise-linear interpolation between musically-meaningful
    breakpoints.

    Returns values in [0, 1].
    """
    if n <= 1:
        return np.array([0.5], dtype=np.float64)

    breakpoints = _ARC_BREAKPOINTS.get(arc_type)
    if breakpoints is None:  # pragma: no cover
        return np.full(n, 0.5, dtype=np.float64)

    return _interpolate_breakpoints(n, breakpoints)


def lufs_to_energy(lufs: float) -> float:
    """Map LUFS to [0, 1] energy range.

    Techno range: -14 LUFS (ambient) to -6 LUFS (hard).
    """
    return max(0.0, min(1.0, (lufs - (-14.0)) / ((-6.0) - (-14.0))))
