"""Rule-based mood classification for techno tracks.

Classifies tracks into 15 mood categories using weighted scoring with fuzzy
membership functions. Each subgenre is scored based on multiple audio features,
and the highest-scoring subgenre wins.

Architecture:
  - 15 subgenres ordered by energy intensity (1=lowest, 15=highest)
  - Weighted scoring system using 5-7 features per subgenre
  - Fuzzy membership functions for smooth transitions
  - Confidence scoring based on separation between top scores

Pure computation — no DB, no IO, no side effects.
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


# ── Fuzzy membership functions ──────────────────────────────────


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


# ── Subgenre scoring functions ──────────────────────────────────


def _score_ambient_dub(
    bpm: float,
    lufs_i: float,
    sub_energy: float,
    onset_rate: float,
    hp_ratio: float,
) -> float:
    """Score for Ambient Dub: slow, quiet, spacious, deep bass."""
    score = 0.0
    score += 0.25 * _gaussian(bpm, 122.0, 4.0)  # 118-126 BPM
    score += 0.25 * _ramp_down(lufs_i, -13.0, -9.0)  # quieter
    score += 0.20 * _ramp_up(sub_energy, 0.25, 0.45)  # deep bass
    score += 0.20 * _ramp_down(onset_rate, 3.0, 6.0)  # smooth, few transients
    score += 0.10 * _ramp_down(hp_ratio, 0.4, 0.7)  # more percussive
    return score


def _score_dub_techno(
    bpm: float,
    lufs_i: float,
    sub_energy: float,
    lra_lu: float,
    centroid_mean_hz: float,
    onset_rate: float,
) -> float:
    """Score for Dub Techno: reverb/delay-heavy, deep bass, darker timbre."""
    score = 0.0
    score += 0.20 * _gaussian(bpm, 124.0, 4.0)  # 120-128 BPM
    score += 0.20 * _ramp_down(lufs_i, -12.0, -8.0)  # quiet to moderate
    score += 0.20 * _ramp_up(sub_energy, 0.30, 0.50)  # strong sub bass
    score += 0.20 * _ramp_up(lra_lu, 6.0, 12.0)  # wide dynamics (echo/decay)
    score += 0.15 * _ramp_down(centroid_mean_hz, 1200.0, 2200.0)  # darker
    score += 0.05 * _ramp_down(onset_rate, 4.0, 7.0)  # smoother
    return score


def _score_minimal(
    bpm: float,
    pulse_clarity: float,
    flux_std: float,
    onset_rate: float,
    energy_std: float,
    lufs_i: float,
) -> float:
    """Score for Minimal Techno: sparse, stable, subtle, tight grid."""
    score = 0.0
    score += 0.20 * _gaussian(bpm, 127.5, 5.0)  # 122-133 BPM
    score += 0.20 * _ramp_up(pulse_clarity, 0.65, 0.85)  # tight grid
    score += 0.20 * _ramp_down(flux_std, 0.20, 0.40)  # stable timbre
    score += 0.20 * _ramp_down(onset_rate, 4.0, 7.0)  # fewer events
    score += 0.15 * _ramp_down(energy_std, 0.10, 0.20)  # consistent energy
    score += 0.05 * _gaussian(lufs_i, -9.5, 2.0)  # moderate loudness
    return score


def _score_detroit(
    bpm: float,
    hp_ratio: float,
    chroma_entropy: float,
    centroid_mean_hz: float,
    lufs_i: float,
) -> float:
    """Score for Detroit Techno: soulful, warm, harmonic, chords/strings."""
    score = 0.0
    score += 0.20 * _gaussian(bpm, 125.0, 5.0)  # 120-130 BPM
    score += 0.30 * _ramp_up(hp_ratio, 0.55, 0.75)  # harmonic content
    score += 0.20 * _ramp_up(chroma_entropy, 0.50, 0.80)  # melodic richness
    score += 0.20 * _gaussian(centroid_mean_hz, 2200.0, 600.0)  # warm but clear
    score += 0.10 * _gaussian(lufs_i, -9.0, 2.0)  # moderate loudness
    return score


def _score_melodic_deep(
    hp_ratio: float,
    centroid_mean_hz: float,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
) -> float:
    """Score for Melodic Deep: harmonic, warm, balanced mix."""
    score = 0.0
    score += 0.30 * _ramp_up(hp_ratio, 0.55, 0.75)  # harmonic
    score += 0.25 * _ramp_down(centroid_mean_hz, 1500.0, 2500.0)  # warm
    score += 0.20 * _gaussian(bpm, 126.0, 5.0)  # 121-131 BPM
    score += 0.15 * _gaussian(lufs_i, -9.5, 2.0)  # moderate
    score += 0.10 * _gaussian(kick_prominence, 0.50, 0.15)  # balanced kick
    return score


def _score_progressive(
    bpm: float,
    energy_slope_mean: float,
    flux_mean: float,
    energy_std: float,
    hp_ratio: float,
) -> float:
    """Score for Progressive Techno: building, evolving, dynamic."""
    score = 0.0
    score += 0.20 * _gaussian(bpm, 127.5, 4.0)  # 123-132 BPM
    score += 0.25 * _ramp_up(energy_slope_mean, -0.05, 0.15)  # building energy
    score += 0.25 * _ramp_up(flux_mean, 0.40, 0.70)  # evolving timbre
    score += 0.20 * _ramp_up(energy_std, 0.15, 0.30)  # dynamic
    score += 0.10 * _gaussian(hp_ratio, 0.55, 0.20)  # some melodic content
    return score


def _score_hypnotic(
    bpm: float,
    flux_std: float,
    pulse_clarity: float,
    energy_std: float,
    kick_prominence: float,
) -> float:
    """Score for Hypnotic Techno: repetitive, trance-inducing, stable."""
    score = 0.0
    score += 0.25 * _gaussian(bpm, 134.0, 4.0)  # 130-138 BPM
    score += 0.25 * _ramp_down(flux_std, 0.15, 0.35)  # very stable
    score += 0.20 * _ramp_up(pulse_clarity, 0.70, 0.90)  # tight grid
    score += 0.20 * _ramp_down(energy_std, 0.08, 0.18)  # consistent
    score += 0.10 * _ramp_up(kick_prominence, 0.55, 0.75)  # solid kick
    return score


def _score_driving(
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    energy_std: float,
) -> float:
    """Score for Driving Techno: standard 4/4, moderate energy, balanced."""
    score = 0.0
    score += 0.30 * _gaussian(bpm, 129.0, 5.0)  # 124-134 BPM
    score += 0.25 * _gaussian(lufs_i, -9.0, 2.0)  # moderate loudness
    score += 0.25 * _gaussian(kick_prominence, 0.58, 0.15)  # solid kick
    score += 0.20 * _gaussian(energy_std, 0.15, 0.10)  # steady
    return score


def _score_tribal(
    bpm: float,
    onset_rate: float,
    contrast_mean_db: float,
    kick_prominence: float,
    lufs_i: float,
) -> float:
    """Score for Tribal Techno: heavy percussion, organic drums, busy."""
    score = 0.0
    score += 0.20 * _gaussian(bpm, 130.0, 5.0)  # 125-135 BPM
    score += 0.30 * _ramp_up(onset_rate, 7.0, 11.0)  # lots of percussion
    score += 0.25 * _ramp_up(contrast_mean_db, 12.0, 18.0)  # percussive transients
    score += 0.15 * _gaussian(kick_prominence, 0.55, 0.15)  # kick present but not dominating
    score += 0.10 * _gaussian(lufs_i, -8.5, 1.5)  # moderate to loud
    return score


def _score_breakbeat(
    kick_prominence: float,
    onset_rate: float,
    pulse_clarity: float,
    contrast_mean_db: float,
    bpm: float,
) -> float:
    """Score for Breakbeat Techno: breaks instead of 4/4, busy, disrupted grid."""
    score = 0.0
    score += 0.35 * _ramp_down(kick_prominence, 0.30, 0.50)  # NO 4-on-floor (key!)
    score += 0.25 * _ramp_up(onset_rate, 8.0, 13.0)  # busy hi-hats/snares
    score += 0.20 * _ramp_down(pulse_clarity, 0.40, 0.65)  # breaks disrupt grid
    score += 0.15 * _ramp_up(contrast_mean_db, 13.0, 19.0)  # punchy
    score += 0.05 * _gaussian(bpm, 132.0, 8.0)  # 124-140 BPM
    return score


def _score_peak_time(
    kick_prominence: float,
    lufs_i: float,
    energy_mean: float,
    bpm: float,
) -> float:
    """Score for Peak Time: heavy kick, loud, high energy, dancefloor focus."""
    score = 0.0
    score += 0.35 * _ramp_up(kick_prominence, 0.60, 0.80)  # dominant kick
    score += 0.30 * _ramp_up(lufs_i, -9.0, -6.5)  # loud
    score += 0.20 * _ramp_up(energy_mean, 0.60, 0.85)  # high energy
    score += 0.15 * _gaussian(bpm, 131.0, 5.0)  # 126-136 BPM
    return score


def _score_acid(
    bpm: float,
    flux_mean: float,
    flux_std: float,
    chroma_entropy: float,
    centroid_mean_hz: float,
) -> float:
    """Score for Acid Techno: TB-303 squelchy basslines, changing timbre, bright."""
    score = 0.0
    score += 0.20 * _gaussian(bpm, 140.0, 5.0)  # 135-145 BPM
    score += 0.30 * _ramp_up(flux_mean, 0.50, 0.80)  # constantly changing (acid)
    score += 0.25 * _ramp_up(flux_std, 0.35, 0.60)  # high variance
    score += 0.15 * _ramp_up(chroma_entropy, 0.55, 0.85)  # melodic but chaotic
    score += 0.10 * _ramp_up(centroid_mean_hz, 2200.0, 3500.0)  # bright, squelchy
    return score


def _score_raw(
    kick_prominence: float,
    lufs_i: float,
    crest_factor_db: float,
    bpm: float,
    energy_mean: float,
) -> float:
    """Score for Raw Techno: aggressive, unpolished, compressed, loud."""
    score = 0.0
    score += 0.30 * _ramp_up(kick_prominence, 0.65, 0.85)  # dominant kick
    score += 0.25 * _ramp_up(lufs_i, -8.0, -5.5)  # very loud
    score += 0.20 * _ramp_down(crest_factor_db, 8.0, 14.0)  # heavily compressed
    score += 0.15 * _gaussian(bpm, 136.0, 4.0)  # 132-140 BPM
    score += 0.10 * _ramp_up(energy_mean, 0.65, 0.90)  # high energy
    return score


def _score_industrial(
    centroid_mean_hz: float,
    onset_rate: float,
    flatness_mean: float,
    bpm: float,
    lufs_i: float,
) -> float:
    """Score for Industrial Techno: harsh, noisy, busy, bright."""
    score = 0.0
    score += 0.30 * _ramp_up(centroid_mean_hz, 3500.0, 5500.0)  # harsh, bright
    score += 0.25 * _ramp_up(onset_rate, 8.0, 12.0)  # busy
    score += 0.20 * _ramp_up(flatness_mean, 0.35, 0.60)  # noisy
    score += 0.15 * _gaussian(bpm, 135.0, 5.0)  # 130-140 BPM
    score += 0.10 * _ramp_up(lufs_i, -9.0, -6.0)  # loud
    return score


def _score_hard_techno(
    bpm: float,
    kick_prominence: float,
    lufs_i: float,
    energy_mean: float,
) -> float:
    """Score for Hard Techno: fast, dominant kick, very loud, relentless."""
    score = 0.0
    score += 0.35 * _ramp_up(bpm, 140.0, 150.0)  # fast (140+ BPM)
    score += 0.30 * _ramp_up(kick_prominence, 0.70, 0.90)  # very dominant kick
    score += 0.20 * _ramp_up(lufs_i, -7.5, -5.0)  # very loud
    score += 0.15 * _ramp_up(energy_mean, 0.70, 0.95)  # relentless energy
    return score


# ── Main classification function ────────────────────────────────


def classify_track(
    *,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    spectral_centroid_mean: float,
    onset_rate: float,
    hp_ratio: float,
    # Extended features for better subgenre discrimination
    pulse_clarity: float = 0.65,
    flux_mean: float = 0.50,
    flux_std: float = 0.30,
    energy_std: float = 0.15,
    energy_mean: float = 0.65,
    sub_energy: float = 0.30,
    lra_lu: float = 8.0,
    crest_factor_db: float = 12.0,
    chroma_entropy: float = 0.60,
    contrast_mean_db: float = 15.0,
    flatness_mean: float = 0.35,
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
        hp_ratio: Harmonic/percussive energy ratio [0, 1].
        pulse_clarity: Beat grid tightness [0, 1]. Default: 0.65.
        flux_mean: Mean spectral flux (timbre change rate) [0, 1]. Default: 0.50.
        flux_std: Std dev of spectral flux [0, 1]. Default: 0.30.
        energy_std: Std dev of energy envelope [0, 1]. Default: 0.15.
        energy_mean: Mean energy level [0, 1]. Default: 0.65.
        sub_energy: Sub-bass energy (20-60 Hz) [0, 1]. Default: 0.30.
        lra_lu: Loudness range (LU). Default: 8.0.
        crest_factor_db: Peak-to-RMS ratio (dB). Default: 12.0.
        chroma_entropy: Chroma diversity [0, 1]. Default: 0.60.
        contrast_mean_db: Mean spectral contrast (dB). Default: 15.0.
        flatness_mean: Mean spectral flatness [0, 1]. Default: 0.35.
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
        TrackMood.AMBIENT_DUB: _score_ambient_dub(bpm, lufs_i, sub_energy, onset_rate, hp_ratio),
        TrackMood.DUB_TECHNO: _score_dub_techno(
            bpm, lufs_i, sub_energy, lra_lu, spectral_centroid_mean, onset_rate
        ),
        TrackMood.MINIMAL: _score_minimal(
            bpm, pulse_clarity, flux_std, onset_rate, energy_std, lufs_i
        ),
        TrackMood.DETROIT: _score_detroit(
            bpm, hp_ratio, chroma_entropy, spectral_centroid_mean, lufs_i
        ),
        TrackMood.MELODIC_DEEP: _score_melodic_deep(
            hp_ratio, spectral_centroid_mean, bpm, lufs_i, kick_prominence
        ),
        TrackMood.PROGRESSIVE: _score_progressive(
            bpm, energy_slope_mean, flux_mean, energy_std, hp_ratio
        ),
        TrackMood.HYPNOTIC: _score_hypnotic(
            bpm, flux_std, pulse_clarity, energy_std, kick_prominence
        ),
        TrackMood.DRIVING: _score_driving(bpm, lufs_i, kick_prominence, energy_std),
        TrackMood.TRIBAL: _score_tribal(
            bpm, onset_rate, contrast_mean_db, kick_prominence, lufs_i
        ),
        TrackMood.BREAKBEAT: _score_breakbeat(
            kick_prominence, onset_rate, pulse_clarity, contrast_mean_db, bpm
        ),
        TrackMood.PEAK_TIME: _score_peak_time(kick_prominence, lufs_i, energy_mean, bpm),
        TrackMood.ACID: _score_acid(
            bpm, flux_mean, flux_std, chroma_entropy, spectral_centroid_mean
        ),
        TrackMood.RAW: _score_raw(kick_prominence, lufs_i, crest_factor_db, bpm, energy_mean),
        TrackMood.INDUSTRIAL: _score_industrial(
            spectral_centroid_mean, onset_rate, flatness_mean, bpm, lufs_i
        ),
        TrackMood.HARD_TECHNO: _score_hard_techno(bpm, kick_prominence, lufs_i, energy_mean),
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
        TrackMood.AMBIENT_DUB: ("bpm", "lufs_i", "sub_energy"),
        TrackMood.DUB_TECHNO: ("sub_energy", "lra_lu", "centroid_mean_hz"),
        TrackMood.MINIMAL: ("pulse_clarity", "flux_std", "onset_rate"),
        TrackMood.DETROIT: ("hp_ratio", "chroma_entropy", "centroid_mean_hz"),
        TrackMood.MELODIC_DEEP: ("hp_ratio", "centroid_mean_hz", "bpm"),
        TrackMood.PROGRESSIVE: ("energy_slope_mean", "flux_mean", "energy_std"),
        TrackMood.HYPNOTIC: ("bpm", "flux_std", "pulse_clarity"),
        TrackMood.DRIVING: ("bpm", "lufs_i", "kick_prominence"),
        TrackMood.TRIBAL: ("onset_rate", "contrast_mean_db", "bpm"),
        TrackMood.BREAKBEAT: ("kick_prominence", "onset_rate", "pulse_clarity"),
        TrackMood.PEAK_TIME: ("kick_prominence", "lufs_i", "energy_mean"),
        TrackMood.ACID: ("flux_mean", "flux_std", "bpm"),
        TrackMood.RAW: ("kick_prominence", "lufs_i", "crest_factor_db"),
        TrackMood.INDUSTRIAL: ("centroid_mean_hz", "onset_rate", "flatness_mean"),
        TrackMood.HARD_TECHNO: ("bpm", "kick_prominence", "lufs_i"),
    }
    return feature_map.get(mood, ("bpm", "lufs_i", "kick_prominence"))
