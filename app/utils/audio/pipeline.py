from __future__ import annotations

import logging
from pathlib import Path

from app.utils.audio._errors import AudioAnalysisError, AudioValidationError
from app.utils.audio._types import AudioSignal, TrackFeatures
from app.utils.audio.bpm import estimate_bpm
from app.utils.audio.energy import compute_band_energies
from app.utils.audio.key_detect import detect_key
from app.utils.audio.loader import load_audio, validate_audio
from app.utils.audio.loudness import measure_loudness
from app.utils.audio.spectral import extract_spectral_features

logger = logging.getLogger(__name__)


def _run_stage(stage: str, path: str, fn: object, signal: AudioSignal) -> object:
    """Run an analysis stage, wrapping unexpected errors in AudioAnalysisError."""
    try:
        return fn(signal)  # type: ignore[operator]
    except (AudioValidationError, FileNotFoundError):
        raise
    except Exception as exc:
        raise AudioAnalysisError(stage, path, exc) from exc


def extract_all_features(
    path: str | Path,
    *,
    target_sr: int = 44100,
) -> TrackFeatures:
    """Load audio file and extract all analysis features.

    Raises:
        FileNotFoundError: If the file does not exist.
        AudioValidationError: If the audio is silence, too short, or corrupt.
        AudioAnalysisError: If any analysis stage fails unexpectedly.
    """
    path_str = str(path)

    signal = load_audio(path, target_sr=target_sr)
    validate_audio(signal)

    logger.info("Extracting features from %s (%.1fs)", path, signal.duration_s)

    bpm_result = _run_stage("bpm", path_str, estimate_bpm, signal)
    key_result = _run_stage("key", path_str, detect_key, signal)
    loudness_result = _run_stage("loudness", path_str, measure_loudness, signal)
    band_energy_result = _run_stage("band_energy", path_str, compute_band_energies, signal)
    spectral_result = _run_stage("spectral", path_str, extract_spectral_features, signal)

    # Phase 2: Beats extraction (optional, graceful failure)
    beats_result = None
    try:
        from app.utils.audio.beats import detect_beats

        beats_result = _run_stage("beats", path_str, detect_beats, signal)
    except ImportError:
        logger.debug("essentia/scipy not installed — skipping beats extraction")
    except AudioAnalysisError:
        logger.warning("Beats extraction failed for %s", path, exc_info=True)

    # Phase 2: MFCC extraction (optional, graceful failure)
    mfcc_result = None
    try:
        from app.utils.audio.mfcc import extract_mfcc

        mfcc_result = _run_stage("mfcc", path_str, extract_mfcc, signal)
    except ImportError:
        logger.debug("librosa not installed — skipping MFCC extraction")
    except AudioAnalysisError:
        logger.warning("MFCC extraction failed for %s", path, exc_info=True)

    logger.info(
        "Extraction complete: BPM=%.1f key=%s%s loudness=%.1f LUFS",
        bpm_result.bpm,  # type: ignore[attr-defined]
        key_result.key,  # type: ignore[attr-defined]
        key_result.scale[0],  # type: ignore[attr-defined]
        loudness_result.lufs_i,  # type: ignore[attr-defined]
    )

    return TrackFeatures(
        bpm=bpm_result,  # type: ignore[arg-type]
        key=key_result,  # type: ignore[arg-type]
        loudness=loudness_result,  # type: ignore[arg-type]
        band_energy=band_energy_result,  # type: ignore[arg-type]
        spectral=spectral_result,  # type: ignore[arg-type]
        beats=beats_result,  # type: ignore[arg-type]
        mfcc=mfcc_result,  # type: ignore[arg-type]
    )
