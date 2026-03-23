"""Structure segmentation for techno tracks.

DSP-based approach: energy novelty function → peak picking → section labeling.
Maps to TrackSection model (section_type 0-11, see app/models/enums.py).

Labeling heuristic for techno:
  - First section with low energy → INTRO (0)
  - Rising energy → BUILDUP (1)
  - High energy plateau → DROP (2)
  - Falling energy from high → BREAKDOWN (3)
  - Last section with low energy → OUTRO (4)
  - Low energy in middle → BREAK (5)
  - Everything else → UNKNOWN (11)
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from app.domain.audio.types import AudioSignal, SectionResult

# Section type constants (match SectionType enum)
INTRO = 0
BUILDUP = 1
DROP = 2
BREAKDOWN = 3
OUTRO = 4
BREAK = 5
UNKNOWN = 11

_FRAME_SIZE = 2048
_HOP_SIZE = 512
_SMOOTH_WINDOW = 100  # frames for energy smoothing (~2.3s at 44100/512)
_MIN_SECTION_S = 3.0  # minimum section duration
_NOVELTY_SMOOTH = 20  # frames for novelty smoothing
_ENERGY_HIGH_PERCENTILE = 70  # above this = "high energy"
_ENERGY_LOW_PERCENTILE = 30  # below this = "low energy"


def _frame_energies(signal: AudioSignal) -> np.ndarray:
    """Compute frame-level RMS energy."""
    import essentia.standard as es

    energies: list[float] = []
    for frame in es.FrameGenerator(signal.samples, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE):
        energies.append(float(np.sqrt(np.mean(frame**2))))
    return np.array(energies, dtype=np.float32)


def _find_boundaries(energy: np.ndarray, min_frames: int) -> list[int]:
    """Find section boundaries from energy novelty peaks."""
    # Smooth energy curve
    smooth = uniform_filter1d(energy.astype(np.float64), size=_SMOOTH_WINDOW)

    # Novelty = absolute derivative of smoothed energy
    novelty = np.abs(np.diff(smooth))
    novelty = uniform_filter1d(novelty, size=_NOVELTY_SMOOTH)

    # Normalize novelty
    nov_max = novelty.max()
    if nov_max > 0:
        novelty = novelty / nov_max

    # Find peaks in novelty (= section boundaries)
    peaks, _ = find_peaks(
        novelty,
        distance=min_frames,
        height=0.15,  # minimum novelty threshold
        prominence=0.1,
    )

    return sorted(peaks.tolist())


def _label_section(
    energy_mean: float,
    energy_slope: float,
    *,
    is_first: bool,
    is_last: bool,
    high_threshold: float,
    low_threshold: float,
) -> int:
    """Assign section_type based on energy profile."""
    if is_first and energy_mean < high_threshold:
        return INTRO
    if is_last and energy_mean < high_threshold:
        return OUTRO
    if energy_mean >= high_threshold and abs(energy_slope) < 0.1:
        return DROP
    if energy_slope > 0.05:
        return BUILDUP
    if energy_slope < -0.05 and energy_mean > low_threshold:
        return BREAKDOWN
    if energy_mean < low_threshold and not is_first and not is_last:
        return BREAK
    return UNKNOWN


def _compute_section_spectral(
    signal: AudioSignal,
    start_s: float,
    end_s: float,
) -> tuple[float, float]:
    """Compute lightweight per-section spectral metrics: centroid_hz, flux.

    Only computes cheap frame-level spectral features.
    Onset rate and pulse clarity are derived from beat_times in the service layer.
    """
    import essentia.standard as es

    sr = signal.sample_rate
    start_sample = int(start_s * sr)
    end_sample = min(int(end_s * sr), len(signal.samples))
    segment = signal.samples[start_sample:end_sample]

    if len(segment) < _FRAME_SIZE:
        return 0.0, 0.0

    centroids: list[float] = []
    fluxes: list[float] = []
    prev_spectrum = np.zeros(_FRAME_SIZE // 2 + 1, dtype=np.float32)
    spectrum_fn = es.Spectrum(size=_FRAME_SIZE)
    centroid_fn = es.SpectralCentroidTime(sampleRate=float(sr))
    windowing_fn = es.Windowing(type="hann")

    for frame in es.FrameGenerator(segment, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE):
        windowed = windowing_fn(frame)
        spectrum = spectrum_fn(windowed)
        centroids.append(float(centroid_fn(frame)))
        diff = spectrum - prev_spectrum
        fluxes.append(float(np.sqrt(np.sum(diff**2))))
        prev_spectrum = spectrum

    centroid_hz = float(np.mean(centroids)) if centroids else 0.0
    flux_mean = float(np.mean(fluxes)) if fluxes else 0.0

    return centroid_hz, flux_mean


def _compute_section_pulse_clarity(
    section_beats: np.ndarray,
    *,
    track_pulse_clarity: float | None,
) -> float:
    """Estimate section pulse clarity from beat interval regularity.

    Formula:
      - >=3 beats: local = clip(1 - std(IOI)/mean(IOI), 0, 1)
      - blend with track pulse when available: 0.7*local + 0.3*track
      - short sections (<3 beats): fallback to track pulse, else 0.0
    """
    if len(section_beats) >= 3:
        ioi = np.diff(section_beats.astype(np.float64))
        ioi_mean = float(np.mean(ioi))
        if ioi_mean > 0:
            cv = float(np.std(ioi)) / ioi_mean
            local = float(np.clip(1.0 - cv, 0.0, 1.0))
        else:
            local = 0.0

        if track_pulse_clarity is not None:
            return float(np.clip(0.7 * local + 0.3 * track_pulse_clarity, 0.0, 1.0))
        return local

    if track_pulse_clarity is not None:
        return float(np.clip(track_pulse_clarity, 0.0, 1.0))

    return 0.0


def segment_structure(
    signal: AudioSignal,
    *,
    min_section_s: float = _MIN_SECTION_S,
    beat_times: np.ndarray | None = None,
    track_pulse_clarity: float | None = None,
) -> list[SectionResult]:
    """Segment track into structural sections.

    If beat_times is provided, computes per-section onset_rate and pulse_clarity.
    Returns list of SectionResult sorted by start time.
    """
    sr = signal.sample_rate
    frame_energy = _frame_energies(signal)
    frames_per_sec = sr / _HOP_SIZE
    min_frames = int(min_section_s * frames_per_sec)

    # Normalize energy to 0-1
    e_max = frame_energy.max()
    norm_energy = frame_energy / e_max if e_max > 0 else frame_energy

    # Find boundaries
    boundaries = _find_boundaries(norm_energy, min_frames)

    # Add start and end
    all_boundaries = [0, *boundaries, len(norm_energy) - 1]

    # Compute thresholds
    high_thresh = float(np.percentile(norm_energy, _ENERGY_HIGH_PERCENTILE))
    low_thresh = float(np.percentile(norm_energy, _ENERGY_LOW_PERCENTILE))

    sections: list[SectionResult] = []
    for i in range(len(all_boundaries) - 1):
        start_frame = all_boundaries[i]
        end_frame = all_boundaries[i + 1]

        if end_frame <= start_frame:
            continue

        seg_energy = norm_energy[start_frame:end_frame]
        start_s = start_frame / frames_per_sec
        end_s = end_frame / frames_per_sec
        duration_s = end_s - start_s

        if duration_s < min_section_s * 0.5:
            continue

        e_mean = float(np.mean(seg_energy))
        e_max_val = float(np.max(seg_energy))

        # Energy slope: linear regression coefficient
        if len(seg_energy) > 1:
            x = np.arange(len(seg_energy), dtype=np.float64)
            slope = float(np.polyfit(x, seg_energy.astype(np.float64), 1)[0])
            # Normalize slope to roughly -1..1 range
            slope = float(np.clip(slope * len(seg_energy), -1.0, 1.0))
        else:
            slope = 0.0

        # Boundary confidence: novelty height at this boundary
        boundary_conf = 0.5  # default for first/last
        if 0 < i < len(all_boundaries) - 1:
            smooth = uniform_filter1d(norm_energy.astype(np.float64), size=_SMOOTH_WINDOW)
            novelty = np.abs(np.diff(smooth))
            nov_max = novelty.max() or 1.0
            if start_frame < len(novelty):
                boundary_conf = float(np.clip(novelty[start_frame] / nov_max, 0.0, 1.0))

        section_type = _label_section(
            e_mean,
            slope,
            is_first=(i == 0),
            is_last=(i == len(all_boundaries) - 2),
            high_threshold=high_thresh,
            low_threshold=low_thresh,
        )

        # Per-section spectral metrics (lightweight: centroid + flux only)
        centroid_hz, flux = _compute_section_spectral(signal, start_s, end_s)

        # Onset rate and pulse clarity from pre-computed beat_times
        onset_rate: float | None = None
        pulse_clarity: float | None = None
        if beat_times is not None and duration_s > 0:
            section_beats = beat_times[(beat_times >= start_s) & (beat_times < end_s)]
            onset_rate = float(len(section_beats) / duration_s)
            pulse_clarity = _compute_section_pulse_clarity(
                section_beats,
                track_pulse_clarity=track_pulse_clarity,
            )

        sections.append(
            SectionResult(
                section_type=section_type,
                start_s=start_s,
                end_s=end_s,
                duration_s=duration_s,
                energy_mean=float(np.clip(e_mean, 0.0, 1.0)),
                energy_max=float(np.clip(e_max_val, 0.0, 1.0)),
                energy_slope=slope,
                boundary_confidence=boundary_conf,
                centroid_hz=centroid_hz,
                flux=flux,
                onset_rate=onset_rate,
                pulse_clarity=pulse_clarity,
            )
        )

    # Fallback: if no sections found, return one UNKNOWN section
    if not sections:
        centroid_hz, flux = _compute_section_spectral(signal, 0.0, signal.duration_s)
        fallback_onset_rate: float | None = None
        fallback_pulse_clarity: float | None = None
        if beat_times is not None and signal.duration_s > 0:
            fallback_onset_rate = float(len(beat_times) / signal.duration_s)
            fallback_pulse_clarity = _compute_section_pulse_clarity(
                beat_times,
                track_pulse_clarity=track_pulse_clarity,
            )

        sections.append(
            SectionResult(
                section_type=UNKNOWN,
                start_s=0.0,
                end_s=signal.duration_s,
                duration_s=signal.duration_s,
                energy_mean=float(np.mean(norm_energy)),
                energy_max=float(np.max(norm_energy)),
                energy_slope=0.0,
                boundary_confidence=0.0,
                centroid_hz=centroid_hz,
                flux=flux,
                onset_rate=fallback_onset_rate,
                pulse_clarity=fallback_pulse_clarity,
            )
        )

    return sections
