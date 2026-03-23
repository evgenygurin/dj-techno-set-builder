from __future__ import annotations

import numpy as np
import pytest

librosa = pytest.importorskip("librosa")

from app.audio import AudioSignal  # noqa: E402
from app.audio.mfcc import MfccResult, extract_mfcc  # noqa: E402

SR = 44100


@pytest.fixture(scope="module")
def tone_1s() -> AudioSignal:
    """1.5-second 440 Hz sine wave."""
    duration = 1.5
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    samples = (0.8 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture(scope="module")
def noise_1s() -> AudioSignal:
    """1.5-second white noise."""
    rng = np.random.default_rng(42)
    duration = 1.5
    samples = (0.3 * rng.standard_normal(int(SR * duration))).astype(np.float32)
    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


@pytest.fixture(scope="module")
def mfcc_tone(tone_1s: AudioSignal) -> MfccResult:
    """Compute MFCC once for all tests in this module."""
    return extract_mfcc(tone_1s)


class TestExtractMfcc:
    def test_returns_mfcc_result(self, mfcc_tone: MfccResult) -> None:
        assert hasattr(mfcc_tone, "coefficients")
        assert len(mfcc_tone.coefficients) == 13
        assert mfcc_tone.n_mfcc == 13

    def test_coefficients_are_finite(self, mfcc_tone: MfccResult) -> None:
        for c in mfcc_tone.coefficients:
            assert np.isfinite(c), f"Non-finite MFCC coefficient: {c}"

    def test_different_signals_different_mfcc(
        self, mfcc_tone: MfccResult, noise_1s: AudioSignal
    ) -> None:
        """Sine tone and white noise must produce different MFCC vectors."""
        mfcc_noise = extract_mfcc(noise_1s)

        vec_a = np.array(mfcc_tone.coefficients)
        vec_b = np.array(mfcc_noise.coefficients)

        # Cosine similarity should be noticeably less than 1.0
        cos_sim = float(
            np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-10)
        )
        assert cos_sim < 0.95, f"Expected different MFCCs, got cosine similarity {cos_sim:.3f}"

    def test_same_signal_identical_mfcc(self, tone_1s: AudioSignal) -> None:
        """Deterministic: same input -> same output."""
        a = extract_mfcc(tone_1s)
        b = extract_mfcc(tone_1s)
        assert a.coefficients == b.coefficients
