from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from app.utils.audio._types import AudioSignal

_MIN_DURATION_S = 1.0
_SILENCE_THRESHOLD = 1e-6


def load_audio(
    path: str | Path,
    *,
    target_sr: int = 44100,
    mono: bool = True,
) -> AudioSignal:
    """Load an audio file and return an AudioSignal.

    Resamples to *target_sr* if the file's native rate differs.
    Converts to mono (channel averaging) when *mono* is True.
    """
    path = Path(path)
    if not path.exists():
        msg = f"Audio file not found: {path}"
        raise FileNotFoundError(msg)

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)

    # Mono mixdown
    if mono and data.shape[1] > 1:
        data = data.mean(axis=1)
    else:
        data = data[:, 0] if data.ndim == 2 else data

    # Resample if needed (simple linear interpolation — sufficient for analysis)
    if sr != target_sr:
        duration = len(data) / sr
        new_length = int(duration * target_sr)
        indices = np.linspace(0, len(data) - 1, new_length)
        data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)
        sr = target_sr

    duration_s = len(data) / sr
    return AudioSignal(samples=data, sample_rate=sr, duration_s=duration_s)


def validate_audio(signal: AudioSignal) -> None:
    """Raise ValueError if the audio signal is silence or too short."""
    if signal.duration_s < _MIN_DURATION_S:
        msg = f"Audio too short ({signal.duration_s:.2f}s < {_MIN_DURATION_S}s)"
        raise ValueError(msg)

    if np.max(np.abs(signal.samples)) < _SILENCE_THRESHOLD:
        msg = "Audio is silence (max amplitude < threshold)"
        raise ValueError(msg)

    if np.any(np.isnan(signal.samples)) or np.any(np.isinf(signal.samples)):
        msg = "Audio contains NaN or Inf samples"
        raise ValueError(msg)
