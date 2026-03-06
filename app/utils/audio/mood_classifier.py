"""Rule-based mood classification for techno tracks.

Classifies tracks into 6 mood categories using audio features.
Priority order (first match wins):
  HARD_TECHNO -> INDUSTRIAL -> AMBIENT_DUB -> PEAK_TIME -> MELODIC_DEEP -> DRIVING

Pure computation — no DB, no IO, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

_INTENSITY_MAP: dict[str, int] = {
    "ambient_dub": 1,
    "melodic_deep": 2,
    "driving": 3,
    "peak_time": 4,
    "industrial": 5,
    "hard_techno": 6,
}


class TrackMood(StrEnum):
    """Techno mood categories ordered by energy intensity."""

    AMBIENT_DUB = "ambient_dub"
    MELODIC_DEEP = "melodic_deep"
    DRIVING = "driving"
    PEAK_TIME = "peak_time"
    INDUSTRIAL = "industrial"
    HARD_TECHNO = "hard_techno"

    @property
    def intensity(self) -> int:
        """Energy intensity level (1=lowest, 6=highest)."""
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
    features_used: tuple[str, ...]  # which features triggered the classification


# Declarative mood profiles with thresholds and weights
# Each profile contains the conditions that must ALL be met for classification

ConditionType = Literal["gt", "lt"]  # greater-than or less-than


@dataclass(frozen=True, slots=True)
class Condition:
    """A single condition for mood classification.

    Args:
        feature: Name of the feature to check
        type: "gt" (greater than) or "lt" (less than)
        threshold: The cutoff value
    """

    feature: str
    type: ConditionType
    threshold: float


@dataclass(frozen=True, slots=True)
class ConfidenceWeight:
    """Weight configuration for confidence scoring.

    Args:
        feature: Name of the feature
        weight: Contribution to confidence (0.0-1.0)
        scale: Range to normalize distance for scoring
    """

    feature: str
    weight: float
    scale: float


@dataclass(frozen=True, slots=True)
class MoodProfile:
    """Complete profile for a mood classification.

    Args:
        conditions: All conditions that must be met (AND logic)
        conf_weights: How to compute confidence from feature distances
        priority: Classification priority (1=highest)
    """

    conditions: tuple[Condition, ...]
    conf_weights: tuple[ConfidenceWeight, ...]
    priority: int


# Declarative profiles - all magic numbers extracted here
SUBGENRE_PROFILES: dict[str, MoodProfile] = {
    "hard_techno": MoodProfile(
        conditions=(
            Condition("bpm", "gt", 140.0),
            Condition("kick_prominence", "gt", 0.6),
        ),
        conf_weights=(
            # Reduced BPM weight from 0.5 to 0.15
            ConfidenceWeight("bpm", weight=0.15, scale=10.0),
            ConfidenceWeight("kick_prominence", weight=0.50, scale=0.4),
            # Added hp_ratio for percussive character proxy
            ConfidenceWeight("hp_ratio_inv", weight=0.35, scale=0.6),
        ),
        priority=1,
    ),
    "industrial": MoodProfile(
        conditions=(
            # Lowered from 4000 to 3200 for better harsh techno detection
            Condition("spectral_centroid_mean", "gt", 3200.0),
            Condition("onset_rate", "gt", 8.0),
        ),
        conf_weights=(
            # Lowered centroid weight, raised onset weight
            ConfidenceWeight("spectral_centroid_mean", weight=0.40, scale=1800.0),
            ConfidenceWeight("onset_rate", weight=0.45, scale=4.0),
            # Added hp_ratio for harshness proxy
            ConfidenceWeight("hp_ratio_inv", weight=0.15, scale=0.65),
        ),
        priority=2,
    ),
    "ambient_dub": MoodProfile(
        conditions=(
            Condition("bpm", "lt", 128.0),
            Condition("lufs_i", "lt", -11.0),
        ),
        conf_weights=(
            ConfidenceWeight("bpm_inv", weight=0.50, scale=6.0),
            ConfidenceWeight("lufs_i_inv", weight=0.50, scale=2.0),
        ),
        priority=3,
    ),
    "peak_time": MoodProfile(
        conditions=(
            Condition("kick_prominence", "gt", 0.6),
            Condition("lufs_i", "gt", -8.0),
        ),
        conf_weights=(
            ConfidenceWeight("kick_prominence", weight=0.50, scale=0.2),
            ConfidenceWeight("lufs_i", weight=0.50, scale=1.5),
        ),
        priority=4,
    ),
    "melodic_deep": MoodProfile(
        conditions=(
            Condition("hp_ratio", "gt", 0.6),
            Condition("spectral_centroid_mean", "lt", 2000.0),
        ),
        conf_weights=(
            ConfidenceWeight("hp_ratio", weight=0.50, scale=0.4),
            ConfidenceWeight("spectral_centroid_mean_inv", weight=0.50, scale=200.0),
        ),
        priority=5,
    ),
}


def _compute_confidence(
    features: dict[str, float], conf_weights: tuple[ConfidenceWeight, ...]
) -> float:
    """Compute confidence score from feature values and weights.

    Special handling for "_inv" suffix: inverts the feature value before computing distance.
    E.g., "bpm_inv" means we want low BPM (for ambient_dub).
    E.g., "hp_ratio_inv" means we want low hp_ratio (for percussive/harsh tracks).

    Args:
        features: Dict of feature_name -> value
        conf_weights: Tuple of ConfidenceWeight specs

    Returns:
        Confidence score in [0.0, 1.0]
    """
    total_score = 0.0

    for cw in conf_weights:
        feature_name = cw.feature

        # Handle inverted features (e.g., bpm_inv for "lower is better")
        if feature_name.endswith("_inv"):
            base_name = feature_name[:-4]
            if base_name not in features:
                continue

            # For inverted: we measure distance from threshold
            # This is implementation-specific per feature type
            if base_name == "bpm":
                # bpm_inv: distance below threshold (128)
                distance = 128.0 - features["bpm"]
            elif base_name == "lufs_i":
                # lufs_i_inv: distance below threshold (-11)
                distance = max(0.0, -11.0 - features["lufs_i"])
            elif base_name == "spectral_centroid_mean":
                # spectral_centroid_mean_inv: distance below threshold (2000)
                distance = max(0.0, 2000.0 - features["spectral_centroid_mean"])
            elif base_name == "hp_ratio":
                # hp_ratio_inv: inverse hp_ratio for percussive/harsh detection
                distance = max(0.0, 1.0 - features["hp_ratio"])
            else:
                continue

            distance = max(0.0, distance)
        else:
            # Normal features: distance above their trigger point
            if feature_name not in features:
                continue

            if feature_name == "bpm":
                distance = features["bpm"] - 140.0
            elif feature_name == "kick_prominence":
                distance = features["kick_prominence"] - 0.6
            elif feature_name == "spectral_centroid_mean":
                distance = features["spectral_centroid_mean"] - 3200.0
            elif feature_name == "onset_rate":
                distance = features["onset_rate"] - 8.0
            elif feature_name == "lufs_i":
                distance = features["lufs_i"] - (-8.0)
            elif feature_name == "hp_ratio":
                distance = features["hp_ratio"] - 0.6
            else:
                continue

            distance = max(0.0, distance)

        # Normalize and weight
        normalized = min(1.0, distance / cw.scale)
        total_score += normalized * cw.weight

    return min(1.0, total_score)


def classify_track(
    *,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    spectral_centroid_mean: float,
    onset_rate: float,
    hp_ratio: float,
) -> MoodClassification:
    """Classify a track into one of 6 mood categories.

    Uses priority-based rule matching (first match wins).
    All thresholds and weights are defined in SUBGENRE_PROFILES.

    Args:
        bpm: Track tempo in BPM.
        lufs_i: Integrated loudness (LUFS).
        kick_prominence: Kick energy at beat positions [0, 1].
        spectral_centroid_mean: Mean spectral centroid (Hz).
        onset_rate: Onsets per second.
        hp_ratio: Harmonic/percussive energy ratio [0, 1].

    Returns:
        MoodClassification with mood, confidence, and features_used.
    """
    features = {
        "bpm": bpm,
        "lufs_i": lufs_i,
        "kick_prominence": kick_prominence,
        "spectral_centroid_mean": spectral_centroid_mean,
        "onset_rate": onset_rate,
        "hp_ratio": hp_ratio,
    }

    # Sort profiles by priority
    sorted_profiles = sorted(
        SUBGENRE_PROFILES.items(), key=lambda x: x[1].priority
    )

    # Try each profile in priority order
    for mood_name, profile in sorted_profiles:
        # Check all conditions (AND logic)
        conditions_met = True
        features_used = []

        for cond in profile.conditions:
            if cond.feature not in features:
                conditions_met = False
                break

            value = features[cond.feature]

            condition_failed = (
                (cond.type == "gt"
                and value <= cond.threshold)
                or (cond.type == "lt"
                and value >= cond.threshold)
            )
            if condition_failed:
                conditions_met = False
                break

            features_used.append(cond.feature)

        if conditions_met:
            # Compute confidence
            conf = _compute_confidence(features, profile.conf_weights)

            return MoodClassification(
                mood=TrackMood(mood_name),
                confidence=conf,
                features_used=tuple(features_used),
            )

    # Default: DRIVING
    return MoodClassification(
        mood=TrackMood.DRIVING,
        confidence=0.5,
        features_used=(),
    )
