from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from app.utils.audio import AudioSignal  # noqa: E402
from app.utils.audio.loader import load_audio, validate_audio  # noqa: E402


class TestLoadAudio:
    def test_loads_wav_mono(self, wav_file_path: Path) -> None:
        signal = load_audio(wav_file_path)
        assert isinstance(signal, AudioSignal)
        assert signal.sample_rate == 44100
        assert signal.samples.dtype == np.float32
        assert signal.samples.ndim == 1  # mono

    def test_loads_with_custom_sr(self, wav_file_path: Path) -> None:
        signal = load_audio(wav_file_path, target_sr=22050)
        assert signal.sample_rate == 22050

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_audio(Path("/nonexistent/audio.wav"))


class TestValidateAudio:
    def test_valid_signal_passes(self, long_sine_440hz: AudioSignal) -> None:
        validate_audio(long_sine_440hz)  # should not raise

    def test_rejects_silence(self, silence: AudioSignal) -> None:
        with pytest.raises(ValueError, match="silence"):
            validate_audio(silence)

    def test_rejects_too_short(self) -> None:
        short = AudioSignal(
            samples=np.zeros(100, dtype=np.float32),
            sample_rate=44100,
            duration_s=100 / 44100,
        )
        with pytest.raises(ValueError, match="short"):
            validate_audio(short)
