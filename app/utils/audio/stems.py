"""Source separation using Demucs v4 (HTDemucs).

Separates audio into 4 stems: drums, bass, vocals, other.
Maps to AudioAsset.asset_type: 1=drums, 2=bass, 3=vocals, 4=other.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.utils.audio._types import AudioSignal, StemsResult

logger = logging.getLogger(__name__)

_MODEL_NAME = "htdemucs"
_STEM_NAMES = ("drums", "bass", "vocals", "other")


def separate_stems(
    signal: AudioSignal,
    *,
    model_name: str = _MODEL_NAME,
    device: str | None = None,
) -> StemsResult:
    """Separate audio into 4 stems using Demucs v4.

    Args:
        signal: Input audio signal (mono or stereo).
        model_name: Demucs model name ('htdemucs', 'htdemucs_ft').
        device: 'cuda', 'cpu', or None (auto-detect).

    Returns:
        StemsResult with drums, bass, vocals, other AudioSignal objects.
    """
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    logger.info("Loading Demucs model %s on %s", model_name, device)
    model: Any = get_model(model_name)
    model.to(device)

    sr = signal.sample_rate
    audio = signal.samples

    # Demucs expects: (batch, channels, samples) — requires 2 channels
    audio_2ch = np.stack([audio, audio], axis=0) if audio.ndim == 1 else audio

    tensor = torch.tensor(audio_2ch, dtype=torch.float32).unsqueeze(0)
    tensor = tensor.to(device)

    # Resample to model's expected sample rate if needed
    model_sr: int = model.samplerate
    if sr != model_sr:
        import torchaudio

        tensor = torchaudio.functional.resample(tensor, sr, model_sr)

    logger.info("Running source separation (%d samples)...", tensor.shape[-1])

    with torch.no_grad():
        sources: Any = apply_model(model, tensor, device=device)
    # sources shape: (1, num_sources, 2, samples)

    # Resample back if needed
    if sr != model_sr:
        import torchaudio

        sources = torchaudio.functional.resample(sources, model_sr, sr)

    sources_np: np.ndarray[Any, Any] = sources.squeeze(0).cpu().numpy()

    # Build stem name → index mapping
    stem_map: dict[str, int] = {
        name: i for i, name in enumerate(model.sources)
    }

    stems: dict[str, AudioSignal] = {}
    for name in _STEM_NAMES:
        idx = stem_map.get(name)
        if idx is not None:
            # Convert stereo to mono (mean of channels)
            stem_mono = sources_np[idx].mean(axis=0).astype(np.float32)
        else:
            stem_mono = np.zeros(len(signal.samples), dtype=np.float32)

        stems[name] = AudioSignal(
            samples=stem_mono,
            sample_rate=sr,
            duration_s=len(stem_mono) / sr,
        )

    logger.info("Separation complete: %s", list(stems.keys()))

    return StemsResult(
        drums=stems["drums"],
        bass=stems["bass"],
        vocals=stems["vocals"],
        other=stems["other"],
    )
