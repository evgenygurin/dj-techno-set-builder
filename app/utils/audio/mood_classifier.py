"""Rule-based mood classification for techno tracks.

Classifies tracks into 15 mood categories using weighted scoring with fuzzy
membership functions. Each subgenre is scored based on multiple audio features,
and the highest-scoring subgenre wins.

Architecture:
  - 15 subgenres ordered by energy intensity (1=lowest, 15=highest)
  - Weighted scoring system using 5-7 features per subgenre
  - Fuzzy membership functions for smooth transitions
  - Confidence scoring based on separation between top scores

Thresholds are calibrated against real data (N=1539 techno tracks):
  BPM 122-149, LUFS -17..-5, hp_ratio 0.66-17.25, centroid 782-5235 Hz,
  onset_rate 3.2-8.3, flux_mean 0.06-0.32, energy_mean 0.06-0.56, etc.

Pure computation -- no DB, no IO, no side effects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

_INTENSITY_MAP: dict[str, int] = {
    "ambient_dub": 1,
    "dub_techno": 2,
    "minimal": 3,
    "detroit": 4,
    "melodic_deep": 5,
    "progressive": 6,
    "hypnotic": 7,
    "driving": 8,
    "tribal": 9,
    "breakbeat": 10,
    "peak_time": 11,
    "acid": 12,
    "raw": 13,
    "industrial": 14,
    "hard_techno": 15,
}


class TrackMood(StrEnum):
    """Techno subgenre categories ordered by energy intensity."""

    AMBIENT_DUB = "ambient_dub"
    DUB_TECHNO = "dub_techno"
    MINIMAL = "minimal"
    DETROIT = "detroit"
    MELODIC_DEEP = "melodic_deep"
    PROGRESSIVE = "progressive"
    HYPNOTIC = "hypnotic"
    DRIVING = "driving"
    TRIBAL = "tribal"
    BREAKBEAT = "breakbeat"
    PEAK_TIME = "peak_time"
    ACID = "acid"
    RAW = "raw"
    INDUSTRIAL = "industrial"
    HARD_TECHNO = "hard_techno"

    @property
    def intensity(self) -> int:
        """Energy intensity level (1=lowest, 15=highest)."""
        return _INTENSITY_MAP[self.value]

    @classmethod
    def energy_order(cls) -> list[TrackMood]:
        """Return moods sorted by increasing energy intensity."""
        return sorted(cls, key=lambda m: m.intensity)


@dataclass(frozen=True, slots=True)
class MoodClassification:
    """Result of mood classification for a single track."""

    mood: TrackMood
    confidence: float  # 0.0-1.0
    features_used: tuple[str, ...]  # which features contributed most


# -- Fuzzy membership functions -----------------------------------------------


def _gaussian(value: float, center: float, width: float) -> float:
    """Gaussian membership function peaked at center.

    Args:
        value: Input value.
        center: Peak of the gaussian.
        width: Standard deviation (controls width).

    Returns:
        Membership value [0.0, 1.0].
    """
    return math.exp(-0.5 * ((value - center) / width) ** 2)


def _ramp_up(value: float, low: float, high: float) -> float:
    """Linear ramp from 0 at low to 1 at high (higher is better).

    Args:
        value: Input value.
        low: Lower threshold (returns 0.0).
        high: Upper threshold (returns 1.0).

    Returns:
        Membership value [0.0, 1.0].
    """
    if value >= high:
        return 1.0
    if value <= low:
        return 0.0
    return (value - low) / (high - low)


def _ramp_down(value: float, low: float, high: float) -> float:
    """Linear ramp from 1 at low to 0 at high (lower is better).

    Args:
        value: Input value.
        low: Lower threshold (returns 1.0).
        high: Upper threshold (returns 0.0).

    Returns:
        Membership value [0.0, 1.0].
    """
    return 1.0 - _ramp_up(value, low, high)


# -- Subgenre scoring functions -----------------------------------------------
# All thresholds calibrated against real data percentiles (N=1539).
#
# Key percentiles for reference:
#   BPM:      P10=125.9  P25=126  P50=128  P75=129.8  P90=131.9
#   LUFS:     P10=-9.8   P25=-9.7 P50=-8.9 P75=-8.1   P90=-7.4
#   kick:     P10=0.57   P25=0.62 P50=0.84 P75=1.0    P90=1.0
#   hp_ratio: P10=1.51   P25=1.59 P50=1.95 P75=2.38   P90=2.85
#   centroid: P10=2181   P25=2278 P50=2616 P75=2985   P90=3390
#   onset:    P10=4.63   P25=4.77 P50=5.34 P75=5.99   P90=6.64
#   flux_m:   P10=0.154  P25=0.160 P50=0.185 P75=0.211 P90=0.235
#   flux_s:   P10=0.108  P25=0.111 P50=0.124 P75=0.136 P90=0.149
#   e_std:    P10=0.129  P25=0.134 P50=0.150 P75=0.167 P90=0.181
#   e_mean:   P10=0.151  P25=0.161 P50=0.201 P75=0.252 P90=0.303
#   lra:      P10=3.6    P25=4.0  P50=5.7  P75=7.7    P90=9.2
#   crest:    P10=9.0    P25=9.2  P50=9.9  P75=10.7   P90=11.5
#   flatness: P10=0.034  P25=0.037 P50=0.049 P75=0.066 P90=0.090
#
# Features with NO discrimination (removed from scoring):
#   pulse_clarity: 0.81-1.0, mostly 1.0 -- zero variance
#   contrast_mean_db: ~-0.7 always -- zero variance
#   energy_slope_mean: +/-0.00001 -- zero variance
#   sub_energy: P25=0.93 -- nearly all tracks saturated at 1.0
#   chroma_entropy: P10=0.96 -- extremely narrow range (0.83-1.0)


def _score_ambient_dub(
    bpm: float,
    lufs_i: float,
    centroid_mean_hz: float,
    onset_rate: float,
    lra_lu: float,
    energy_mean: float,
    hp_ratio: float = 2.0,
) -> float:
    """Ambient Dub: slow, quiet, deep, spacious, wide dynamics.

    Research: 110-125 BPM, heavy reverb/delay, dark timbre, harmonic pads.
    Discriminators: slowest BPM, quietest, lowest centroid, high LRA.
    Added hp_ratio: ambient dub is harmonic (pads > percussion).
    """
    score = 0.0
    score += 0.20 * _gaussian(bpm, 123.0, 4.0)  # wider: 119-127 BPM
    score += 0.20 * _ramp_down(lufs_i, -11.0, -9.0)  # quieter than P25
    score += 0.20 * _ramp_down(centroid_mean_hz, 1500.0, 2300.0)  # dark
    score += 0.15 * _ramp_down(onset_rate, 4.0, 5.5)  # sparse
    score += 0.10 * _ramp_up(lra_lu, 5.0, 9.0)  # spacious dynamics
    score += 0.10 * _ramp_up(hp_ratio, 2.0, 3.5)  # harmonic pads
    score += 0.05 * _ramp_down(energy_mean, 0.12, 0.20)  # low energy
    return score


def _score_dub_techno(
    bpm: float,
    lufs_i: float,
    lra_lu: float,
    centroid_mean_hz: float,
    onset_rate: float,
    hp_ratio: float,
) -> float:
    """Dub Techno: echo-laden, deep, wide dynamics from reverb tails.

    Research: 118-128 BPM, extensive delay/reverb, dark timbre.
    Key discriminator: very high LRA (>P75=7.7, ideally >9) from echo decay.
    """
    score = 0.0
    score += 0.15 * _gaussian(bpm, 124.0, 3.0)  # below median
    score += 0.15 * _ramp_down(lufs_i, -11.0, -9.0)  # quieter
    score += 0.30 * _ramp_up(lra_lu, 7.0, 12.0)  # KEY: wide dynamics
    score += 0.15 * _ramp_down(centroid_mean_hz, 1800.0, 2400.0)  # dark
    score += 0.15 * _ramp_down(onset_rate, 4.0, 5.5)  # smooth
    score += 0.10 * _ramp_up(hp_ratio, 1.5, 2.5)  # some harmonic
    return score


def _score_minimal(
    bpm: float,
    onset_rate: float,
    energy_std: float,
    flux_mean: float,
    kick_prominence: float,
    lufs_i: float,
) -> float:
    """Minimal Techno: sparse, stable, restrained, subtle variations.

    Research: 120-128 BPM, stripped-back arrangements, tight grid.
    Discriminators: low onset rate, low energy_std, low flux, moderate kick.
    """
    score = 0.0
    score += 0.15 * _gaussian(bpm, 126.0, 3.0)  # ~P25
    score += 0.25 * _ramp_down(onset_rate, 4.2, 5.5)  # sparse < P25
    score += 0.20 * _ramp_down(energy_std, 0.11, 0.15)  # stable < P50
    score += 0.20 * _ramp_down(flux_mean, 0.14, 0.19)  # stable timbre < P50
    score += 0.10 * _gaussian(kick_prominence, 0.65, 0.15)  # moderate kick
    score += 0.10 * _gaussian(lufs_i, -9.5, 1.5)  # moderate loudness
    return score


def _score_detroit(
    bpm: float,
    hp_ratio: float,
    centroid_mean_hz: float,
    lufs_i: float,
    kick_prominence: float,
    energy_mean: float,
) -> float:
    """Detroit Techno: soulful, warm, harmonic, chords/strings.

    Research: 125-135 BPM, emotive melodies, warm pads.
    Key discriminator: high hp_ratio (>P75=2.38) + warm centroid.
    Penalty: too fast (>135) or too quiet or too percussive.
    """
    score = 0.0
    # hp_ratio: P50=1.95, P75=2.38, P90=2.85 -- Detroit needs >P75
    score += 0.25 * _ramp_up(hp_ratio, 2.0, 3.0)  # KEY: harmonic content
    score += 0.20 * _gaussian(bpm, 128.0, 4.0)  # around median
    score += 0.15 * _gaussian(centroid_mean_hz, 2500.0, 500.0)  # warm/clear
    score += 0.10 * _gaussian(lufs_i, -8.5, 1.5)  # moderate
    score += 0.10 * _gaussian(kick_prominence, 0.70, 0.20)  # moderate kick
    score += 0.10 * _ramp_up(energy_mean, 0.18, 0.28)  # decent energy (vs melodic)
    # Additional: centroid >2000 distinguishes from melodic_deep (avg 2064)
    score += 0.10 * _ramp_up(centroid_mean_hz, 2000.0, 2500.0)  # brighter than melodic
    # Penalty: low hp_ratio = not Detroit
    score *= max(0.3, _ramp_up(hp_ratio, 1.5, 2.2))
    return score


def _score_melodic_deep(
    hp_ratio: float,
    centroid_mean_hz: float,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    energy_mean: float,
) -> float:
    """Melodic Deep: harmonic but darker/warmer than Detroit.

    Research: 120-128 BPM, layered synths, deep basslines, warm.
    vs Detroit: lower centroid (darker), slightly slower, quieter.
    """
    score = 0.0
    score += 0.25 * _ramp_up(hp_ratio, 1.8, 2.5)  # harmonic
    score += 0.25 * _ramp_down(centroid_mean_hz, 1800.0, 2500.0)  # KEY: dark
    score += 0.15 * _gaussian(bpm, 125.0, 3.0)  # slower side
    score += 0.10 * _ramp_down(lufs_i, -10.0, -8.5)  # quieter
    score += 0.10 * _gaussian(kick_prominence, 0.60, 0.15)  # moderate
    score += 0.15 * _ramp_down(energy_mean, 0.12, 0.20)  # KEY: restrained (vs detroit avg 0.23)
    return score


def _score_progressive(
    bpm: float,
    energy_std: float,
    flux_mean: float,
    lra_lu: float,
    hp_ratio: float,
) -> float:
    """Progressive Techno: building, evolving, dynamic.

    Research: 125-133 BPM, gradual build-ups, complex arrangements.
    Discriminators: high energy_std (>P75), high flux_mean (>P75), wide LRA.
    """
    score = 0.0
    score += 0.15 * _gaussian(bpm, 128.0, 3.0)  # around median
    # energy_std: P50=0.15, P75=0.167, P90=0.181
    score += 0.30 * _ramp_up(energy_std, 0.16, 0.20)  # KEY: dynamic > P75
    # flux_mean: P50=0.185, P75=0.211, P90=0.235
    score += 0.25 * _ramp_up(flux_mean, 0.20, 0.27)  # evolving > P75
    score += 0.15 * _ramp_up(lra_lu, 6.0, 9.0)  # dynamic range
    score += 0.15 * _gaussian(hp_ratio, 2.0, 0.6)  # some melody
    return score


def _score_hypnotic(
    bpm: float,
    flux_std: float,
    energy_std: float,
    kick_prominence: float,
    flux_mean: float,
) -> float:
    """Hypnotic Techno: repetitive, trance-inducing, very stable.

    Research: 120-130 BPM, steady pulse, minimal variation.
    Discriminators: low flux_std (<P25), low energy_std (<P25).
    Opposite of Progressive (high variability).
    """
    score = 0.0
    score += 0.15 * _gaussian(bpm, 128.0, 4.0)  # 124-132 BPM
    # flux_std: P25=0.111, P50=0.124 -- hypnotic needs <P25
    score += 0.30 * _ramp_down(flux_std, 0.09, 0.12)  # KEY: very stable
    # energy_std: P25=0.134, P50=0.150
    score += 0.25 * _ramp_down(energy_std, 0.10, 0.14)  # consistent
    score += 0.15 * _ramp_up(kick_prominence, 0.70, 0.90)  # solid kick
    score += 0.15 * _ramp_down(flux_mean, 0.14, 0.18)  # stable timbre
    return score


def _score_driving(
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    energy_mean: float,
    onset_rate: float,
    *,
    hp_ratio: float = 2.0,
    flux_std: float = 0.12,
    centroid_mean_hz: float = 2500.0,
    flatness_mean: float = 0.06,
    lra_lu: float = 6.0,
) -> float:
    """Driving Techno: standard 4/4, solid kick, moderate energy.

    Research: 127-135 BPM, four-on-the-floor, mechanical groove.
    The "typical techno" catch-all -- should win for median-range tracks.

    Penalty multiplier prevents driving from absorbing tracks that
    clearly belong to other subgenres (high hp_ratio → Detroit,
    sparse onset → Minimal, stable flux → Hypnotic, bright → Industrial,
    dark centroid → Melodic Deep, high LRA → Dub/Progressive,
    weak kick → Breakbeat).
    """
    score = 0.0
    score += 0.25 * _gaussian(bpm, 129.0, 2.5)  # ~P50-P75
    score += 0.20 * _gaussian(lufs_i, -8.5, 1.0)  # around P50
    score += 0.25 * _ramp_up(kick_prominence, 0.75, 0.95)  # strong kick
    score += 0.15 * _gaussian(energy_mean, 0.22, 0.06)  # ~P50-P75
    score += 0.15 * _gaussian(onset_rate, 5.5, 1.0)  # moderate

    # Anti-catch-all penalties: reduce score when distinctive traits
    # of other subgenres are present.
    penalty = 1.0
    # hp_ratio > P75 (2.38) → likely Detroit/Melodic Deep
    if hp_ratio > 2.5:
        penalty *= 0.7 + 0.3 * _ramp_down(hp_ratio, 2.5, 3.5)
    # Very sparse onset → likely Minimal/Hypnotic
    if onset_rate < 4.5:
        penalty *= 0.7 + 0.3 * _ramp_up(onset_rate, 3.5, 4.5)
    # Very stable flux → likely Hypnotic
    if flux_std < 0.10:
        penalty *= 0.7 + 0.3 * _ramp_up(flux_std, 0.08, 0.10)
    # Very bright centroid → likely Industrial/Acid
    if centroid_mean_hz > 3200:
        penalty *= 0.7 + 0.3 * _ramp_down(centroid_mean_hz, 3200.0, 4000.0)
    # Very noisy → likely Industrial
    if flatness_mean > 0.09:
        penalty *= 0.7 + 0.3 * _ramp_down(flatness_mean, 0.09, 0.14)
    # Dark centroid → likely Melodic Deep/Detroit territory
    if centroid_mean_hz < 2100:
        penalty *= 0.65 + 0.35 * _ramp_up(centroid_mean_hz, 1800.0, 2100.0)
    # High LRA → likely Dub Techno/Progressive (dynamic, not driving)
    if lra_lu > 9.0:
        penalty *= 0.7 + 0.3 * _ramp_down(lra_lu, 9.0, 13.0)
    # Weak kick → likely Breakbeat/Progressive, not driving
    if kick_prominence < 0.4:
        penalty *= 0.6 + 0.4 * _ramp_up(kick_prominence, 0.2, 0.4)
    # High onset → likely Tribal territory
    if onset_rate > 6.3:
        penalty *= 0.75 + 0.25 * _ramp_down(onset_rate, 6.3, 7.5)

    return score * penalty


def _score_tribal(
    bpm: float,
    onset_rate: float,
    kick_prominence: float,
    lufs_i: float,
    hp_ratio: float,
) -> float:
    """Tribal Techno: heavy percussion, organic drums, polyrhythmic.

    Research: 125-135 BPM, dense percussion layers, congas/bongos.
    Key discriminator: very high onset_rate (>P75=6.0, ideally >6.5).
    vs Breakbeat: still has kick (4/4). vs Industrial: lower centroid.
    """
    score = 0.0
    score += 0.15 * _gaussian(bpm, 130.0, 4.0)  # mid-range
    # onset_rate: P75=5.99, P90=6.64 -- tribal needs top quartile
    score += 0.35 * _ramp_up(onset_rate, 5.8, 7.0)  # KEY: busy percussion
    score += 0.15 * _gaussian(kick_prominence, 0.70, 0.15)  # kick present
    score += 0.10 * _gaussian(lufs_i, -8.0, 1.5)  # moderate-loud
    score += 0.10 * _ramp_down(hp_ratio, 1.3, 2.0)  # percussive, not harmonic
    # Penalty: very low onset = not tribal
    score *= max(0.3, _ramp_up(onset_rate, 5.0, 6.0))
    return score


def _score_breakbeat(
    kick_prominence: float,
    onset_rate: float,
    bpm: float,
    energy_mean: float,
    hp_ratio: float,
) -> float:
    """Breakbeat Techno: broken beats, no 4-on-floor, syncopated.

    Research: 128-145 BPM, break patterns, off-grid snares.
    Key discriminator: LOW kick prominence (<P25=0.62) -- no 4/4 kick.
    """
    score = 0.0
    # kick: P10=0.57, P25=0.62 -- breakbeat needs bottom quartile
    score += 0.40 * _ramp_down(kick_prominence, 0.30, 0.55)  # KEY: no 4/4
    score += 0.20 * _ramp_up(onset_rate, 5.0, 6.5)  # busy hi-hats
    score += 0.15 * _gaussian(bpm, 133.0, 6.0)  # wider range
    score += 0.15 * _ramp_up(energy_mean, 0.18, 0.28)  # decent energy
    score += 0.10 * _ramp_down(hp_ratio, 1.2, 2.0)  # percussive
    # Hard penalty: strong kick = not breakbeat
    score *= max(0.2, _ramp_down(kick_prominence, 0.50, 0.75))
    return score


def _score_peak_time(
    kick_prominence: float,
    lufs_i: float,
    energy_mean: float,
    bpm: float,
    onset_rate: float,
) -> float:
    """Peak Time: heavy kick, loud, high energy, dancefloor weapon.

    Research: 128-140 BPM, punchy kick, rolling bass, dense.
    Discriminators: loud (>P75 LUFS), high kick, high energy_mean.
    """
    score = 0.0
    score += 0.25 * _ramp_up(kick_prominence, 0.85, 1.0)  # dominant kick
    # LUFS: P75=-8.1, P90=-7.4 -- peak time is loud
    score += 0.25 * _ramp_up(lufs_i, -8.5, -7.0)  # KEY: loud > P75
    # energy_mean: P75=0.252, P90=0.303
    score += 0.25 * _ramp_up(energy_mean, 0.25, 0.35)  # KEY: high energy
    score += 0.15 * _gaussian(bpm, 132.0, 4.0)  # 128-136 BPM
    score += 0.10 * _ramp_up(onset_rate, 5.5, 6.5)  # active
    return score


def _score_acid(
    bpm: float,
    flux_mean: float,
    flux_std: float,
    centroid_mean_hz: float,
    hp_ratio: float,
) -> float:
    """Acid Techno: TB-303 squelchy basslines, changing timbre, bright.

    Research: 130-145 BPM, filter sweeps, resonant 303.
    Key: high flux (>P90) from filter modulation + bright centroid.
    """
    score = 0.0
    score += 0.15 * _gaussian(bpm, 136.0, 5.0)  # faster, >P90
    # flux_mean: P75=0.211, P90=0.235, max=0.319
    score += 0.30 * _ramp_up(flux_mean, 0.22, 0.30)  # KEY: high flux
    # flux_std: P75=0.136, P90=0.149, max=0.211
    score += 0.20 * _ramp_up(flux_std, 0.14, 0.19)  # high variance
    # centroid: P75=2985, P90=3390
    score += 0.20 * _ramp_up(centroid_mean_hz, 2800.0, 3500.0)  # bright
    score += 0.15 * _ramp_down(hp_ratio, 1.3, 2.0)  # not too harmonic
    return score


def _score_raw(
    kick_prominence: float,
    lufs_i: float,
    crest_factor_db: float,
    bpm: float,
    energy_mean: float,
) -> float:
    """Raw Techno: aggressive, unpolished, compressed, loud.

    Research: 132-142 BPM, distorted kick, heavily compressed.
    Key: low crest factor (<P25=9.2) = heavy compression + very loud.
    """
    score = 0.0
    score += 0.20 * _ramp_up(kick_prominence, 0.80, 1.0)  # dominant kick
    # LUFS: P90=-7.4, max=-5.0
    score += 0.20 * _ramp_up(lufs_i, -7.5, -6.0)  # KEY: very loud
    # crest: P10=9.0, P25=9.2 -- raw has low crest (compressed)
    score += 0.25 * _ramp_down(crest_factor_db, 8.0, 10.0)  # KEY: compressed
    score += 0.15 * _gaussian(bpm, 136.0, 4.0)  # >P90
    score += 0.20 * _ramp_up(energy_mean, 0.25, 0.40)  # high energy
    return score


def _score_industrial(
    centroid_mean_hz: float,
    onset_rate: float,
    flatness_mean: float,
    bpm: float,
    lufs_i: float,
    flux_mean: float = 0.18,
) -> float:
    """Industrial Techno: harsh, noisy, busy, bright, textured.

    Research: 130-145 BPM, distorted, mechanical, metallic, multiband saturation.
    Key: high centroid (>P75=2985) + high flatness (>P75=0.066) + texture (flux).
    Lowered thresholds from P90 to P75 range — industrial is about combined
    harshness, not requiring extreme values on every axis simultaneously.
    """
    score = 0.0
    # centroid: P75=2985, P90=3390 -- industrial starts above P75
    score += 0.25 * _ramp_up(centroid_mean_hz, 2800.0, 3800.0)  # harsh
    score += 0.15 * _ramp_up(onset_rate, 5.5, 6.8)  # busy
    # flatness: P75=0.066, P90=0.090
    score += 0.20 * _ramp_up(flatness_mean, 0.06, 0.10)  # noisy
    score += 0.15 * _gaussian(bpm, 134.0, 6.0)  # wider BPM range 128-140
    score += 0.10 * _ramp_up(lufs_i, -9.0, -7.5)  # moderate-loud
    # flux_mean: high spectral change from distortion/texture
    score += 0.15 * _ramp_up(flux_mean, 0.20, 0.28)  # textured
    return score


def _score_hard_techno(
    bpm: float,
    kick_prominence: float,
    lufs_i: float,
    energy_mean: float,
    onset_rate: float = 5.0,
) -> float:
    """Hard Techno: fast, dominant kick, loud, relentless energy.

    Research: 138-160 BPM, punishing kick, dense percussion, overwhelming.
    Key discriminator: BPM >135 + high energy + strong kick.
    Lowered thresholds: kick 0.80→0.65, LUFS -7.5→-8.5 — hard techno
    doesn't require extreme loudness, it's about speed + impact.
    """
    score = 0.0
    # BPM: P90=131.9, max=149 -- hard techno is the fastest
    score += 0.35 * _ramp_up(bpm, 135.0, 143.0)  # KEY: fast (lowered)
    score += 0.20 * _ramp_up(kick_prominence, 0.65, 0.90)  # strong kick
    score += 0.15 * _ramp_up(lufs_i, -8.5, -6.5)  # loud (relaxed)
    score += 0.15 * _ramp_up(energy_mean, 0.22, 0.35)  # high energy
    score += 0.15 * _ramp_up(onset_rate, 5.5, 7.0)  # dense percussion
    return score


# -- Main classification function ---------------------------------------------


def classify_track(
    *,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    spectral_centroid_mean: float,
    onset_rate: float,
    hp_ratio: float,
    # Extended features — defaults are P50 medians from real data (N=583)
    pulse_clarity: float = 1.0,
    flux_mean: float = 0.18,
    flux_std: float = 0.10,
    energy_std: float = 0.13,
    energy_mean: float = 0.22,
    sub_energy: float = 0.95,
    lra_lu: float = 6.6,
    crest_factor_db: float = 13.3,
    chroma_entropy: float = 0.98,
    contrast_mean_db: float = -0.7,
    flatness_mean: float = 0.06,
    energy_slope_mean: float = 0.0,
) -> MoodClassification:
    """Classify a track into one of 15 techno subgenres using weighted scoring.

    Uses fuzzy membership functions to score each subgenre based on multiple
    audio features. The subgenre with the highest score wins. Confidence is
    computed from the separation between the top two scores.

    Args:
        bpm: Track tempo in BPM.
        lufs_i: Integrated loudness (LUFS).
        kick_prominence: Kick energy at beat positions [0, 1].
        spectral_centroid_mean: Mean spectral centroid (Hz).
        onset_rate: Onsets per second.
        hp_ratio: Harmonic/percussive energy ratio (typically 0.66-17).
        pulse_clarity: Beat grid tightness [0, 1]. Default: 0.65.
        flux_mean: Mean spectral flux [0, 0.32]. Default: 0.50.
        flux_std: Std dev of spectral flux [0, 0.21]. Default: 0.30.
        energy_std: Std dev of energy envelope [0, 0.24]. Default: 0.15.
        energy_mean: Mean energy level [0, 0.56]. Default: 0.65.
        sub_energy: Sub-bass energy (20-60 Hz) [0, 1]. Default: 0.30.
        lra_lu: Loudness range (LU). Default: 8.0.
        crest_factor_db: Peak-to-RMS ratio (dB). Default: 12.0.
        chroma_entropy: Chroma diversity [0, 1]. Default: 0.60.
        contrast_mean_db: Mean spectral contrast (dB). Default: 15.0.
        flatness_mean: Mean spectral flatness [0, 0.16]. Default: 0.35.
        energy_slope_mean: Mean energy slope over time. Default: 0.0.

    Returns:
        MoodClassification with mood, confidence [0, 1], and key features.

    Notes:
        - Extended features have sensible defaults for backward compatibility
        - For best results, provide all features from audio analysis
        - Confidence > 0.7: clear classification
        - Confidence < 0.3: ambiguous, borderline between subgenres
    """
    # Compute scores for all subgenres
    scores: dict[TrackMood, float] = {
        TrackMood.AMBIENT_DUB: _score_ambient_dub(
            bpm,
            lufs_i,
            spectral_centroid_mean,
            onset_rate,
            lra_lu,
            energy_mean,
            hp_ratio,
        ),
        TrackMood.DUB_TECHNO: _score_dub_techno(
            bpm, lufs_i, lra_lu, spectral_centroid_mean, onset_rate, hp_ratio
        ),
        TrackMood.MINIMAL: _score_minimal(
            bpm, onset_rate, energy_std, flux_mean, kick_prominence, lufs_i
        ),
        TrackMood.DETROIT: _score_detroit(
            bpm,
            hp_ratio,
            spectral_centroid_mean,
            lufs_i,
            kick_prominence,
            energy_mean,
        ),
        TrackMood.MELODIC_DEEP: _score_melodic_deep(
            hp_ratio,
            spectral_centroid_mean,
            bpm,
            lufs_i,
            kick_prominence,
            energy_mean,
        ),
        TrackMood.PROGRESSIVE: _score_progressive(bpm, energy_std, flux_mean, lra_lu, hp_ratio),
        TrackMood.HYPNOTIC: _score_hypnotic(bpm, flux_std, energy_std, kick_prominence, flux_mean),
        TrackMood.DRIVING: _score_driving(
            bpm,
            lufs_i,
            kick_prominence,
            energy_mean,
            onset_rate,
            hp_ratio=hp_ratio,
            flux_std=flux_std,
            centroid_mean_hz=spectral_centroid_mean,
            flatness_mean=flatness_mean,
            lra_lu=lra_lu,
        ),
        TrackMood.TRIBAL: _score_tribal(bpm, onset_rate, kick_prominence, lufs_i, hp_ratio),
        TrackMood.BREAKBEAT: _score_breakbeat(
            kick_prominence, onset_rate, bpm, energy_mean, hp_ratio
        ),
        TrackMood.PEAK_TIME: _score_peak_time(
            kick_prominence, lufs_i, energy_mean, bpm, onset_rate
        ),
        TrackMood.ACID: _score_acid(bpm, flux_mean, flux_std, spectral_centroid_mean, hp_ratio),
        TrackMood.RAW: _score_raw(kick_prominence, lufs_i, crest_factor_db, bpm, energy_mean),
        TrackMood.INDUSTRIAL: _score_industrial(
            spectral_centroid_mean,
            onset_rate,
            flatness_mean,
            bpm,
            lufs_i,
            flux_mean,
        ),
        TrackMood.HARD_TECHNO: _score_hard_techno(
            bpm,
            kick_prominence,
            lufs_i,
            energy_mean,
            onset_rate,
        ),
    }

    # Sort by score (highest first)
    sorted_moods = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_mood, best_score = sorted_moods[0]
    second_best_score = sorted_moods[1][1]

    # Confidence: based on score separation and absolute score
    # High when best_score is high AND margin is large
    if best_score < 1e-6:
        confidence = 0.0
    else:
        margin = (best_score - second_best_score) / best_score
        confidence = best_score * margin

    # Identify key features for this classification
    # Use the top 3 features by weight from the winning scorer
    features_used = _get_key_features(best_mood)

    return MoodClassification(
        mood=best_mood,
        confidence=min(1.0, max(0.0, confidence)),
        features_used=features_used,
    )


def _get_key_features(mood: TrackMood) -> tuple[str, ...]:
    """Return the most important features for each subgenre classification."""
    # Map each mood to its key discriminative features (top 3)
    feature_map: dict[TrackMood, tuple[str, ...]] = {
        TrackMood.AMBIENT_DUB: ("bpm", "lufs_i", "centroid_mean_hz"),
        TrackMood.DUB_TECHNO: ("lra_lu", "centroid_mean_hz", "lufs_i"),
        TrackMood.MINIMAL: ("onset_rate", "energy_std", "flux_mean"),
        TrackMood.DETROIT: ("hp_ratio", "bpm", "centroid_mean_hz"),
        TrackMood.MELODIC_DEEP: ("hp_ratio", "centroid_mean_hz", "bpm"),
        TrackMood.PROGRESSIVE: ("energy_std", "flux_mean", "lra_lu"),
        TrackMood.HYPNOTIC: ("flux_std", "energy_std", "kick_prominence"),
        TrackMood.DRIVING: ("bpm", "kick_prominence", "lufs_i"),
        TrackMood.TRIBAL: ("onset_rate", "bpm", "kick_prominence"),
        TrackMood.BREAKBEAT: ("kick_prominence", "onset_rate", "bpm"),
        TrackMood.PEAK_TIME: ("kick_prominence", "lufs_i", "energy_mean"),
        TrackMood.ACID: ("flux_mean", "flux_std", "centroid_mean_hz"),
        TrackMood.RAW: ("crest_factor_db", "lufs_i", "kick_prominence"),
        TrackMood.INDUSTRIAL: ("centroid_mean_hz", "flatness_mean", "onset_rate"),
        TrackMood.HARD_TECHNO: ("bpm", "kick_prominence", "lufs_i"),
    }
    return feature_map.get(mood, ("bpm", "lufs_i", "kick_prominence"))
