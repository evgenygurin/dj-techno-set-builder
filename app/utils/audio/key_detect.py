from __future__ import annotations

import math

import numpy as np

from app.utils.audio._types import AudioSignal, KeyResult

# Essentia key names → pitch_class mapping
_PITCH_CLASS: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

_MODE_MAP: dict[str, int] = {"minor": 0, "major": 1}

# Atonal detection: if chroma entropy is close to max (uniform), the track is atonal
_MAX_CHROMA_ENTROPY = math.log2(12)  # ~3.585
_ATONAL_ENTROPY_THRESHOLD = 0.95  # fraction of max entropy


def _key_to_key_code(key: str, scale: str) -> int:
    """Convert essentia key name + scale to key_code (0-23)."""
    pitch = _PITCH_CLASS[key]
    mode = _MODE_MAP[scale]
    return pitch * 2 + mode


def _chroma_entropy(chroma: np.ndarray) -> float:  # type: ignore[type-arg]
    """Compute Shannon entropy of a chroma vector (normalized)."""
    chroma = chroma / (chroma.sum() + 1e-10)
    chroma = chroma[chroma > 0]
    return float(-np.sum(chroma * np.log2(chroma)))


def detect_key(
    signal: AudioSignal,
    *,
    profile: str = "bgate",
) -> KeyResult:
    """Detect musical key using essentia KeyExtractor with EDM-specific profiles.

    Profiles: 'bgate' (default, Beatport-derived), 'edmm' (manual EDM),
    'edma' (auto EDM), 'braw' (raw Beatport medians).
    """
    import essentia.standard as es

    key_extractor = es.KeyExtractor(
        profileType=profile,
        sampleRate=float(signal.sample_rate),
    )
    key, scale, strength = key_extractor(signal.samples)

    # Compute mean chroma (HPCP) for the chroma vector field
    hpcp = es.HPCP(
        size=12,
        referenceFrequency=440.0,
        sampleRate=float(signal.sample_rate),
    )
    w = es.Windowing(type="blackmanharris62")
    spectrum = es.Spectrum()
    spectral_peaks = es.SpectralPeaks(
        sampleRate=float(signal.sample_rate),
        maxFrequency=3500.0,
    )

    chroma_frames: list[np.ndarray] = []  # type: ignore[type-arg]
    for frame in es.FrameGenerator(signal.samples, frameSize=4096, hopSize=2048):
        windowed = w(frame)
        spec = spectrum(windowed)
        freqs, mags = spectral_peaks(spec)
        chroma_frame = hpcp(freqs, mags)
        chroma_frames.append(chroma_frame)

    if chroma_frames:
        mean_chroma = np.mean(chroma_frames, axis=0).astype(np.float32)
    else:
        mean_chroma = np.zeros(12, dtype=np.float32)

    # Atonal detection
    entropy = _chroma_entropy(mean_chroma)
    is_atonal = entropy > _ATONAL_ENTROPY_THRESHOLD * _MAX_CHROMA_ENTROPY

    key_code = _key_to_key_code(key, scale)

    return KeyResult(
        key=key,
        scale=scale,
        key_code=key_code,
        confidence=float(np.clip(strength, 0.0, 1.0)),
        is_atonal=is_atonal,
        chroma=mean_chroma,
    )
