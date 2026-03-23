from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from app.audio import AudioSignal, AudioValidationError  # noqa: E402
from app.domain.audio.dsp.loader import load_audio, validate_audio  # noqa: E402


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

    def test_stereo_to_mono_mixdown(self, tmp_path: Path) -> None:
        """Stereo WAV should be averaged to mono."""
        sr = 44100
        duration = 2.0
        n = int(sr * duration)
        left = np.ones(n, dtype=np.float32) * 0.5
        right = np.ones(n, dtype=np.float32) * 1.0
        stereo = np.column_stack([left, right])

        path = tmp_path / "stereo.wav"
        soundfile.write(str(path), stereo, sr)

        signal = load_audio(path)
        assert signal.samples.ndim == 1
        # Mono mixdown: mean of 0.5 and 1.0 = 0.75
        assert np.allclose(signal.samples, 0.75, atol=0.01)


class TestValidateAudio:
    def test_valid_signal_passes(self, long_sine_440hz: AudioSignal) -> None:
        validate_audio(long_sine_440hz)  # should not raise

    def test_rejects_silence(self, silence: AudioSignal) -> None:
        with pytest.raises(AudioValidationError, match="silence"):
            validate_audio(silence)

    def test_rejects_too_short(self) -> None:
        short = AudioSignal(
            samples=np.zeros(100, dtype=np.float32),
            sample_rate=44100,
            duration_s=100 / 44100,
        )
        with pytest.raises(AudioValidationError, match="short"):
            validate_audio(short)

    def test_rejects_nan(self) -> None:
        samples = np.array([0.5, float("nan"), 0.3] * 15000, dtype=np.float32)
        signal = AudioSignal(samples=samples, sample_rate=44100, duration_s=1.02)
        with pytest.raises(AudioValidationError, match="NaN"):
            validate_audio(signal)
