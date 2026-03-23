from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from app.audio._errors import AudioAnalysisError, AudioValidationError
from app.audio._types import AudioSignal, TrackFeatures
from app.audio.bpm import estimate_bpm
from app.audio.energy import compute_band_energies
from app.audio.key_detect import detect_key
from app.audio.loader import load_audio, validate_audio
from app.audio.loudness import measure_loudness
from app.audio.spectral import extract_spectral_features

logger = logging.getLogger(__name__)


def _run_stage[T](
    stage: str,
    path: str,
    fn: Callable[[AudioSignal], T],
    signal: AudioSignal,
) -> T:
    """Run an analysis stage, wrapping unexpected errors in AudioAnalysisError."""
    try:
        return fn(signal)
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
        from app.audio.beats import detect_beats

        beats_result = _run_stage("beats", path_str, detect_beats, signal)
    except ImportError:
        logger.debug("essentia/scipy not installed — skipping beats extraction")
    except AudioAnalysisError:
        logger.warning("Beats extraction failed for %s", path, exc_info=True)

    # Phase 2: MFCC extraction (optional, graceful failure)
    mfcc_result = None
    try:
        from app.audio.mfcc import extract_mfcc

        mfcc_result = _run_stage("mfcc", path_str, extract_mfcc, signal)
    except ImportError:
        logger.debug("librosa not installed — skipping MFCC extraction")
    except AudioAnalysisError:
        logger.warning("MFCC extraction failed for %s", path, exc_info=True)

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
        beats=beats_result,
        mfcc=mfcc_result,
    )
