"""Multi-component transition quality scoring for DJ set generation.

Implements a *filter-then-rank* pipeline:
1. **Hard constraints** — reject transitions that are musically unacceptable
   (BPM diff >10, Camelot distance ≥5, energy delta >6 LUFS).
2. **Multi-component scoring** — weighted composite of BPM, harmonic,
   energy, spectral, and groove sub-scores.

Pure computation — no DB or ORM dependencies.

References:
- Kim et al. (ISMIR 2020): 86.1% of tempo adjustments under 5%
- Kell & Tzanetakis (ISMIR 2013): Timbral similarity is most important
- Zehren et al. (CMJ 2022): Rule-based scoring at 96% quality
- Cliff (CMJ 2000): BPM tolerance ±6% for seamless beatmatching
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
    # Phase 2 enrichment fields (all optional with backward-compat defaults)
    mfcc_vector: list[float] | None = None  # 13 mean MFCC coefficients
    kick_prominence: float = 0.5  # 0-1, kick energy at beat positions
    hnr_db: float = 0.0  # Harmonics-to-noise ratio (dB)
    spectral_slope: float = 0.0  # Spectral slope (dB/octave)


@dataclass(frozen=True, slots=True)
class HardConstraints:
    """Thresholds for the hard-reject filter.

    Transitions violating *any* enabled constraint are rejected (score = 0.0)
    before the multi-component formula runs.  Set a threshold to ``None`` to
    disable that constraint.

    Defaults are calibrated to professional techno DJ practice:
    - BPM: ±6% ≈ 8 BPM at 130; 10 BPM gives headroom for half/double-time.
    - Camelot: distance ≥5 means ≤3/7 shared pitch-classes → audible clash.
    - Energy: >6 LUFS jump is perceptible even with volume riding.
    """

    max_bpm_diff: float | None = 10.0
    max_camelot_distance: int | None = 5  # reject if distance >= this value
    max_energy_delta_lufs: float | None = 6.0


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

    def __init__(
        self,
        camelot_lookup: dict[tuple[int, int], float] | None = None,
        *,
        hard_constraints: HardConstraints | None = None,
    ) -> None:
        """Initialise with a pre-built Camelot lookup table.

        Args:
            camelot_lookup: ``{(from_key, to_key): score}`` built by
                ``CamelotLookupService``.  When *None* a fallback based
                on ``camelot_distance()`` is generated (useful in tests).
            hard_constraints: Thresholds for the pre-filter gate.
                ``None`` → use default thresholds.
        """
        if camelot_lookup is not None:
            self.camelot_lookup = camelot_lookup
        else:
            self.camelot_lookup = self._build_fallback_lookup()

        self.hard_constraints = hard_constraints or HardConstraints()

    # ------------------------------------------------------------------

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

    def check_hard_constraints(self, track_a: TrackFeatures, track_b: TrackFeatures) -> bool:
        """Return ``True`` if the transition should be **rejected**.

        Checks (in order, short-circuiting):
        1. BPM difference (accounting for double/half-time)
        2. Camelot wheel distance
        3. Energy (LUFS) delta

        Returns:
            ``True`` → reject (hard constraint violated).
            ``False`` → proceed to multi-component scoring.
        """
        hc = self.hard_constraints

        # 1. BPM constraint (with double/half-time awareness)
        if hc.max_bpm_diff is not None:
            bpm_diff = effective_bpm_diff(track_a.bpm, track_b.bpm)
            if bpm_diff > hc.max_bpm_diff:
                return True

        # 2. Camelot distance constraint
        if hc.max_camelot_distance is not None:
            from app.utils.audio.camelot import camelot_distance

            dist = camelot_distance(track_a.key_code, track_b.key_code)
            if dist >= hc.max_camelot_distance:
                return True

        # 3. Energy (LUFS) constraint
        if hc.max_energy_delta_lufs is not None:
            energy_diff = abs(track_a.energy_lufs - track_b.energy_lufs)
            if energy_diff > hc.max_energy_delta_lufs:
                return True

        return False

    def score_transition(self, track_a: TrackFeatures, track_b: TrackFeatures) -> float:
        """Compute overall transition quality (filter-then-rank).

        First applies hard constraints — if any are violated the transition
        is rejected immediately with score ``0.0``.  Otherwise computes the
        weighted composite of sub-scores.

        Args:
            track_a: Outgoing track features
            track_b: Incoming track features

        Returns:
            Overall transition score ``[0, 1]``. ``0.0`` means hard-rejected.
        """
        # ── Stage 1: hard-reject gate ──
        if self.check_hard_constraints(track_a, track_b):
            return 0.0

        # ── Stage 2: multi-component scoring ──
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

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fallback_lookup() -> dict[tuple[int, int], float]:
        """Build a Camelot lookup using pitch-class overlap scoring (no DB).

        Uses research-validated scores based on pitch-class set overlap
        between keys on the Camelot wheel (same key=1.0, adjacent=0.9,
        relative major/minor=0.85, tritone=0.05).

        Used in tests or when ``CamelotLookupService`` is unavailable.
        """
        from app.utils.audio.camelot import build_pitch_class_lookup

        return build_pitch_class_lookup()


# ------------------------------------------------------------------
# Free helpers
# ------------------------------------------------------------------


def effective_bpm_diff(bpm_a: float, bpm_b: float) -> float:
    """BPM difference accounting for double- and half-time.

    DJs routinely mix 140 BPM tracks over 70 BPM half-time beats.
    This function returns the smallest absolute difference among
    the normal, double, and half tempo relationships.

    >>> effective_bpm_diff(128.0, 130.0)
    2.0
    >>> effective_bpm_diff(140.0, 70.0)
    0.0
    >>> effective_bpm_diff(128.0, 64.0)
    0.0
    """
    return min(
        abs(bpm_a - bpm_b),
        abs(bpm_a - bpm_b * 2.0),
        abs(bpm_a - bpm_b * 0.5),
    )
