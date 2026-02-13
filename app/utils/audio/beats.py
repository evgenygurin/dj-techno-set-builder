"""Beat, onset, and rhythm feature extraction.

Uses essentia for beat tracking and onset detection.
Computes derived features: pulse_clarity, kick_prominence, hp_ratio.
Maps to TrackAudioFeaturesComputed fields: onset_rate_mean, onset_rate_max,
pulse_clarity, kick_prominence, hp_ratio.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from app.utils.audio._types import AudioSignal, BeatsResult

_HOP_SIZE = 512
_ONSET_WINDOW_S = 2.0  # window for windowed onset rate
_HARMONIC_LOW = 200.0
_HARMONIC_HIGH = 3000.0
_PERCUSSIVE_LOW = 3000.0
_PERCUSSIVE_HIGH = 12000.0
_FILTER_ORDER = 4


def _band_rms(samples: np.ndarray, sr: int, low: float, high: float) -> float:
    """RMS energy in a frequency band via Butterworth bandpass."""
    nyq = sr / 2.0
    lo = max(low / nyq, 0.001)
    hi = min(high / nyq, 0.999)
    if lo >= hi:
        return 0.0
    sos = butter(_FILTER_ORDER, [lo, hi], btype="bandpass", output="sos")
    filtered = sosfiltfilt(sos, samples)
    return float(np.sqrt(np.mean(filtered**2)))


def detect_beats(
    signal: AudioSignal,
    *,
    min_bpm: float = 80.0,
    max_bpm: float = 200.0,
) -> BeatsResult:
    """Detect beats, onsets, and compute rhythm features."""
    import essentia.standard as es

    sr = signal.sample_rate
    audio = signal.samples

    # ── 1. Beat tracking ──
    rhythm = es.RhythmExtractor2013(
        method="multifeature",
        minTempo=int(min_bpm),
        maxTempo=int(max_bpm),
    )
    # Returns: (bpm, ticks, confidence, estimates, bpmIntervals)
    # confidence is a single float (0-1), not an array
    _, beat_times, beat_confidence, _, _ = rhythm(audio)

    beat_times = np.sort(beat_times).astype(np.float32)

    # Downbeats: every 4th beat (4/4 assumption, standard for techno)
    downbeat_times = (
        beat_times[::4].astype(np.float32)
        if len(beat_times) >= 4
        else beat_times
    )

    # ── 2. Onset detection ──
    onset_rate_algo = es.OnsetRate()
    onsets_times, onset_rate_global = onset_rate_algo(audio)

    # Windowed onset rate: max onset density in sliding window
    if len(onsets_times) > 1 and signal.duration_s > _ONSET_WINDOW_S:
        window_counts: list[float] = []
        for t in np.arange(
            0, signal.duration_s - _ONSET_WINDOW_S, _ONSET_WINDOW_S / 2
        ):
            count = np.sum(
                (onsets_times >= t) & (onsets_times < t + _ONSET_WINDOW_S)
            )
            window_counts.append(float(count) / _ONSET_WINDOW_S)
        onset_rate_max = (
            float(max(window_counts)) if window_counts else onset_rate_global
        )
    else:
        onset_rate_max = onset_rate_global

    # ── 3. Onset envelope (frame-level) ──
    onset_env_frames: list[float] = []
    w = es.Windowing(type="hann")
    spectrum = es.Spectrum(size=2048)
    flux = es.Flux()
    for frame in es.FrameGenerator(audio, frameSize=2048, hopSize=_HOP_SIZE):
        windowed = w(frame)
        spec = spectrum(windowed)
        onset_env_frames.append(float(flux(spec)))
    onset_envelope = np.array(onset_env_frames, dtype=np.float32)

    # ── 4. Pulse clarity ──
    # Use beat confidence directly — higher = clearer rhythmic pulse
    pulse_clarity = float(np.clip(beat_confidence, 0.0, 1.0))

    # ── 5. Kick prominence ──
    # Energy in sub-bass at beat positions vs overall sub-bass energy
    if len(beat_times) > 2:
        beat_samples = (beat_times * sr).astype(int)
        beat_samples = beat_samples[beat_samples < len(audio)]
        window_half = int(0.015 * sr)  # ±15ms around beat

        beat_energies: list[float] = []
        for bs in beat_samples:
            start = max(0, bs - window_half)
            end = min(len(audio), bs + window_half)
            segment = audio[start:end]
            if len(segment) > 0:
                beat_energies.append(float(np.mean(segment**2)))

        overall_energy = float(np.mean(audio**2)) + 1e-10
        beat_mean_energy = (
            float(np.mean(beat_energies)) if beat_energies else 0.0
        )
        kick_prominence = float(
            np.clip(beat_mean_energy / overall_energy, 0.0, 1.0)
        )
    else:
        kick_prominence = 0.0

    # ── 6. Harmonic / Percussive ratio ──
    harmonic_rms = _band_rms(audio, sr, _HARMONIC_LOW, _HARMONIC_HIGH)
    percussive_rms = _band_rms(audio, sr, _PERCUSSIVE_LOW, _PERCUSSIVE_HIGH)
    hp_ratio = harmonic_rms / (percussive_rms + 1e-10)

    return BeatsResult(
        beat_times=beat_times,
        downbeat_times=downbeat_times,
        onset_rate_mean=float(onset_rate_global),
        onset_rate_max=float(onset_rate_max),
        pulse_clarity=pulse_clarity,
        kick_prominence=kick_prominence,
        hp_ratio=float(hp_ratio),
        onset_envelope=onset_envelope,
    )
