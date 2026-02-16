from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class AudioSignal:
    """Raw audio data with metadata."""

    samples: NDArray[np.float32]
    sample_rate: int
    duration_s: float


@dataclass(frozen=True, slots=True)
class BpmResult:
    bpm: float
    confidence: float  # 0-1
    stability: float  # 0-1
    is_variable: bool


@dataclass(frozen=True, slots=True)
class KeyResult:
    key: str  # e.g. "A"
    scale: str  # "minor" or "major"
    key_code: int  # 0-23 (pitch_class * 2 + mode)
    confidence: float  # 0-1
    is_atonal: bool
    chroma: NDArray[np.float32]  # 12-dim mean HPCP vector
    chroma_entropy: float  # Shannon entropy / log2(12), normalized [0, 1]


@dataclass(frozen=True, slots=True)
class LoudnessResult:
    lufs_i: float  # Integrated loudness (LUFS)
    lufs_s_mean: float  # Short-term mean (LUFS)
    lufs_m_max: float  # Momentary max (LUFS)
    rms_dbfs: float  # RMS level (dBFS)
    true_peak_db: float  # True peak (dBTP)
    crest_factor_db: float  # true_peak_db - rms_dbfs
    lra_lu: float  # Loudness range (LU)


@dataclass(frozen=True, slots=True)
class BandEnergyResult:
    sub: float  # 20-60 Hz, normalized 0-1
    low: float  # 60-200 Hz
    low_mid: float  # 200-800 Hz
    mid: float  # 800-3000 Hz
    high_mid: float  # 3000-6000 Hz
    high: float  # 6000-12000 Hz
    low_high_ratio: float  # low / high (or 0 if high ≈ 0)
    sub_lowmid_ratio: float  # sub / low_mid (or 0 if low_mid ≈ 0)
    energy_slope_mean: float = 0.0  # mean slope of frame-level RMS energy
    energy_std: float = 0.0  # std of frame-level RMS energy


@dataclass(frozen=True, slots=True)
class SpectralResult:
    centroid_mean_hz: float
    rolloff_85_hz: float
    rolloff_95_hz: float
    flatness_mean: float  # 0-1
    flux_mean: float
    flux_std: float
    contrast_mean_db: float
    slope_db_per_oct: float = 0.0
    hnr_mean_db: float = 0.0  # harmonics-to-noise ratio in dB


@dataclass(frozen=True, slots=True)
class BeatsResult:
    beat_times: NDArray[np.float32]  # seconds, sorted
    downbeat_times: NDArray[np.float32]  # every 4th beat (4/4 assumption)
    onset_rate_mean: float  # onsets per second, mean
    onset_rate_max: float  # onsets per second, max (windowed)
    pulse_clarity: float  # 0-1, how clear the pulse is
    kick_prominence: float  # 0-1, how prominent kick is at beat positions
    hp_ratio: float  # harmonic / percussive energy ratio
    onset_envelope: NDArray[np.float32]  # frame-level onset strength


@dataclass(frozen=True, slots=True)
class StemsResult:
    """Four-stem source separation result."""

    drums: AudioSignal  # asset_type = 1
    bass: AudioSignal  # asset_type = 2
    vocals: AudioSignal  # asset_type = 3
    other: AudioSignal  # asset_type = 4


@dataclass(frozen=True, slots=True)
class SectionResult:
    """One detected structural section.

    section_type matches SectionType enum (app/models/enums.py):
      0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro,
      5=break, 6=inst, 7=verse, 8=chorus, 9=bridge, 10=solo, 11=unknown
    """

    section_type: int
    start_s: float
    end_s: float
    duration_s: float
    energy_mean: float  # 0-1
    energy_max: float  # 0-1
    energy_slope: float  # positive = rising, negative = falling
    boundary_confidence: float  # 0-1
    centroid_hz: float | None = None  # spectral centroid mean for section
    flux: float | None = None  # spectral flux mean for section
    onset_rate: float | None = None  # onsets per second in section
    pulse_clarity: float | None = None  # rhythmic clarity 0-1


@dataclass(frozen=True, slots=True)
class TransitionScore:
    """Composite transition quality score between two tracks.

    Maps to Transition model fields.
    """

    transition_quality: float  # 0-1, composite score (higher = better)
    bpm_distance: float  # absolute BPM difference
    key_distance_weighted: float  # Camelot distance * confidence
    energy_step: float  # signed energy difference (positive = going up)
    low_conflict_score: float  # 0-1, bass frequency overlap risk
    overlap_score: float  # 0-1, spectral compatibility
    groove_similarity: float  # 0-1, rhythmic pattern compatibility


@dataclass(frozen=True, slots=True)
class TrackFeatures:
    """Complete feature set for one track."""

    bpm: BpmResult
    key: KeyResult
    loudness: LoudnessResult
    band_energy: BandEnergyResult
    spectral: SpectralResult
    beats: BeatsResult | None = None  # Phase 2: optional
