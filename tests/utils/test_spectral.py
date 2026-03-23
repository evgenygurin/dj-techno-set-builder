from __future__ import annotations

import math

import pytest

essentia = pytest.importorskip("essentia")

from app.audio import AudioSignal, SpectralResult  # noqa: E402
from app.domain.audio.dsp.spectral import extract_spectral_features  # noqa: E402


@pytest.fixture(scope="module")
def spectral_result(long_sine_440hz: AudioSignal) -> SpectralResult:
    """Compute spectral features once for all tests in this module."""
    return extract_spectral_features(long_sine_440hz)


class TestExtractSpectralFeatures:
    def test_returns_spectral_result(self, spectral_result: SpectralResult) -> None:
        assert isinstance(spectral_result, SpectralResult)

    def test_centroid_positive(self, spectral_result: SpectralResult) -> None:
        assert spectral_result.centroid_mean_hz > 0

    def test_sine_centroid_near_440(self, spectral_result: SpectralResult) -> None:
        # Centroid of a pure sine ~ its frequency
        assert 400.0 <= spectral_result.centroid_mean_hz <= 500.0

    def test_rolloff_above_centroid(self, spectral_result: SpectralResult) -> None:
        assert spectral_result.rolloff_85_hz >= spectral_result.centroid_mean_hz

    def test_flatness_range(self, spectral_result: SpectralResult) -> None:
        assert 0.0 <= spectral_result.flatness_mean <= 1.0

    def test_flux_non_negative(self, spectral_result: SpectralResult) -> None:
        assert spectral_result.flux_mean >= 0
        assert spectral_result.flux_std >= 0

    def test_slope_finite(self, spectral_result: SpectralResult) -> None:
        assert math.isfinite(spectral_result.slope_db_per_oct)
