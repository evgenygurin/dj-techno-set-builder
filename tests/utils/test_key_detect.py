from __future__ import annotations

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, KeyResult  # noqa: E402
from app.utils.audio.key_detect import detect_key  # noqa: E402

SR = 44100


@pytest.fixture
def a_major_chord() -> AudioSignal:
    """3-second A major chord (A4 + C#5 + E5) — should detect A major."""
    duration = 3.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (
        0.4 * np.sin(2 * np.pi * 440.0 * t)  # A4
        + 0.3 * np.sin(2 * np.pi * 554.37 * t)  # C#5
        + 0.3 * np.sin(2 * np.pi * 659.25 * t)  # E5
    ).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


class TestDetectKey:
    def test_returns_key_result(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert isinstance(result, KeyResult)

    def test_key_code_range(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert 0 <= result.key_code <= 23

    def test_confidence_range(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert 0.0 <= result.confidence <= 1.0

    def test_chroma_shape(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert result.chroma.shape == (12,)

    def test_scale_is_valid(self, long_sine_440hz: AudioSignal) -> None:
        result = detect_key(long_sine_440hz)
        assert result.scale in ("minor", "major")

    def test_a_major_detection(self, a_major_chord: AudioSignal) -> None:
        result = detect_key(a_major_chord)
        # A major → key = "A", scale = "major", key_code = 19
        assert result.key == "A"
        assert result.scale == "major"
        assert result.key_code == 19

    def test_chroma_entropy_returned(self, long_sine_440hz: AudioSignal) -> None:
        """KeyResult must include normalized chroma entropy [0, 1]."""
        result = detect_key(long_sine_440hz)
        assert hasattr(result, "chroma_entropy")
        assert 0.0 <= result.chroma_entropy <= 1.0
