"""MFCC extraction for timbral similarity scoring.

Uses librosa to compute mean MFCC coefficients (c1-c13) across all frames.
These 13 coefficients capture the spectral envelope — the #1 predictor of
"sounds right together" per Kell & Tzanetakis (ISMIR 2013).
"""

from __future__ import annotations

from app.audio._types import AudioSignal, MfccResult


def extract_mfcc(
    signal: AudioSignal,
    *,
    n_mfcc: int = 14,
    n_fft: int = 2048,
    hop_length: int = 512,
) -> MfccResult:
    """Extract mean MFCC vector from audio signal.

    Args:
        signal: Mono audio signal.
        n_mfcc: Number of MFCCs to compute (14, then skip c0 → 13 used).
        n_fft: FFT window size.
        hop_length: Hop between frames.

    Returns:
        MfccResult with 13 mean coefficients (c1-c13).
    """
    import librosa
    import numpy as np

    # librosa expects float32 numpy array
    mfcc_matrix = librosa.feature.mfcc(
        y=signal.samples,
        sr=signal.sample_rate,
        n_mfcc=n_mfcc,
        n_fft=n_fft,
        hop_length=hop_length,
    )

    # Skip c0 (energy), take c1-c13
    mfcc_no_c0 = mfcc_matrix[1:]  # shape: (n_mfcc-1, n_frames)

    # Mean across time frames
    mean_mfcc = np.mean(mfcc_no_c0, axis=1)  # shape: (13,)

    return MfccResult(
        coefficients=[float(v) for v in mean_mfcc],
        n_mfcc=len(mean_mfcc),
    )
