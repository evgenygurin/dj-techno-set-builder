"""Transition quality scoring between two tracks.

Produces a composite score (0-1) from multiple components.
Maps to TransitionCandidate (pre-filter) and Transition (full scoring) models.

Component weights (configurable):
  - BPM distance:  40%  (most critical for techno beatmatching)
  - Key distance:   25%  (harmonic compatibility via Camelot)
  - Energy step:    15%  (dramaturgical fit)
  - Bass conflict:  10%  (spectral overlap in sub/low bands)
  - Groove sim:     10%  (rhythmic pattern compatibility)
"""

from __future__ import annotations

import numpy as np

from app.utils.audio._types import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    SpectralResult,
    TransitionScore,
)
from app.utils.audio.camelot import camelot_distance

# Default weights
_W_BPM = 0.40
_W_KEY = 0.25
_W_ENERGY = 0.15
_W_BASS = 0.10
_W_GROOVE = 0.10

# Normalization constants
_BPM_MAX_PENALTY = 20.0  # BPM difference beyond this = 0 score
_KEY_MAX_DISTANCE = 6  # max Camelot distance
_ENERGY_MAX_STEP = 0.5  # energy delta beyond this = penalty


def _bpm_score(bpm_a: float, bpm_b: float) -> float:
    """0-1 score: 1 = same BPM, 0 = >=20 BPM apart."""
    delta = abs(bpm_a - bpm_b)
    return float(np.clip(1.0 - delta / _BPM_MAX_PENALTY, 0.0, 1.0))


def _key_score(key_a: KeyResult, key_b: KeyResult) -> tuple[float, float]:
    """Returns (score_0_1, weighted_distance).

    Uses Camelot distance weighted by confidence.
    """
    dist = camelot_distance(key_a.key_code, key_b.key_code)
    min_conf = min(key_a.confidence, key_b.confidence)

    # Weighted distance (mirrors SQL key_distance_weighted logic)
    if min_conf < 0.4:
        alpha = min_conf / 0.4
        weighted = (1.0 - alpha) * 1.0 + alpha * dist * min_conf
    else:
        weighted = dist * min_conf

    # Score: inverse of normalized distance
    score = float(np.clip(1.0 - dist / _KEY_MAX_DISTANCE, 0.0, 1.0))
    return score, float(weighted)


def _energy_score(
    energy_a: BandEnergyResult, energy_b: BandEnergyResult
) -> tuple[float, float]:
    """Returns (score_0_1, signed_step).

    Small energy steps are preferred. Step sign: positive = going up.
    """
    # Global energy proxy: weighted mean of bands
    e_a = (
        0.3 * energy_a.sub
        + 0.3 * energy_a.low
        + 0.2 * energy_a.mid
        + 0.2 * energy_a.high
    )
    e_b = (
        0.3 * energy_b.sub
        + 0.3 * energy_b.low
        + 0.2 * energy_b.mid
        + 0.2 * energy_b.high
    )

    step = e_b - e_a
    score = float(np.clip(1.0 - abs(step) / _ENERGY_MAX_STEP, 0.0, 1.0))
    return score, float(step)


def _bass_conflict_score(
    energy_a: BandEnergyResult, energy_b: BandEnergyResult
) -> float:
    """0-1 score: 1 = no bass conflict, 0 = maximum bass clash.

    Both tracks having high sub/low energy = conflict risk during transition.
    """
    sub_overlap = min(energy_a.sub, energy_b.sub)
    low_overlap = min(energy_a.low, energy_b.low)
    conflict = 0.6 * sub_overlap + 0.4 * low_overlap  # 0-1
    return float(np.clip(1.0 - conflict, 0.0, 1.0))


def _spectral_overlap_score(
    spec_a: SpectralResult, spec_b: SpectralResult
) -> float:
    """0-1 score: 1 = similar spectral profile, 0 = very different.

    Based on centroid proximity — tracks with similar spectral centroids
    blend better during transitions.
    """
    centroid_gap = abs(spec_a.centroid_mean_hz - spec_b.centroid_mean_hz)
    # Normalize: 0-5000 Hz gap → 1-0 score
    return float(np.clip(1.0 - centroid_gap / 5000.0, 0.0, 1.0))


def score_transition(
    *,
    bpm_a: BpmResult,
    bpm_b: BpmResult,
    key_a: KeyResult,
    key_b: KeyResult,
    energy_a: BandEnergyResult,
    energy_b: BandEnergyResult,
    spectral_a: SpectralResult,
    spectral_b: SpectralResult,
    groove_sim: float = 0.5,
    weights: dict[str, float] | None = None,
) -> TransitionScore:
    """Compute composite transition quality score.

    Args:
        bpm_a, bpm_b: BPM results for both tracks.
        key_a, key_b: Key detection results for both tracks.
        energy_a, energy_b: Band energy results for both tracks.
        spectral_a, spectral_b: Spectral results for both tracks.
        groove_sim: Pre-computed groove similarity (0-1), default 0.5.
        weights: Optional custom weights dict with keys: bpm, key, energy, bass, groove.

    Returns:
        TransitionScore with composite quality and all component scores.
    """
    w = weights or {}
    w_bpm = w.get("bpm", _W_BPM)
    w_key = w.get("key", _W_KEY)
    w_energy = w.get("energy", _W_ENERGY)
    w_bass = w.get("bass", _W_BASS)
    w_groove = w.get("groove", _W_GROOVE)

    # Compute components
    bpm_sc = _bpm_score(bpm_a.bpm, bpm_b.bpm)
    key_sc, key_dist_weighted = _key_score(key_a, key_b)
    energy_sc, energy_step = _energy_score(energy_a, energy_b)
    bass_sc = _bass_conflict_score(energy_a, energy_b)
    overlap_sc = _spectral_overlap_score(spectral_a, spectral_b)

    # Composite: weighted sum of component scores
    # Bass and spectral overlap combined into "compatibility"
    compatibility = 0.5 * bass_sc + 0.5 * overlap_sc
    groove_clamped = float(np.clip(groove_sim, 0.0, 1.0))

    quality = (
        w_bpm * bpm_sc
        + w_key * key_sc
        + w_energy * energy_sc
        + w_bass * compatibility
        + w_groove * groove_clamped
    )
    quality = float(np.clip(quality, 0.0, 1.0))

    return TransitionScore(
        transition_quality=quality,
        bpm_distance=abs(bpm_a.bpm - bpm_b.bpm),
        key_distance_weighted=key_dist_weighted,
        energy_step=energy_step,
        low_conflict_score=bass_sc,
        overlap_score=overlap_sc,
        groove_similarity=groove_clamped,
    )
