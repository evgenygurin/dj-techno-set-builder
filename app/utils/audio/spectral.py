from __future__ import annotations

import numpy as np

from app.utils.audio._types import AudioSignal, SpectralResult

_FRAME_SIZE = 2048
_HOP_SIZE = 512


def extract_spectral_features(
    signal: AudioSignal,
    *,
    frame_size: int = _FRAME_SIZE,
    hop_size: int = _HOP_SIZE,
) -> SpectralResult:
    """Extract spectral descriptors using essentia frame-by-frame analysis."""
    import essentia.standard as es

    sr = signal.sample_rate
    half_sr = float(sr) / 2.0

    w = es.Windowing(type="hann")
    spectrum = es.Spectrum(size=frame_size)
    centroid = es.Centroid(range=half_sr)
    rolloff85 = es.RollOff(cutoff=0.85, sampleRate=float(sr))
    rolloff95 = es.RollOff(cutoff=0.95, sampleRate=float(sr))
    flatness = es.Flatness()
    flux = es.Flux()
    contrast = es.SpectralContrast(
        sampleRate=float(sr),
        frameSize=frame_size,
    )

    centroids: list[float] = []
    rolloffs85: list[float] = []
    rolloffs95: list[float] = []
    flatnesses: list[float] = []
    fluxes: list[float] = []
    contrasts: list[float] = []

    for frame in es.FrameGenerator(signal.samples, frameSize=frame_size, hopSize=hop_size):
        windowed = w(frame)
        spec = spectrum(windowed)

        centroids.append(float(centroid(spec)))
        rolloffs85.append(float(rolloff85(spec)))
        rolloffs95.append(float(rolloff95(spec)))
        flatnesses.append(float(flatness(spec)))
        fluxes.append(float(flux(spec)))

        sc, _sv = contrast(spec)
        contrasts.append(float(np.mean(sc)))

    return SpectralResult(
        centroid_mean_hz=float(np.mean(centroids)) if centroids else 0.0,
        rolloff_85_hz=float(np.mean(rolloffs85)) if rolloffs85 else 0.0,
        rolloff_95_hz=float(np.mean(rolloffs95)) if rolloffs95 else 0.0,
        flatness_mean=float(np.clip(np.mean(flatnesses), 0.0, 1.0)) if flatnesses else 0.0,
        flux_mean=float(np.mean(fluxes)) if fluxes else 0.0,
        flux_std=float(np.std(fluxes)) if fluxes else 0.0,
        contrast_mean_db=float(np.mean(contrasts)) if contrasts else 0.0,
    )
