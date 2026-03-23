from __future__ import annotations

from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.candidates import CandidateRepository
from app.repositories.transitions import TransitionRepository
from app.services.base import BaseService
from app.services.transition_scoring import TransitionScoringService
from app.utils.audio.camelot import camelot_distance
from app.utils.audio.feature_conversion import orm_features_to_track_features


class TransitionPersistenceService(BaseService):
    """Bridges TransitionScoringService (v2) -> Transition ORM via repositories."""

    def __init__(
        self,
        features_repo: AudioFeaturesRepository,
        transitions_repo: TransitionRepository,
        candidates_repo: CandidateRepository,
        scorer: TransitionScoringService | None = None,
    ) -> None:
        super().__init__()
        self.features_repo = features_repo
        self.transitions_repo = transitions_repo
        self.candidates_repo = candidates_repo
        self.scorer = scorer or TransitionScoringService()

    async def score_pair(
        self,
        from_track_id: int,
        to_track_id: int,
        run_id: int,
        *,
        groove_sim: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> float:
        """Score a transition between two tracks and persist result.

        Returns the overall transition quality score (0-1).
        """
        feat_a = await self.features_repo.get_by_track(from_track_id)
        if not feat_a:
            msg = f"No features found for track {from_track_id}"
            raise ValueError(msg)

        feat_b = await self.features_repo.get_by_track(to_track_id)
        if not feat_b:
            msg = f"No features found for track {to_track_id}"
            raise ValueError(msg)

        # Convert ORM → domain TrackFeatures via unified converter
        tf_a = orm_features_to_track_features(feat_a)
        tf_b = orm_features_to_track_features(feat_b)

        # Score via v2 scorer
        quality = self.scorer.score_transition(tf_a, tf_b)

        # Persist — compute fields needed by Transition ORM model
        bpm_distance = abs(feat_a.bpm - feat_b.bpm)
        energy_step = feat_b.lufs_i - feat_a.lufs_i
        centroid_gap = abs((feat_a.centroid_mean_hz or 0) - (feat_b.centroid_mean_hz or 0))
        key_dist = float(camelot_distance(feat_a.key_code, feat_b.key_code))

        await self.transitions_repo.create(
            run_id=run_id,
            from_track_id=from_track_id,
            to_track_id=to_track_id,
            overlap_ms=0,
            bpm_distance=bpm_distance,
            energy_step=energy_step,
            centroid_gap_hz=centroid_gap,
            low_conflict_score=0.0,
            overlap_score=0.0,
            groove_similarity=groove_sim,
            key_distance_weighted=key_dist,
            transition_quality=quality,
        )

        return quality

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
