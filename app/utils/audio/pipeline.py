from __future__ import annotations

import logging
from pathlib import Path

from app.utils.audio._types import TrackFeatures
from app.utils.audio.bpm import estimate_bpm
from app.utils.audio.energy import compute_band_energies
from app.utils.audio.key_detect import detect_key
from app.utils.audio.loader import load_audio, validate_audio
from app.utils.audio.loudness import measure_loudness
from app.utils.audio.spectral import extract_spectral_features

logger = logging.getLogger(__name__)


def extract_all_features(
    path: str | Path,
    *,
    target_sr: int = 44100,
) -> TrackFeatures:
    """Load audio file and extract all analysis features.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the audio is silence or too short.
    """
    signal = load_audio(path, target_sr=target_sr)
    validate_audio(signal)

    logger.info("Extracting features from %s (%.1fs)", path, signal.duration_s)

    bpm_result = estimate_bpm(signal)
    key_result = detect_key(signal)
    loudness_result = measure_loudness(signal)
    band_energy_result = compute_band_energies(signal)
    spectral_result = extract_spectral_features(signal)

    logger.info(
        "Extraction complete: BPM=%.1f key=%s%s loudness=%.1f LUFS",
        bpm_result.bpm,
        key_result.key,
        key_result.scale[0],
        loudness_result.lufs_i,
    )

    return TrackFeatures(
        bpm=bpm_result,
        key=key_result,
        loudness=loudness_result,
        band_energy=band_energy_result,
        spectral=spectral_result,
    )
