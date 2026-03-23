from __future__ import annotations

import numpy as np

from app.audio._types import AudioSignal, BpmResult

_DEFAULT_MIN_BPM = 80.0
_DEFAULT_MAX_BPM = 200.0
_VARIABLE_TEMPO_THRESHOLD = 5.0  # BPM std dev


def estimate_bpm(
    signal: AudioSignal,
    *,
    min_bpm: float = _DEFAULT_MIN_BPM,
    max_bpm: float = _DEFAULT_MAX_BPM,
) -> BpmResult:
    """Estimate BPM using essentia RhythmExtractor2013 (multifeature method)."""
    import essentia.standard as es

    extractor = es.RhythmExtractor2013(
        method="multifeature",
        minTempo=int(min_bpm),
        maxTempo=int(max_bpm),
    )
    # Returns: bpm, ticks, confidence (scalar), estimates, bpmIntervals
    bpm, _ticks, raw_confidence, _estimates, beats_intervals = extractor(signal.samples)

    confidence = float(np.clip(raw_confidence, 0.0, 1.0))

    # Stability: inverse of tempo variation across beat intervals
    if len(beats_intervals) > 1:
        interval_bpms = 60.0 / beats_intervals
        bpm_std = float(np.std(interval_bpms))
        stability = float(np.clip(1.0 - bpm_std / max_bpm, 0.0, 1.0))
        is_variable = bpm_std > _VARIABLE_TEMPO_THRESHOLD
    else:
        stability = 0.0
        is_variable = False

    return BpmResult(
        bpm=float(np.clip(bpm, min_bpm, max_bpm)),
        confidence=confidence,
        stability=stability,
        is_variable=is_variable,
    )
