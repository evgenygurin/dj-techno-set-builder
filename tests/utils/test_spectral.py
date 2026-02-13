from __future__ import annotations

import math

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, SpectralResult  # noqa: E402
from app.utils.audio.spectral import extract_spectral_features  # noqa: E402


class TestExtractSpectralFeatures:
    def test_returns_spectral_result(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert isinstance(result, SpectralResult)

    def test_centroid_positive(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert result.centroid_mean_hz > 0

    def test_sine_centroid_near_440(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        # Centroid of a pure sine ~ its frequency
        assert 400.0 <= result.centroid_mean_hz <= 500.0

    def test_rolloff_above_centroid(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert result.rolloff_85_hz >= result.centroid_mean_hz

    def test_flatness_range(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert 0.0 <= result.flatness_mean <= 1.0

    def test_flux_non_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert result.flux_mean >= 0
        assert result.flux_std >= 0

    def test_slope_finite(self, long_sine_440hz: AudioSignal) -> None:
        result = extract_spectral_features(long_sine_440hz)
        assert math.isfinite(result.slope_db_per_oct)
