from __future__ import annotations

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.audio import AudioSignal, BeatsResult  # noqa: E402
from app.audio.beats import detect_beats  # noqa: E402

SR = 44100


@pytest.fixture
def kick_pattern() -> AudioSignal:
    """10-second 4/4 kick pattern at 140 BPM with sub-bass energy.

    Simulates a techno kick: short burst at 50 Hz every beat.
    """
    duration = 10.0
    bpm = 140.0
    samples = np.zeros(int(SR * duration), dtype=np.float32)
    interval = int(60.0 / bpm * SR)
    kick_len = int(0.03 * SR)  # 30ms kick

    for i in range(0, len(samples), interval):
        end = min(i + kick_len, len(samples))
        t = np.arange(end - i) / SR
        # Sub-bass sine burst with fast decay
        kick = 0.9 * np.sin(2 * np.pi * 50.0 * t) * np.exp(-t * 40)
        samples[i:end] += kick.astype(np.float32)

    return AudioSignal(samples=samples, sample_rate=SR, duration_s=duration)


class TestDetectBeats:
    def test_returns_beats_result(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert isinstance(result, BeatsResult)

    def test_beat_count_reasonable(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        # 10s at 140 BPM ≈ 23 beats
        assert 15 <= len(result.beat_times) <= 30

    def test_beats_sorted(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert np.all(np.diff(result.beat_times) > 0)

    def test_downbeats_subset_of_beats(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        # Every downbeat should be close to some beat
        for db in result.downbeat_times:
            dists = np.abs(result.beat_times - db)
            assert np.min(dists) < 0.05  # within 50ms

    def test_onset_rate_range(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert result.onset_rate_mean > 0
        assert result.onset_rate_max >= result.onset_rate_mean

    def test_pulse_clarity_range(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert 0.0 <= result.pulse_clarity <= 1.0

    def test_kick_prominence_range(self, kick_pattern: AudioSignal) -> None:
        result = detect_beats(kick_pattern)
        assert 0.0 <= result.kick_prominence <= 1.0

    def test_hp_ratio_positive(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert result.hp_ratio >= 0.0

    def test_onset_envelope_length(self, click_140bpm: AudioSignal) -> None:
        result = detect_beats(click_140bpm)
        assert len(result.onset_envelope) > 0

    def test_kick_pattern_has_high_pulse_clarity(self, kick_pattern: AudioSignal) -> None:
        result = detect_beats(kick_pattern)
        # A regular kick pattern should have clear pulse
        assert result.pulse_clarity > 0.3
