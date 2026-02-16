"""Multi-component transition quality scoring for DJ set generation.

Implements a *filter-then-rank* pipeline:
1. **Hard constraints** — reject transitions that are musically unacceptable
   (BPM diff >10, Camelot distance >=5, energy delta >6 LUFS).
2. **Multi-component scoring** — weighted composite of BPM, harmonic,
   energy, spectral, and groove sub-scores.

Phase 2 enrichments:
- Spectral: MFCC cosine similarity (40%) + centroid (30%) + band balance (30%)
- Harmonic: Camelot modulated by chroma entropy (60%) + HNR (40%)
- Groove: Onset density (70%) + kick prominence (30%)

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
    # Phase 3 fields
    hp_ratio: float = 0.5  # harmonic/percussive energy ratio (0 = percussive, 1 = harmonic)
    last_section: str | None = None  # last section type name (e.g. "outro", "breakdown")
    first_section: str | None = None  # first section type name (e.g. "intro", "drop")


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

    def score_harmonic(
        self,
        cam_a: int,
        cam_b: int,
        density_a: float,
        density_b: float,
        hnr_a: float = 0.0,
        hnr_b: float = 0.0,
    ) -> float:
        """Camelot score modulated by harmonic density and HNR.

        For percussive techno (low density + low HNR), Camelot matters less.
        For melodic techno (high density + high HNR), Camelot is critical.

        Args:
            cam_a: Key code of track A (0-23)
            cam_b: Key code of track B (0-23)
            density_a: Harmonic density of A [0, 1] (from chroma entropy)
            density_b: Harmonic density of B [0, 1]
            hnr_a: Harmonics-to-noise ratio of A (dB, typically 0-30)
            hnr_b: Harmonics-to-noise ratio of B (dB)

        Returns:
            Modulated harmonic compatibility [0, 1]
        """
        raw_camelot = self.camelot_lookup.get((cam_a, cam_b), 0.5)

        # Average harmonic density (from chroma entropy)
        avg_density = (density_a + density_b) / 2.0

        # HNR factor: normalize from typical [0, 20+] dB range to [0, 1]
        avg_hnr = (hnr_a + hnr_b) / 2.0
        hnr_factor = min(max(avg_hnr / 20.0, 0.0), 1.0)

        # Combined: 60% chroma entropy + 40% HNR
        combined = 0.6 * avg_density + 0.4 * hnr_factor

        # Modulation factor: [0.3, 1.0]
        factor = 0.3 + 0.7 * combined

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
        """Timbral similarity: MFCC cosine + centroid + band balance.

        When MFCC vectors are available (Phase 2), uses a 40/30/30 blend
        of MFCC cosine similarity, centroid proximity, and band balance.
        Falls back to 50/50 centroid+balance when MFCC is absent.

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

        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        balance_score = float(dot / (norm_a * norm_b)) if norm_a > 0 and norm_b > 0 else 0.0

        # Phase 2: MFCC cosine similarity when available
        if track_a.mfcc_vector and track_b.mfcc_vector:
            mfcc_a = np.array(track_a.mfcc_vector)
            mfcc_b = np.array(track_b.mfcc_vector)
            mfcc_dot = np.dot(mfcc_a, mfcc_b)
            mfcc_norm_a = np.linalg.norm(mfcc_a)
            mfcc_norm_b = np.linalg.norm(mfcc_b)

            if mfcc_norm_a > 0 and mfcc_norm_b > 0:
                # Cosine similarity [-1, 1] → remap to [0, 1]
                cosine_sim = float(mfcc_dot / (mfcc_norm_a * mfcc_norm_b))
                mfcc_score = (cosine_sim + 1.0) / 2.0
            else:
                mfcc_score = 0.5  # Neutral fallback

            return 0.40 * mfcc_score + 0.30 * centroid_score + 0.30 * balance_score

        # Fallback: Phase 1 formula (no MFCC)
        return 0.50 * centroid_score + 0.50 * balance_score

    def score_groove(
        self,
        onset_a: float,
        onset_b: float,
        kick_a: float = 0.5,
        kick_b: float = 0.5,
    ) -> float:
        """70% onset density + 30% kick prominence similarity.

        Onset density captures rhythmic texture compatibility.
        Kick prominence captures whether both tracks are driven by heavy kicks
        (peak-time) or subtle percussion (minimal).

        Args:
            onset_a: Onset rate (onsets/sec) of track A
            onset_b: Onset rate of track B
            kick_a: Kick prominence of A [0, 1]
            kick_b: Kick prominence of B [0, 1]

        Returns:
            Groove compatibility [0, 1]
        """
        # Onset density component
        if onset_a <= 0 and onset_b <= 0:
            onset_score = 1.0
        else:
            max_onset = max(onset_a, onset_b, 1e-6)
            onset_score = 1.0 - abs(onset_a - onset_b) / max_onset

        # Kick prominence component
        kick_score = 1.0 - abs(kick_a - kick_b)

        return 0.70 * onset_score + 0.30 * kick_score

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
            track_a.hnr_db,
            track_b.hnr_db,
        )
        energy_s = self.score_energy(track_a.energy_lufs, track_b.energy_lufs)
        spectral_s = self.score_spectral(track_a, track_b)
        groove_s = self.score_groove(
            track_a.onset_rate,
            track_b.onset_rate,
            track_a.kick_prominence,
            track_b.kick_prominence,
        )

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
