from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")
demucs = pytest.importorskip("demucs")

from app.utils.audio import AudioSignal, StemsResult  # noqa: E402
from app.utils.audio.stems import separate_stems  # noqa: E402

SR = 44100


def _all_stems(r: StemsResult) -> tuple[AudioSignal, ...]:
    return (r.drums, r.bass, r.vocals, r.other)


@pytest.fixture(scope="module")
def short_mix() -> AudioSignal:
    """3-second synthetic mix: kick (50Hz) + bass (100Hz) + lead (800Hz) + hats (8kHz)."""
    duration = 3.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (
        0.3 * np.sin(2 * np.pi * 50.0 * t)  # kick
        + 0.3 * np.sin(2 * np.pi * 100.0 * t)  # bass
        + 0.2 * np.sin(2 * np.pi * 800.0 * t)  # lead
        + 0.1 * np.sin(2 * np.pi * 8000.0 * t)  # hats
    ).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture(scope="module")
def stems_result(short_mix: AudioSignal) -> StemsResult:
    """Run separation once for all tests in this module."""
    return separate_stems(short_mix)


class TestSeparateStems:
    def test_returns_stems_result(self, stems_result: StemsResult) -> None:
        assert isinstance(stems_result, StemsResult)

    def test_four_stems_present(self, stems_result: StemsResult) -> None:
        for stem in _all_stems(stems_result):
            assert isinstance(stem, AudioSignal)

    def test_stems_same_sample_rate(
        self, stems_result: StemsResult, short_mix: AudioSignal
    ) -> None:
        for stem in _all_stems(stems_result):
            assert stem.sample_rate == short_mix.sample_rate

    def test_stems_similar_duration(
        self, stems_result: StemsResult, short_mix: AudioSignal
    ) -> None:
        for stem in _all_stems(stems_result):
            # Demucs may pad slightly — allow 0.5s tolerance
            assert abs(stem.duration_s - short_mix.duration_s) < 0.5

    def test_stems_not_all_silent(self, stems_result: StemsResult) -> None:
        total_energy = sum(float(np.mean(s.samples**2)) for s in _all_stems(stems_result))
        assert total_energy > 1e-8
