from __future__ import annotations

import numpy as np
import pytest

scipy = pytest.importorskip("scipy")

from app.audio import AudioSignal, BandEnergyResult  # noqa: E402
from app.domain.audio.dsp.energy import compute_band_energies  # noqa: E402

SR = 44100


@pytest.fixture
def low_freq_signal() -> AudioSignal:
    """5-second 100 Hz sine — energy should concentrate in 'low' band (60-200 Hz)."""
    duration = 5.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 100.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture
def high_freq_signal() -> AudioSignal:
    """5-second 8000 Hz sine — energy should concentrate in 'high' band (6000-12000 Hz)."""
    duration = 5.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 8000.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


class TestComputeBandEnergies:
    def test_returns_band_energy_result(self, long_sine_440hz: AudioSignal) -> None:
        result = compute_band_energies(long_sine_440hz)
        assert isinstance(result, BandEnergyResult)

    def test_values_between_0_and_1(self, long_sine_440hz: AudioSignal) -> None:
        result = compute_band_energies(long_sine_440hz)
        for field in ("sub", "low", "low_mid", "mid", "high_mid", "high"):
            val = getattr(result, field)
            assert 0.0 <= val <= 1.0, f"{field}={val} out of range"

    def test_low_freq_concentrated_in_low_band(self, low_freq_signal: AudioSignal) -> None:
        result = compute_band_energies(low_freq_signal)
        assert result.low > result.high
        assert result.low > result.mid

    def test_high_freq_concentrated_in_high_band(self, high_freq_signal: AudioSignal) -> None:
        result = compute_band_energies(high_freq_signal)
        assert result.high > result.low
        assert result.high > result.sub
