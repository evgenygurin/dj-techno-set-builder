from __future__ import annotations

import numpy as np
import pytest

librosa = pytest.importorskip("librosa")

from app.utils.audio import AudioSignal  # noqa: E402
from app.utils.audio.mfcc import extract_mfcc  # noqa: E402

SR = 44100


@pytest.fixture
def tone_5s() -> AudioSignal:
    """5-second 440 Hz sine wave."""
    duration = 5.0
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture
def noise_5s() -> AudioSignal:
    """5-second white noise."""
    rng = np.random.default_rng(42)
    duration = 5.0
    samples = (0.3 * rng.standard_normal(int(SR * duration))).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


class TestExtractMfcc:
    def test_returns_mfcc_result(self, tone_5s: AudioSignal) -> None:
        result = extract_mfcc(tone_5s)
        assert hasattr(result, "coefficients")
        assert len(result.coefficients) == 13
        assert result.n_mfcc == 13

    def test_coefficients_are_finite(self, tone_5s: AudioSignal) -> None:
        result = extract_mfcc(tone_5s)
        for c in result.coefficients:
            assert np.isfinite(c), f"Non-finite MFCC coefficient: {c}"

    def test_different_signals_different_mfcc(
        self, tone_5s: AudioSignal, noise_5s: AudioSignal
    ) -> None:
        """Sine tone and white noise must produce different MFCC vectors."""
        mfcc_tone = extract_mfcc(tone_5s)
        mfcc_noise = extract_mfcc(noise_5s)

        vec_a = np.array(mfcc_tone.coefficients)
        vec_b = np.array(mfcc_noise.coefficients)

        # Cosine similarity should be noticeably less than 1.0
        cos_sim = float(
            np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-10)
        )
        assert cos_sim < 0.95, f"Expected different MFCCs, got cosine similarity {cos_sim:.3f}"

    def test_same_signal_identical_mfcc(self, tone_5s: AudioSignal) -> None:
        """Deterministic: same input -> same output."""
        a = extract_mfcc(tone_5s)
        b = extract_mfcc(tone_5s)
        assert a.coefficients == b.coefficients
