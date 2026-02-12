from __future__ import annotations

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, LoudnessResult  # noqa: E402
from app.utils.audio.loudness import measure_loudness  # noqa: E402


class TestMeasureLoudness:
    def test_returns_loudness_result(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert isinstance(result, LoudnessResult)

    def test_lufs_i_is_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        # A sine wave at 0.8 amplitude should have negative LUFS
        assert result.lufs_i < 0

    def test_rms_is_negative_dbfs(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert result.rms_dbfs < 0

    def test_crest_factor_non_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert result.crest_factor_db >= 0

    def test_lra_non_negative(self, long_sine_440hz: AudioSignal) -> None:
        result = measure_loudness(long_sine_440hz)
        assert result.lra_lu >= 0
