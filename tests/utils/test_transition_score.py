from __future__ import annotations

import numpy as np

from app.utils.audio import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    SpectralResult,
)
from app.utils.audio.transition_score import (
    TransitionScore,
    score_transition,
)


def _make_bpm(bpm: float, conf: float = 0.9) -> BpmResult:
    return BpmResult(bpm=bpm, confidence=conf, stability=0.9, is_variable=False)


def _make_key(key_code: int, conf: float = 0.8) -> KeyResult:
    return KeyResult(
        key="C",
        scale="minor",
        key_code=key_code,
        confidence=conf,
        is_atonal=False,
        chroma=np.zeros(12, dtype=np.float32),
    )


def _make_energy(sub: float = 0.5, low: float = 0.5) -> BandEnergyResult:
    return BandEnergyResult(
        sub=sub,
        low=low,
        low_mid=0.4,
        mid=0.3,
        high_mid=0.2,
        high=0.1,
        low_high_ratio=5.0,
        sub_lowmid_ratio=1.0,
    )


def _make_spectral(centroid: float = 1500.0) -> SpectralResult:
    return SpectralResult(
        centroid_mean_hz=centroid,
        rolloff_85_hz=5000.0,
        rolloff_95_hz=8000.0,
        flatness_mean=0.3,
        flux_mean=0.5,
        flux_std=0.1,
        contrast_mean_db=20.0,
    )


class TestScoreTransition:
    def test_returns_transition_score(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
        )
        assert isinstance(result, TransitionScore)

    def test_identical_tracks_high_quality(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
        )
        assert result.transition_quality > 0.8

    def test_large_bpm_gap_low_quality(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(130),
            bpm_b=_make_bpm(150),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
        )
        assert result.transition_quality < 0.6
        assert result.bpm_distance == 20.0

    def test_incompatible_key_lowers_quality(self) -> None:
        # Cm (0) → F#m (12) = Camelot distance 6
        result = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(12),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
        )
        compatible = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
        )
        assert result.transition_quality < compatible.transition_quality

    def test_quality_between_0_and_1(self) -> None:
        result = score_transition(
            bpm_a=_make_bpm(120),
            bpm_b=_make_bpm(160),
            key_a=_make_key(0),
            key_b=_make_key(12),
            energy_a=_make_energy(),
            energy_b=_make_energy(sub=0.9),
            spectral_a=_make_spectral(500),
            spectral_b=_make_spectral(5000),
        )
        assert 0.0 <= result.transition_quality <= 1.0

    def test_groove_similarity_bonus(self) -> None:
        base = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
            groove_sim=0.0,
        )
        with_groove = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(),
            energy_b=_make_energy(),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
            groove_sim=0.95,
        )
        assert with_groove.transition_quality > base.transition_quality

    def test_energy_step_signed(self) -> None:
        """Going from low to high energy should have positive energy_step."""
        result = score_transition(
            bpm_a=_make_bpm(140),
            bpm_b=_make_bpm(140),
            key_a=_make_key(0),
            key_b=_make_key(0),
            energy_a=_make_energy(sub=0.2, low=0.3),
            energy_b=_make_energy(sub=0.8, low=0.9),
            spectral_a=_make_spectral(),
            spectral_b=_make_spectral(),
        )
        assert result.energy_step > 0
