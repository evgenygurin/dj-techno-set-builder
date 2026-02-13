from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pytest
import soundfile as sf
from numpy.typing import NDArray

from app.utils.audio import AudioSignal

SR = 44100


def _sine(freq: float, duration: float, sr: int = SR) -> NDArray[np.float32]:
    """Generate a mono sine wave."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (0.8 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _click_track(bpm: float, duration: float, sr: int = SR) -> NDArray[np.float32]:
    """Generate a click track at given BPM."""
    samples = int(sr * duration)
    audio = np.zeros(samples, dtype=np.float32)
    interval = int(60.0 / bpm * sr)
    click_len = int(0.005 * sr)  # 5ms click
    for i in range(0, samples, interval):
        end = min(i + click_len, samples)
        audio[i:end] = 0.9
    return audio


@pytest.fixture
def sine_440hz() -> AudioSignal:
    """1-second 440 Hz sine wave (A4)."""
    samples = _sine(440.0, 1.0)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=1.0)


@pytest.fixture
def click_140bpm() -> AudioSignal:
    """10-second click track at 140 BPM."""
    duration = 10.0
    samples = _click_track(140.0, duration)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture
def long_sine_440hz() -> AudioSignal:
    """30-second 440 Hz sine wave — for loudness / spectral tests."""
    duration = 30.0
    samples = _sine(440.0, duration)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture
def silence() -> AudioSignal:
    """1-second silence."""
    samples = np.zeros(SR, dtype=np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=1.0)


@pytest.fixture
def wav_file_path(long_sine_440hz: AudioSignal) -> Generator[Path, None, None]:
    """Temporary WAV file for loader tests."""
    with NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)
    sf.write(str(path), long_sine_440hz.samples, long_sine_440hz.sample_rate)
    yield path
    path.unlink(missing_ok=True)
