from __future__ import annotations

import contextlib
import json

import numpy as np

from app.core.models.features import TrackAudioFeaturesComputed
from app.domain.audio.camelot import camelot_distance
from app.domain.audio.scoring.transition_score import score_transition
from app.domain.audio.types import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    SpectralResult,
    TransitionScore,
)
from app.infrastructure.repositories.audio.candidates import CandidateRepository
from app.infrastructure.repositories.audio.features import AudioFeaturesRepository
from app.infrastructure.repositories.audio.transitions import TransitionRepository
from app.services.base import BaseService


class TransitionPersistenceService(BaseService):
    """Bridges utils/transition_score -> Transition ORM via repositories."""

    def __init__(
        self,
        features_repo: AudioFeaturesRepository,
        transitions_repo: TransitionRepository,
        candidates_repo: CandidateRepository,
    ) -> None:
        super().__init__()
        self.features_repo = features_repo
        self.transitions_repo = transitions_repo
        self.candidates_repo = candidates_repo

    async def score_pair(
        self,
        from_track_id: int,
        to_track_id: int,
        run_id: int,
        *,
        groove_sim: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> TransitionScore:
        """Score a transition between two tracks and persist result."""
        feat_a = await self.features_repo.get_by_track(from_track_id)
        if not feat_a:
            msg = f"No features found for track {from_track_id}"
            raise ValueError(msg)

        feat_b = await self.features_repo.get_by_track(to_track_id)
        if not feat_b:
            msg = f"No features found for track {to_track_id}"
            raise ValueError(msg)

        # Map ORM -> utils types
        bpm_a, bpm_b = self._to_bpm(feat_a), self._to_bpm(feat_b)
        key_a, key_b = self._to_key(feat_a), self._to_key(feat_b)
        energy_a, energy_b = self._to_energy(feat_a), self._to_energy(feat_b)
        spec_a, spec_b = self._to_spectral(feat_a), self._to_spectral(feat_b)

        # Score via utils
        result = score_transition(
            bpm_a=bpm_a,
            bpm_b=bpm_b,
            key_a=key_a,
            key_b=key_b,
            energy_a=energy_a,
            energy_b=energy_b,
            spectral_a=spec_a,
            spectral_b=spec_b,
            groove_sim=groove_sim,
            weights=weights,
        )

        # Persist
        centroid_gap = abs((feat_a.centroid_mean_hz or 0) - (feat_b.centroid_mean_hz or 0))
        await self.transitions_repo.create(
            run_id=run_id,
            from_track_id=from_track_id,
            to_track_id=to_track_id,
            overlap_ms=0,
            bpm_distance=result.bpm_distance,
            energy_step=result.energy_step,
            centroid_gap_hz=centroid_gap,
            low_conflict_score=result.low_conflict_score,
            overlap_score=result.overlap_score,
            groove_similarity=result.groove_similarity,
            key_distance_weighted=result.key_distance_weighted,
            transition_quality=result.transition_quality,
        )

        return result

    async def create_candidate(
        self,
        from_track_id: int,
        to_track_id: int,
        run_id: int,
    ) -> None:
        """Pre-filter stage 1: create lightweight candidate from features."""
        feat_a = await self.features_repo.get_by_track(from_track_id)
        feat_b = await self.features_repo.get_by_track(to_track_id)
        if not feat_a or not feat_b:
            return

        bpm_dist = abs(feat_a.bpm - feat_b.bpm)
        key_dist = float(camelot_distance(feat_a.key_code, feat_b.key_code))
        energy_delta = (feat_b.energy_mean or 0) - (feat_a.energy_mean or 0)

        await self.candidates_repo.create(
            from_track_id=from_track_id,
            to_track_id=to_track_id,
            run_id=run_id,
            bpm_distance=bpm_dist,
            key_distance=key_dist,
            energy_delta=energy_delta,
            is_fully_scored=False,
        )

    @staticmethod
    def _to_bpm(feat: TrackAudioFeaturesComputed) -> BpmResult:
        return BpmResult(
            bpm=feat.bpm,
            confidence=feat.tempo_confidence,
            stability=feat.bpm_stability,
            is_variable=feat.is_variable_tempo,
        )

    @staticmethod
    def _to_key(feat: TrackAudioFeaturesComputed) -> KeyResult:
        chroma = np.zeros(12, dtype=np.float32)
        if feat.chroma:
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                chroma = np.array(json.loads(feat.chroma), dtype=np.float32)
        pitch_class = feat.key_code // 2
        mode = feat.key_code % 2
        pitch_names = [
            "C",
            "C#",
            "D",
            "D#",
            "E",
            "F",
            "F#",
            "G",
            "G#",
            "A",
            "A#",
            "B",
        ]
        return KeyResult(
            key=pitch_names[pitch_class],
            scale="major" if mode == 1 else "minor",
            key_code=feat.key_code,
            confidence=feat.key_confidence,
            is_atonal=feat.is_atonal,
            chroma=chroma,
            chroma_entropy=feat.chroma_entropy if feat.chroma_entropy is not None else 0.5,
        )

    @staticmethod
    def _to_energy(feat: TrackAudioFeaturesComputed) -> BandEnergyResult:
        return BandEnergyResult(
            sub=feat.sub_energy or 0.0,
            low=feat.low_energy or 0.0,
            low_mid=feat.lowmid_energy or 0.0,
            mid=feat.mid_energy or 0.0,
            high_mid=feat.highmid_energy or 0.0,
            high=feat.high_energy or 0.0,
            low_high_ratio=feat.low_high_ratio or 0.0,
            sub_lowmid_ratio=feat.sub_lowmid_ratio or 0.0,
        )

    @staticmethod
    def _to_spectral(feat: TrackAudioFeaturesComputed) -> SpectralResult:
        return SpectralResult(
            centroid_mean_hz=feat.centroid_mean_hz or 0.0,
            rolloff_85_hz=feat.rolloff_85_hz or 0.0,
            rolloff_95_hz=feat.rolloff_95_hz or 0.0,
            flatness_mean=feat.flatness_mean or 0.0,
            flux_mean=feat.flux_mean or 0.0,
            flux_std=feat.flux_std or 0.0,
            contrast_mean_db=feat.contrast_mean_db or 0.0,
            slope_db_per_oct=feat.slope_db_per_oct or 0.0,
            hnr_mean_db=feat.hnr_mean_db or 0.0,
        )
