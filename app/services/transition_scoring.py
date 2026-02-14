"""Multi-component transition quality scoring for DJ set generation.

Implements research-backed scoring formula combining:
- BPM matching (Gaussian decay, sigma=8)
- Harmonic compatibility (Camelot modulated by density)
- Energy matching (LUFS sigmoid decay)
- Spectral similarity (centroid + band balance)
- Groove compatibility (onset rate relative difference)

Pure computation — no DB or ORM dependencies.

References:
- Kim et al. (ISMIR 2020): 86.1% of tempo adjustments under 5%
- Kell & Tzanetakis (ISMIR 2013): Timbral similarity is most important
- Zehren et al. (CMJ 2022): Rule-based scoring at 96% quality
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np


@dataclass(frozen=True, slots=True)
class TrackFeatures:
    """Minimal feature set for transition scoring."""

    bpm: float
    energy_lufs: float  # Integrated LUFS (ITU-R BS.1770)
    key_code: int  # 0-23
    harmonic_density: float  # Chroma entropy / log(12), range [0, 1]
    centroid_hz: float  # Spectral centroid mean
    band_ratios: list[float]  # [low, mid, high] energy ratios, sum=1.0
    onset_rate: float  # Onsets per second


class TransitionScoringService:
    """Computes transition quality scores using multi-component formula."""

    # Weights sum to 1.0 (from research synthesis)
    WEIGHTS: ClassVar[dict[str, float]] = {
        "bpm": 0.30,  # BPM matching (25% + buffer)
        "harmonic": 0.25,  # Key compatibility (12% base + density boost)
        "energy": 0.20,  # Energy/loudness matching (15%)
        "spectral": 0.15,  # Timbral similarity proxy (20% in research, here simplified)
        "groove": 0.10,  # Rhythmic texture (8%)
    }

    def __init__(self) -> None:
        self.camelot_lookup: dict[tuple[int, int], float] = {}

    def score_bpm(self, bpm_a: float, bpm_b: float) -> float:
        """Gaussian decay scoring with sigma=8. Handles double/half-time.

        Args:
            bpm_a: BPM of outgoing track
            bpm_b: BPM of incoming track

        Returns:
            Score in [0, 1], where 1.0 = identical BPM
        """
        # Check double-time and half-time compatibility
        diff_normal = abs(bpm_a - bpm_b)
        diff_double = abs(bpm_a - bpm_b * 2.0)
        diff_half = abs(bpm_a - bpm_b * 0.5)

        best_diff = min(diff_normal, diff_double, diff_half)

        # Gaussian decay: exp(-(diff²) / (2*sigma²)), sigma=8
        return float(np.exp(-(best_diff**2) / (2 * 8.0**2)))

    def score_harmonic(self, cam_a: int, cam_b: int, density_a: float, density_b: float) -> float:
        """Camelot score modulated by harmonic density.

        For percussive techno (low density), Camelot matters less.
        For melodic techno (high density), Camelot is critical.

        Args:
            cam_a: Key code of track A (0-23)
            cam_b: Key code of track B (0-23)
            density_a: Harmonic density of A [0, 1]
            density_b: Harmonic density of B [0, 1]

        Returns:
            Modulated harmonic compatibility [0, 1]
        """
        raw_camelot = self.camelot_lookup.get((cam_a, cam_b), 0.5)

        # Average harmonic density
        avg_density = (density_a + density_b) / 2.0

        # Modulation factor: [0.3, 1.0] based on density
        # Low density (0.0) → factor = 0.3 (Camelot weight reduced)
        # High density (1.0) → factor = 1.0 (full Camelot weight)
        factor = 0.3 + 0.7 * avg_density

        # Blend: modulated Camelot + fallback for low-density
        return raw_camelot * factor + 0.8 * (1.0 - factor)

    def score_energy(self, lufs_a: float, lufs_b: float) -> float:
        """Sigmoid decay on LUFS difference.

        LUFS (ITU-R BS.1770) is the gold standard for perceived loudness.

        Args:
            lufs_a: Integrated LUFS of track A (typically -14 to -6 LUFS)
            lufs_b: Integrated LUFS of track B

        Returns:
            Energy match score [0, 1]
        """
        diff = abs(lufs_a - lufs_b)
        # Sigmoid: 1 / (1 + (diff/4)²)
        # At diff=4, score=0.5; at diff=8, score=0.2
        return 1.0 / (1.0 + (diff / 4.0) ** 2)

    def score_spectral(self, track_a: TrackFeatures, track_b: TrackFeatures) -> float:
        """50% centroid similarity + 50% band balance cosine.

        Proxy for timbral similarity (full MFCC cosine is better but not available).

        Args:
            track_a: Features of outgoing track
            track_b: Features of incoming track

        Returns:
            Spectral similarity [0, 1]
        """
        # Centroid component (normalized by 7500 Hz typical range)
        centroid_diff = abs(track_a.centroid_hz - track_b.centroid_hz)
        centroid_score = max(0.0, 1.0 - centroid_diff / 7500.0)

        # Band balance component (cosine similarity)
        vec_a = np.array(track_a.band_ratios)
        vec_b = np.array(track_b.band_ratios)

        # Cosine similarity: (A·B) / (||A|| ||B||)
        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        balance_score = float(dot / (norm_a * norm_b)) if norm_a > 0 and norm_b > 0 else 0.0

        return 0.5 * centroid_score + 0.5 * balance_score

    def score_groove(self, onset_a: float, onset_b: float) -> float:
        """Onset density relative difference.

        Captures rhythmic texture compatibility.

        Args:
            onset_a: Onset rate (onsets/sec) of track A
            onset_b: Onset rate of track B

        Returns:
            Groove compatibility [0, 1]
        """
        if onset_a <= 0 and onset_b <= 0:
            return 1.0

        max_onset = max(onset_a, onset_b, 1e-6)  # Avoid division by zero
        return 1.0 - abs(onset_a - onset_b) / max_onset

    def score_transition(self, track_a: TrackFeatures, track_b: TrackFeatures) -> float:
        """Compute overall transition quality (weighted composite).

        Args:
            track_a: Outgoing track features
            track_b: Incoming track features

        Returns:
            Overall transition score [0, 1]
        """
        bpm_s = self.score_bpm(track_a.bpm, track_b.bpm)
        harm_s = self.score_harmonic(
            track_a.key_code,
            track_b.key_code,
            track_a.harmonic_density,
            track_b.harmonic_density,
        )
        energy_s = self.score_energy(track_a.energy_lufs, track_b.energy_lufs)
        spectral_s = self.score_spectral(track_a, track_b)
        groove_s = self.score_groove(track_a.onset_rate, track_b.onset_rate)

        w = self.WEIGHTS
        return (
            w["bpm"] * bpm_s
            + w["harmonic"] * harm_s
            + w["energy"] * energy_s
            + w["spectral"] * spectral_s
            + w["groove"] * groove_s
        )
