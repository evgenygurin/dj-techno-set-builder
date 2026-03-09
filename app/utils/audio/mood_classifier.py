"""Rule-based mood classification for techno tracks.

Classifies tracks into 15 mood categories using weighted scoring with fuzzy
membership functions. Each subgenre is scored based on multiple audio features,
and the highest-scoring subgenre wins.

Architecture:
  - 15 subgenres ordered by energy intensity (1=lowest, 15=highest)
  - Config-driven scoring: each subgenre = list of FeatureRules + PenaltyRules
  - Fuzzy membership functions for smooth transitions
  - Confidence scoring based on separation between top scores
  - Adding a 16th subgenre = 1 dict entry in _SCORER_CONFIG

Thresholds are calibrated against real data (N=1539 techno tracks):
  BPM 122-149, LUFS -17..-5, hp_ratio 0.66-17.25, centroid 782-5235 Hz,
  onset_rate 3.2-8.3, flux_mean 0.06-0.32, energy_mean 0.06-0.56, etc.

Pure computation -- no DB, no IO, no side effects.
"""

from __future__ import annotations

import math
from collections.abc import Callable
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
    """Gaussian membership: 1.0 at *center*, decaying with *width* (sigma)."""
    return math.exp(-0.5 * ((value - center) / width) ** 2)


def _ramp_up(value: float, low: float, high: float) -> float:
    """Linear ramp: 0.0 at *low*, 1.0 at *high* (higher is better)."""
    if value >= high:
        return 1.0
    if value <= low:
        return 0.0
    return (value - low) / (high - low)


def _ramp_down(value: float, low: float, high: float) -> float:
    """Linear ramp: 1.0 at *low*, 0.0 at *high* (lower is better)."""
    return 1.0 - _ramp_up(value, low, high)


_FN_MAP: dict[str, Callable[..., float]] = {
    "gaussian": _gaussian,
    "ramp_up": _ramp_up,
    "ramp_down": _ramp_down,
}


# -- Config-driven scorer dataclasses -----------------------------------------


@dataclass(frozen=True, slots=True)
class FeatureRule:
    """One weighted scoring rule: ``weight * fn(features[feature], *params)``."""

    feature: str
    weight: float
    fn: str
    params: tuple[float, float]


@dataclass(frozen=True, slots=True)
class PenaltyRule:
    """Penalty multiplier applied after scoring.

    Unconditional (condition=None): ``score *= max(floor, fn(value, *params))``.
    Conditional: ``if value op threshold: score *= base + (1-base) * fn(...)``.
    """

    feature: str
    fn: str
    params: tuple[float, float]
    floor: float = 0.0
    condition: tuple[str, float] | None = None
    base: float = 0.0


@dataclass(frozen=True, slots=True)
class ScorerConfig:
    """Full config for one subgenre: rules + penalties + key_features."""

    rules: tuple[FeatureRule, ...]
    key_features: tuple[str, ...]
    penalties: tuple[PenaltyRule, ...] = ()


# -- Scorer configuration for all 15 subgenres --------------------------------
# Thresholds calibrated against real data percentiles (N=1539).

_SCORER_CONFIG: dict[TrackMood, ScorerConfig] = {
    # Ambient Dub: slow, quiet, deep, spacious, wide dynamics.
    TrackMood.AMBIENT_DUB: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.20, "gaussian", (123.0, 4.0)),
            FeatureRule("lufs_i", 0.20, "ramp_down", (-11.0, -9.0)),
            FeatureRule("spectral_centroid_mean", 0.20, "ramp_down", (1500.0, 2300.0)),
            FeatureRule("onset_rate", 0.15, "ramp_down", (4.0, 5.5)),
            FeatureRule("lra_lu", 0.10, "ramp_up", (5.0, 9.0)),
            FeatureRule("hp_ratio", 0.10, "ramp_up", (2.0, 3.5)),
            FeatureRule("energy_mean", 0.05, "ramp_down", (0.12, 0.20)),
        ),
        key_features=("bpm", "lufs_i", "spectral_centroid_mean"),
    ),
    # Dub Techno: KEY = very high LRA from echo/reverb decay.
    TrackMood.DUB_TECHNO: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.15, "gaussian", (124.0, 3.0)),
            FeatureRule("lufs_i", 0.15, "ramp_down", (-11.0, -9.0)),
            FeatureRule("lra_lu", 0.30, "ramp_up", (7.0, 12.0)),
            FeatureRule("spectral_centroid_mean", 0.15, "ramp_down", (1800.0, 2400.0)),
            FeatureRule("onset_rate", 0.15, "ramp_down", (4.0, 5.5)),
            FeatureRule("hp_ratio", 0.10, "ramp_up", (1.5, 2.5)),
        ),
        key_features=("lra_lu", "spectral_centroid_mean", "lufs_i"),
    ),
    # Minimal: sparse, stable; low onset, low energy_std, low flux.
    TrackMood.MINIMAL: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.15, "gaussian", (126.0, 3.0)),
            FeatureRule("onset_rate", 0.25, "ramp_down", (4.2, 5.5)),
            FeatureRule("energy_std", 0.20, "ramp_down", (0.11, 0.15)),
            FeatureRule("flux_mean", 0.20, "ramp_down", (0.14, 0.19)),
            FeatureRule("kick_prominence", 0.10, "gaussian", (0.65, 0.15)),
            FeatureRule("lufs_i", 0.10, "gaussian", (-9.5, 1.5)),
        ),
        key_features=("onset_rate", "energy_std", "flux_mean"),
    ),
    # Detroit: KEY = high hp_ratio + warm centroid. Penalty: low hp_ratio.
    TrackMood.DETROIT: ScorerConfig(
        rules=(
            FeatureRule("hp_ratio", 0.25, "ramp_up", (2.0, 3.0)),
            FeatureRule("bpm", 0.20, "gaussian", (128.0, 4.0)),
            FeatureRule("spectral_centroid_mean", 0.15, "gaussian", (2500.0, 500.0)),
            FeatureRule("lufs_i", 0.10, "gaussian", (-8.5, 1.5)),
            FeatureRule("kick_prominence", 0.10, "gaussian", (0.70, 0.20)),
            FeatureRule("energy_mean", 0.10, "ramp_up", (0.18, 0.28)),
            FeatureRule("spectral_centroid_mean", 0.10, "ramp_up", (2000.0, 2500.0)),
        ),
        key_features=("hp_ratio", "bpm", "spectral_centroid_mean"),
        penalties=(PenaltyRule("hp_ratio", "ramp_up", (1.5, 2.2), floor=0.3),),
    ),
    # Melodic Deep: vs Detroit = lower centroid (darker), slower, quieter.
    TrackMood.MELODIC_DEEP: ScorerConfig(
        rules=(
            FeatureRule("hp_ratio", 0.25, "ramp_up", (1.8, 2.5)),
            FeatureRule("spectral_centroid_mean", 0.25, "ramp_down", (1800.0, 2500.0)),
            FeatureRule("bpm", 0.15, "gaussian", (125.0, 3.0)),
            FeatureRule("lufs_i", 0.10, "ramp_down", (-10.0, -8.5)),
            FeatureRule("kick_prominence", 0.10, "gaussian", (0.60, 0.15)),
            FeatureRule("energy_mean", 0.15, "ramp_down", (0.12, 0.20)),
        ),
        key_features=("hp_ratio", "spectral_centroid_mean", "bpm"),
    ),
    # Progressive: high energy_std + flux_mean + LRA (dynamic, evolving).
    TrackMood.PROGRESSIVE: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.15, "gaussian", (128.0, 3.0)),
            FeatureRule("energy_std", 0.30, "ramp_up", (0.16, 0.20)),
            FeatureRule("flux_mean", 0.25, "ramp_up", (0.20, 0.27)),
            FeatureRule("lra_lu", 0.15, "ramp_up", (6.0, 9.0)),
            FeatureRule("hp_ratio", 0.15, "gaussian", (2.0, 0.6)),
        ),
        key_features=("energy_std", "flux_mean", "lra_lu"),
    ),
    # Hypnotic: very low flux_std + energy_std (stable, trance-inducing).
    TrackMood.HYPNOTIC: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.15, "gaussian", (128.0, 4.0)),
            FeatureRule("flux_std", 0.30, "ramp_down", (0.09, 0.12)),
            FeatureRule("energy_std", 0.25, "ramp_down", (0.10, 0.14)),
            FeatureRule("kick_prominence", 0.15, "ramp_up", (0.70, 0.90)),
            FeatureRule("flux_mean", 0.15, "ramp_down", (0.14, 0.18)),
        ),
        key_features=("flux_std", "energy_std", "kick_prominence"),
    ),
    # Driving: "typical techno" catch-all with 9 anti-catch-all penalties.
    TrackMood.DRIVING: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.25, "gaussian", (129.0, 2.5)),
            FeatureRule("lufs_i", 0.20, "gaussian", (-8.5, 1.0)),
            FeatureRule("kick_prominence", 0.25, "ramp_up", (0.75, 0.95)),
            FeatureRule("energy_mean", 0.15, "gaussian", (0.22, 0.06)),
            FeatureRule("onset_rate", 0.15, "gaussian", (5.5, 1.0)),
        ),
        key_features=("bpm", "kick_prominence", "lufs_i"),
        penalties=(
            PenaltyRule("hp_ratio", "ramp_down", (2.5, 3.5), condition=("gt", 2.5), base=0.7),
            PenaltyRule("onset_rate", "ramp_up", (3.5, 4.5), condition=("lt", 4.5), base=0.7),
            PenaltyRule("flux_std", "ramp_up", (0.08, 0.10), condition=("lt", 0.10), base=0.7),
            PenaltyRule(
                "spectral_centroid_mean",
                "ramp_down",
                (3200.0, 4000.0),
                condition=("gt", 3200.0),
                base=0.7,
            ),
            PenaltyRule(
                "flatness_mean", "ramp_down", (0.09, 0.14), condition=("gt", 0.09), base=0.7
            ),
            PenaltyRule(
                "spectral_centroid_mean",
                "ramp_up",
                (1800.0, 2100.0),
                condition=("lt", 2100.0),
                base=0.65,
            ),
            PenaltyRule("lra_lu", "ramp_down", (9.0, 13.0), condition=("gt", 9.0), base=0.7),
            PenaltyRule("kick_prominence", "ramp_up", (0.2, 0.4), condition=("lt", 0.4), base=0.6),
            PenaltyRule("onset_rate", "ramp_down", (6.3, 7.5), condition=("gt", 6.3), base=0.75),
        ),
    ),
    # Tribal: KEY = very high onset_rate. Penalty: low onset.
    TrackMood.TRIBAL: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.15, "gaussian", (130.0, 4.0)),
            FeatureRule("onset_rate", 0.35, "ramp_up", (5.8, 7.0)),
            FeatureRule("kick_prominence", 0.15, "gaussian", (0.70, 0.15)),
            FeatureRule("lufs_i", 0.10, "gaussian", (-8.0, 1.5)),
            FeatureRule("hp_ratio", 0.10, "ramp_down", (1.3, 2.0)),
        ),
        key_features=("onset_rate", "bpm", "kick_prominence"),
        penalties=(PenaltyRule("onset_rate", "ramp_up", (5.0, 6.0), floor=0.3),),
    ),
    # Breakbeat: KEY = LOW kick prominence. Penalty: strong kick.
    TrackMood.BREAKBEAT: ScorerConfig(
        rules=(
            FeatureRule("kick_prominence", 0.40, "ramp_down", (0.30, 0.55)),
            FeatureRule("onset_rate", 0.20, "ramp_up", (5.0, 6.5)),
            FeatureRule("bpm", 0.15, "gaussian", (133.0, 6.0)),
            FeatureRule("energy_mean", 0.15, "ramp_up", (0.18, 0.28)),
            FeatureRule("hp_ratio", 0.10, "ramp_down", (1.2, 2.0)),
        ),
        key_features=("kick_prominence", "onset_rate", "bpm"),
        penalties=(PenaltyRule("kick_prominence", "ramp_down", (0.50, 0.75), floor=0.2),),
    ),
    # Peak Time: loud, dominant kick, high energy.
    TrackMood.PEAK_TIME: ScorerConfig(
        rules=(
            FeatureRule("kick_prominence", 0.25, "ramp_up", (0.85, 1.0)),
            FeatureRule("lufs_i", 0.25, "ramp_up", (-8.5, -7.0)),
            FeatureRule("energy_mean", 0.25, "ramp_up", (0.25, 0.35)),
            FeatureRule("bpm", 0.15, "gaussian", (132.0, 4.0)),
            FeatureRule("onset_rate", 0.10, "ramp_up", (5.5, 6.5)),
        ),
        key_features=("kick_prominence", "lufs_i", "energy_mean"),
    ),
    # Acid: KEY = high flux (303 filter sweeps) + bright centroid.
    TrackMood.ACID: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.15, "gaussian", (136.0, 5.0)),
            FeatureRule("flux_mean", 0.30, "ramp_up", (0.22, 0.30)),
            FeatureRule("flux_std", 0.20, "ramp_up", (0.14, 0.19)),
            FeatureRule("spectral_centroid_mean", 0.20, "ramp_up", (2800.0, 3500.0)),
            FeatureRule("hp_ratio", 0.15, "ramp_down", (1.3, 2.0)),
        ),
        key_features=("flux_mean", "flux_std", "spectral_centroid_mean"),
    ),
    # Raw: KEY = low crest factor (compressed) + very loud.
    TrackMood.RAW: ScorerConfig(
        rules=(
            FeatureRule("kick_prominence", 0.20, "ramp_up", (0.80, 1.0)),
            FeatureRule("lufs_i", 0.20, "ramp_up", (-7.5, -6.0)),
            FeatureRule("crest_factor_db", 0.25, "ramp_down", (8.0, 10.0)),
            FeatureRule("bpm", 0.15, "gaussian", (136.0, 4.0)),
            FeatureRule("energy_mean", 0.20, "ramp_up", (0.25, 0.40)),
        ),
        key_features=("crest_factor_db", "lufs_i", "kick_prominence"),
    ),
    # Industrial: KEY = high centroid + high flatness (harsh, noisy).
    TrackMood.INDUSTRIAL: ScorerConfig(
        rules=(
            FeatureRule("spectral_centroid_mean", 0.25, "ramp_up", (2800.0, 3800.0)),
            FeatureRule("onset_rate", 0.15, "ramp_up", (5.5, 6.8)),
            FeatureRule("flatness_mean", 0.20, "ramp_up", (0.06, 0.10)),
            FeatureRule("bpm", 0.15, "gaussian", (134.0, 6.0)),
            FeatureRule("lufs_i", 0.10, "ramp_up", (-9.0, -7.5)),
            FeatureRule("flux_mean", 0.15, "ramp_up", (0.20, 0.28)),
        ),
        key_features=("spectral_centroid_mean", "flatness_mean", "onset_rate"),
    ),
    # Hard Techno: KEY = BPM >135 + strong kick + high energy.
    TrackMood.HARD_TECHNO: ScorerConfig(
        rules=(
            FeatureRule("bpm", 0.35, "ramp_up", (135.0, 143.0)),
            FeatureRule("kick_prominence", 0.20, "ramp_up", (0.65, 0.90)),
            FeatureRule("lufs_i", 0.15, "ramp_up", (-8.5, -6.5)),
            FeatureRule("energy_mean", 0.15, "ramp_up", (0.22, 0.35)),
            FeatureRule("onset_rate", 0.15, "ramp_up", (5.5, 7.0)),
        ),
        key_features=("bpm", "kick_prominence", "lufs_i"),
    ),
}


# -- Generic scoring engine ---------------------------------------------------


def _score_mood(features: dict[str, float], config: ScorerConfig) -> float:
    """Score a track against one subgenre config. Returns [0.0, ~1.0]."""
    # Weighted sum of feature membership scores
    score = 0.0
    for rule in config.rules:
        value = features[rule.feature]
        fn = _FN_MAP[rule.fn]
        score += rule.weight * fn(value, *rule.params)

    # Apply penalty multipliers
    if config.penalties:
        penalty = 1.0
        for p in config.penalties:
            value = features[p.feature]
            fn = _FN_MAP[p.fn]
            if p.condition is not None:
                # Conditional penalty: only apply when condition is met
                op, threshold = p.condition
                triggered = (op == "gt" and value > threshold) or (
                    op == "lt" and value < threshold
                )
                if triggered:
                    penalty *= p.base + (1.0 - p.base) * fn(value, *p.params)
            else:
                # Unconditional penalty with floor
                penalty *= max(p.floor, fn(value, *p.params))
        score *= penalty

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
    # Extended features -- defaults are P50 medians from real data (N=583)
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
    """Classify a track into one of 15 techno subgenres.

    Scores all subgenres via ``_SCORER_CONFIG`` and returns the highest.
    Extended features have sensible defaults for backward compatibility.
    """
    # Pack all features into a dict for the generic scorer
    features: dict[str, float] = {
        "bpm": bpm,
        "lufs_i": lufs_i,
        "kick_prominence": kick_prominence,
        "spectral_centroid_mean": spectral_centroid_mean,
        "onset_rate": onset_rate,
        "hp_ratio": hp_ratio,
        "pulse_clarity": pulse_clarity,
        "flux_mean": flux_mean,
        "flux_std": flux_std,
        "energy_std": energy_std,
        "energy_mean": energy_mean,
        "sub_energy": sub_energy,
        "lra_lu": lra_lu,
        "crest_factor_db": crest_factor_db,
        "chroma_entropy": chroma_entropy,
        "contrast_mean_db": contrast_mean_db,
        "flatness_mean": flatness_mean,
        "energy_slope_mean": energy_slope_mean,
    }

    # Compute scores for all subgenres via config-driven scorer
    scores: dict[TrackMood, float] = {
        mood: _score_mood(features, config) for mood, config in _SCORER_CONFIG.items()
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

    return MoodClassification(
        mood=best_mood,
        confidence=min(1.0, max(0.0, confidence)),
        features_used=_SCORER_CONFIG[best_mood].key_features,
    )
