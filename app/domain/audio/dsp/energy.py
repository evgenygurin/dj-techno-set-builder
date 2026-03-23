from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from app.domain.audio.types import AudioSignal, BandEnergyResult

# Frequency bands (Hz)
_BANDS: list[tuple[str, float, float]] = [
    ("sub", 20.0, 60.0),
    ("low", 60.0, 200.0),
    ("low_mid", 200.0, 800.0),
    ("mid", 800.0, 3000.0),
    ("high_mid", 3000.0, 6000.0),
    ("high", 6000.0, 12000.0),
]

_FILTER_ORDER = 4


def _bandpass_energy(
    samples: np.ndarray,
    sr: int,
    low_hz: float,
    high_hz: float,
) -> float:
    """Compute RMS energy in a frequency band using Butterworth bandpass."""
    nyquist = sr / 2.0
    low = max(low_hz / nyquist, 0.001)
    high = min(high_hz / nyquist, 0.999)
    if low >= high:
        return 0.0
    sos = butter(_FILTER_ORDER, [low, high], btype="bandpass", output="sos")
    filtered = sosfiltfilt(sos, samples)
    return float(np.sqrt(np.mean(filtered**2)))


def _frame_rms_stats(
    samples: np.ndarray, frame_size: int = 2048, hop_size: int = 512
) -> tuple[float, float]:
    """Compute slope and std of frame-level RMS energy.

    Returns (slope, std). Slope via linear regression, std via numpy.
    """
    n_frames = 1 + (len(samples) - frame_size) // hop_size
    if n_frames < 2:
        return 0.0, 0.0
    energies = np.array(
        [
            float(np.sqrt(np.mean(samples[i * hop_size : i * hop_size + frame_size] ** 2)))
            for i in range(n_frames)
        ]
    )
    x = np.arange(n_frames, dtype=np.float64)
    slope = float(np.polyfit(x, energies.astype(np.float64), 1)[0])
    std = float(np.std(energies))
    return slope, std


def compute_band_energies(signal: AudioSignal) -> BandEnergyResult:
    """Compute energy in 6 frequency bands, normalized to 0-1."""
    raw: dict[str, float] = {}
    for name, low_hz, high_hz in _BANDS:
        raw[name] = _bandpass_energy(signal.samples, signal.sample_rate, low_hz, high_hz)

    # Normalize: divide by max band energy (or 1.0 if all zero)
    max_energy = max(raw.values()) or 1.0
    normed = {k: v / max_energy for k, v in raw.items()}

    low_val = normed["low"]
    high_val = normed["high"]
    sub_val = normed["sub"]
    lowmid_val = normed["low_mid"]

    energy_slope, energy_std = _frame_rms_stats(signal.samples)

    return BandEnergyResult(
        sub=normed["sub"],
        low=normed["low"],
        low_mid=normed["low_mid"],
        mid=normed["mid"],
        high_mid=normed["high_mid"],
        high=normed["high"],
        low_high_ratio=low_val / high_val if high_val > 1e-10 else 0.0,
        sub_lowmid_ratio=sub_val / lowmid_val if lowmid_val > 1e-10 else 0.0,
        energy_slope_mean=energy_slope,
        energy_std=energy_std,
    )
