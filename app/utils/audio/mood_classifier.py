"""Rule-based mood classification for techno tracks.

Classifies tracks into 6 mood categories using audio features.
Priority order (first match wins):
  HARD_TECHNO -> INDUSTRIAL -> AMBIENT_DUB -> PEAK_TIME -> MELODIC_DEEP -> DRIVING

Pure computation — no DB, no IO, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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
    # Priority 1: HARD_TECHNO — fast + percussive
    if bpm >= 140 and kick_prominence > 0.6:
        conf = min(1.0, (bpm - 140) / 10 * 0.5 + kick_prominence * 0.5)
        return MoodClassification(
            mood=TrackMood.HARD_TECHNO,
            confidence=conf,
            features_used=("bpm", "kick_prominence"),
        )

    # Priority 2: INDUSTRIAL — harsh + busy
    if spectral_centroid_mean > 4000 and onset_rate > 8:
        conf = min(1.0, (spectral_centroid_mean - 4000) / 2000 * 0.5 + (onset_rate - 8) / 4 * 0.5)
        return MoodClassification(
            mood=TrackMood.INDUSTRIAL,
            confidence=conf,
            features_used=("spectral_centroid_mean", "onset_rate"),
        )

    # Priority 3: AMBIENT_DUB — slow + quiet
    if bpm < 128 and lufs_i < -11:
        conf = min(1.0, (128 - bpm) / 10 * 0.5 + (-11 - lufs_i) / 5 * 0.5)
        return MoodClassification(
            mood=TrackMood.AMBIENT_DUB,
            confidence=conf,
            features_used=("bpm", "lufs_i"),
        )

    # Priority 4: PEAK_TIME — heavy kick + loud
    if kick_prominence > 0.6 and lufs_i > -8:
        conf = min(1.0, kick_prominence * 0.5 + (lufs_i + 8) / 4 * 0.5)
        return MoodClassification(
            mood=TrackMood.PEAK_TIME,
            confidence=conf,
            features_used=("kick_prominence", "lufs_i"),
        )

    # Priority 5: MELODIC_DEEP — harmonic + warm
    if hp_ratio > 0.6 and spectral_centroid_mean < 2000:
        conf = min(1.0, hp_ratio * 0.5 + (2000 - spectral_centroid_mean) / 1000 * 0.5)
        return MoodClassification(
            mood=TrackMood.MELODIC_DEEP,
            confidence=conf,
            features_used=("hp_ratio", "spectral_centroid_mean"),
        )

    # Default: DRIVING
    return MoodClassification(
        mood=TrackMood.DRIVING,
        confidence=0.5,
        features_used=(),
    )
