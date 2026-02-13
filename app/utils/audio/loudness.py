from __future__ import annotations

import numpy as np
from scipy.signal import resample

from app.utils.audio._types import AudioSignal, LoudnessResult

_TRUE_PEAK_OVERSAMPLE = 4


def _mono_to_stereo(samples: np.ndarray) -> np.ndarray:
    """Convert mono samples to stereo (Nx2) for essentia LoudnessEBUR128."""
    return np.column_stack([samples, samples]).astype(np.float32)


def _true_peak_dbtp(samples: np.ndarray) -> float:
    """Compute true peak (dBTP) via 4x oversampling per ITU-R BS.1770."""
    oversampled = resample(samples, len(samples) * _TRUE_PEAK_OVERSAMPLE)
    peak_linear = float(np.max(np.abs(oversampled)))
    return float(20.0 * np.log10(peak_linear + 1e-10))


def measure_loudness(signal: AudioSignal) -> LoudnessResult:
    """Measure loudness using essentia LoudnessEBUR128 (all 5 EBU R128 metrics)."""
    import essentia.standard as es

    stereo = _mono_to_stereo(signal.samples)

    loudness = es.LoudnessEBUR128(sampleRate=float(signal.sample_rate))
    momentary, short_term, integrated, loudness_range = loudness(stereo)

    # Short-term mean and momentary max
    lufs_s_mean = float(np.mean(short_term)) if len(short_term) > 0 else float(integrated)
    lufs_m_max = float(np.max(momentary)) if len(momentary) > 0 else float(integrated)

    # RMS in dBFS
    rms_linear = float(np.sqrt(np.mean(signal.samples**2)))
    rms_dbfs = float(20.0 * np.log10(rms_linear + 1e-10))

    # True peak via 4x oversampling
    true_peak_db = _true_peak_dbtp(signal.samples)

    crest_factor_db = max(0.0, true_peak_db - rms_dbfs)

    return LoudnessResult(
        lufs_i=float(integrated),
        lufs_s_mean=lufs_s_mean,
        lufs_m_max=lufs_m_max,
        rms_dbfs=rms_dbfs,
        true_peak_db=true_peak_db,
        crest_factor_db=crest_factor_db,
        lra_lu=float(max(0.0, loudness_range)),
    )
