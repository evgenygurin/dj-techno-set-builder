"""Rule-based mood classification for techno tracks.

Classifies tracks into 9 mood categories using audio features.
Uses declarative mood profiles with scored matching (best score wins).

Pure computation — no DB, no IO, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_INTENSITY_MAP: dict[str, int] = {
    "ambient_dub": 1,
    "dub_techno": 2,
    "melodic_deep": 3,
    "minimal": 4,
    "hypnotic": 5,
    "driving": 6,
    "peak_time": 7,
    "industrial": 8,
    "hard_techno": 9,
}


class TrackMood(StrEnum):
    """Techno mood categories ordered by energy intensity."""

    AMBIENT_DUB = "ambient_dub"
    DUB_TECHNO = "dub_techno"
    MELODIC_DEEP = "melodic_deep"
    MINIMAL = "minimal"
    HYPNOTIC = "hypnotic"
    DRIVING = "driving"
    PEAK_TIME = "peak_time"
    INDUSTRIAL = "industrial"
    HARD_TECHNO = "hard_techno"

    @property
    def intensity(self) -> int:
        """Energy intensity level (1=lowest, 9=highest)."""
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


@dataclass(frozen=True, slots=True)
class _MoodScore:
    """Internal: score for a single mood profile."""

    mood: TrackMood
    score: float
    features: tuple[str, ...]


def _score_hard_techno(
    bpm: float,
    kick_prominence: float,
    **_kwargs: object,
) -> _MoodScore:
    """HARD_TECHNO: fast + percussive."""
    score = 0.0
    features = []

    if bpm >= 140:
        score += min(1.0, (bpm - 140) / 15 * 0.6)  # BPM contribution (140-155 range)
        features.append("bpm")

    if kick_prominence > 0.6:
        score += (kick_prominence - 0.6) / 0.4 * 0.4  # Kick contribution
        features.append("kick_prominence")

    return _MoodScore(TrackMood.HARD_TECHNO, score, tuple(features))


def _score_industrial(
    spectral_centroid_mean: float,
    onset_rate: float,
    **_kwargs: object,
) -> _MoodScore:
    """INDUSTRIAL: harsh + busy."""
    score = 0.0
    features = []

    if spectral_centroid_mean > 4000:
        score += (spectral_centroid_mean - 4000) / 3000 * 0.5  # Centroid contribution
        features.append("spectral_centroid_mean")

    if onset_rate > 8:
        score += (onset_rate - 8) / 6 * 0.5  # Onset contribution
        features.append("onset_rate")

    return _MoodScore(TrackMood.INDUSTRIAL, score, tuple(features))


def _score_ambient_dub(
    bpm: float,
    lufs_i: float,
    onset_rate: float,
    crest_factor_db: float,
    **_kwargs: object,
) -> _MoodScore:
    """AMBIENT_DUB: slow + quiet + sustained (low transients)."""
    score = 0.0
    features = []

    if bpm < 128:
        score += (128 - bpm) / 15 * 0.3  # BPM contribution
        features.append("bpm")

    if lufs_i < -11:
        score += (-11 - lufs_i) / 6 * 0.3  # Loudness contribution
        features.append("lufs_i")

    if onset_rate < 5:
        score += (5 - onset_rate) / 4 * 0.2  # Sparse onsets
        features.append("onset_rate")

    # Low crest factor = sustained energy (ambient characteristic)
    if crest_factor_db < 12:
        score += (12 - crest_factor_db) / 8 * 0.2
        features.append("crest_factor_db")

    return _MoodScore(TrackMood.AMBIENT_DUB, score, tuple(features))


def _score_dub_techno(
    bpm: float,
    onset_rate: float,
    kick_prominence: float,
    crest_factor_db: float,
    lra_lu: float,
    lufs_i: float,
    **_kwargs: object,
) -> _MoodScore:
    """DUB_TECHNO: moderate tempo + rhythmic structure + balanced dynamics + not too loud."""
    score = 0.0
    features = []

    # Dub techno sweet spot: 120-128 BPM (strict range)
    if 120 <= bpm <= 128:
        score += 0.3
        features.append("bpm")
    elif bpm < 120 or bpm > 132:
        return _MoodScore(TrackMood.DUB_TECHNO, 0.0, tuple())  # Hard reject out of range

    # Moderate rhythmic activity (more than ambient, less than driving)
    if 4.5 < onset_rate < 6.5:
        score += 0.25
        features.append("onset_rate")

    # Present but not dominant kick
    if 0.35 < kick_prominence < 0.55:
        score += 0.2
        features.append("kick_prominence")

    # Moderate crest factor = some transients but not harsh
    if 11 < crest_factor_db < 14:
        score += 0.15
        features.append("crest_factor_db")

    # Moderate LRA = controlled dynamics (dub techno characteristic)
    if 6 < lra_lu < 10:
        score += 0.1
        features.append("lra_lu")

    return _MoodScore(TrackMood.DUB_TECHNO, score, tuple(features))


def _score_peak_time(
    kick_prominence: float,
    lufs_i: float,
    bpm: float,
    **_kwargs: object,
) -> _MoodScore:
    """PEAK_TIME: heavy kick + loud + energetic."""
    score = 0.0
    features = []

    if kick_prominence > 0.6:
        score += (kick_prominence - 0.6) / 0.4 * 0.4  # Kick contribution
        features.append("kick_prominence")

    if lufs_i > -8:
        score += (lufs_i + 8) / 4 * 0.3  # Loudness contribution
        features.append("lufs_i")

    # Peak time typically in energetic BPM range
    if 128 <= bpm <= 136:
        score += 0.3
        features.append("bpm")

    return _MoodScore(TrackMood.PEAK_TIME, score, tuple(features))


def _score_melodic_deep(
    hp_ratio: float,
    spectral_centroid_mean: float,
    **_kwargs: object,
) -> _MoodScore:
    """MELODIC_DEEP: harmonic + warm."""
    score = 0.0
    features = []

    if hp_ratio > 0.6:
        score += (hp_ratio - 0.6) / 0.4 * 0.5  # Harmonic contribution
        features.append("hp_ratio")

    if spectral_centroid_mean < 2000:
        score += (2000 - spectral_centroid_mean) / 1200 * 0.5  # Warmth contribution
        features.append("spectral_centroid_mean")

    return _MoodScore(TrackMood.MELODIC_DEEP, score, tuple(features))


def _score_minimal(
    flux_std: float,
    onset_rate: float,
    energy_std: float,
    bpm: float,
    **_kwargs: object,
) -> _MoodScore:
    """MINIMAL: sparse events + low flux + subtle variations."""
    score = 0.0
    features = []

    # Low flux variance = minimal textural changes
    if flux_std < 50:
        score += (50 - flux_std) / 40 * 0.3
        features.append("flux_std")

    # Sparse onsets
    if onset_rate < 5:
        score += (5 - onset_rate) / 4 * 0.3
        features.append("onset_rate")

    # Low energy variance = stable, minimal dynamics
    if energy_std < 0.15:
        score += (0.15 - energy_std) / 0.1 * 0.2
        features.append("energy_std")

    # Minimal works across BPM range but often moderate
    if 122 <= bpm <= 132:
        score += 0.2
        features.append("bpm")

    return _MoodScore(TrackMood.MINIMAL, score, tuple(features))


def _score_hypnotic(
    flux_std: float,
    onset_rate: float,
    energy_std: float,
    bpm: float,
    **_kwargs: object,
) -> _MoodScore:
    """HYPNOTIC: strict rhythmic regularity + moderate-high BPM + repetitive motifs."""
    score = 0.0
    features = []

    # Very low flux variance = repetitive motifs (hypnotic loop persistence) - KEY FEATURE
    if flux_std < 35:
        score += (35 - flux_std) / 25 * 0.45  # Increased weight
        features.append("flux_std")

    # Regular onset pattern (not sparse, but highly regular)
    if 5.5 <= onset_rate <= 7.5:
        score += 0.25
        features.append("onset_rate")

    # Low energy variance = strict rhythmic regularity - KEY FEATURE
    if energy_std < 0.11:
        score += (0.11 - energy_std) / 0.07 * 0.25  # Increased weight
        features.append("energy_std")

    # Hypnotic grooves often in moderate-high BPM
    if 130 <= bpm <= 138:
        score += 0.05  # Reduced weight
        features.append("bpm")

    return _MoodScore(TrackMood.HYPNOTIC, score, tuple(features))


def _score_driving(
    bpm: float,
    kick_prominence: float,
    onset_rate: float,
    spectral_centroid_mean: float,
    lufs_i: float,
    **_kwargs: object,
) -> _MoodScore:
    """DRIVING: balanced kick + moderate BPM + steady energy (now a scored profile)."""
    score = 0.0
    features = []

    # Driving sweet spot: 128-136 BPM (strict)
    if 128 <= bpm <= 136:
        score += 0.3
        features.append("bpm")
    elif bpm < 125 or bpm > 140:
        return _MoodScore(TrackMood.DRIVING, 0.0, tuple())  # Hard reject out of range

    # Balanced kick (not too heavy, not too weak)
    if 0.45 <= kick_prominence <= 0.6:
        score += 0.3
        features.append("kick_prominence")

    # Moderate onset activity
    if 5.5 <= onset_rate <= 7.5:
        score += 0.2
        features.append("onset_rate")

    # Mid-range spectral centroid
    if 2200 <= spectral_centroid_mean <= 3000:
        score += 0.1
        features.append("spectral_centroid_mean")

    # Moderate loudness (not too quiet, not peak)
    if -9.5 <= lufs_i <= -7.5:
        score += 0.1
        features.append("lufs_i")

    return _MoodScore(TrackMood.DRIVING, score, tuple(features))


def classify_track(
    *,
    bpm: float,
    lufs_i: float,
    kick_prominence: float,
    spectral_centroid_mean: float,
    onset_rate: float,
    hp_ratio: float,
    flux_std: float,
    energy_std: float,
    crest_factor_db: float,
    lra_lu: float,
) -> MoodClassification:
    """Classify a track into one of 9 mood categories.

    Uses scored profile matching (best score wins).

    Args:
        bpm: Track tempo in BPM.
        lufs_i: Integrated loudness (LUFS).
        kick_prominence: Kick energy at beat positions [0, 1].
        spectral_centroid_mean: Mean spectral centroid (Hz).
        onset_rate: Onsets per second.
        hp_ratio: Harmonic/percussive energy ratio [0, 1].
        flux_std: Spectral flux standard deviation (variability).
        energy_std: Energy envelope standard deviation (dynamics).
        crest_factor_db: Crest factor in dB (transient vs sustained).
        lra_lu: Loudness range in LU (dynamic range).

    Returns:
        MoodClassification with mood, confidence, and features_used.
    """
    # Collect all parameters for passing to scorers
    params = {
        "bpm": bpm,
        "lufs_i": lufs_i,
        "kick_prominence": kick_prominence,
        "spectral_centroid_mean": spectral_centroid_mean,
        "onset_rate": onset_rate,
        "hp_ratio": hp_ratio,
        "flux_std": flux_std,
        "energy_std": energy_std,
        "crest_factor_db": crest_factor_db,
        "lra_lu": lra_lu,
    }

    # Score all mood profiles
    scores = [
        _score_hard_techno(**params),
        _score_industrial(**params),
        _score_ambient_dub(**params),
        _score_dub_techno(**params),
        _score_peak_time(**params),
        _score_melodic_deep(**params),
        _score_minimal(**params),
        _score_hypnotic(**params),
        _score_driving(**params),
    ]

    # Sort by score (descending)
    scores.sort(key=lambda s: s.score, reverse=True)
    best = scores[0]
    second_best = scores[1]

    # Calculate confidence based on margin between best and second-best
    margin = best.score - second_best.score

    if margin < 0.05:
        # Very close scores → low confidence
        confidence = 0.3 + margin * 4  # 0.3-0.5 range
    elif margin > 0.15:
        # Large margin → high confidence
        confidence = min(1.0, 0.7 + (margin - 0.15) * 2)  # 0.7-1.0 range
    else:
        # Moderate margin → moderate confidence
        confidence = 0.5 + (margin - 0.05) * 2  # 0.5-0.7 range

    # Ensure confidence is in valid range
    confidence = max(0.0, min(1.0, confidence))

    return MoodClassification(
        mood=best.mood,
        confidence=confidence,
        features_used=best.features,
    )
