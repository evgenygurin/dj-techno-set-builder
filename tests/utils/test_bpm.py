from __future__ import annotations

import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import AudioSignal, BpmResult  # noqa: E402
from app.utils.audio.bpm import estimate_bpm  # noqa: E402


class TestEstimateBpm:
    def test_returns_bpm_result(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        assert isinstance(result, BpmResult)

    def test_detects_140bpm(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        # Allow ±5 BPM tolerance for synthetic click track
        assert 135.0 <= result.bpm <= 145.0

    def test_confidence_range(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        assert 0.0 <= result.confidence <= 1.0
        assert 0.0 <= result.stability <= 1.0

    def test_stable_tempo_not_variable(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm)
        assert not result.is_variable

    def test_clamps_to_range(self, click_140bpm: AudioSignal) -> None:
        result = estimate_bpm(click_140bpm, min_bpm=120, max_bpm=160)
        assert 120.0 <= result.bpm <= 160.0
