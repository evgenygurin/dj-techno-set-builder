"""Unified transition scoring service that works across all entry points.

This module provides a single interface for transition scoring that ensures
consistent results whether accessed via API, GA, or MCP paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.features import TrackAudioFeaturesComputed  
from app.repositories.audio_features import AudioFeaturesRepository
from app.services.base import BaseService
from app.services.camelot_lookup import CamelotLookupService
from app.services.transition_scoring import TrackFeatures, TransitionScoringService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class UnifiedTransitionScoringService(BaseService):
    """Unified transition scoring service with consistent DB-backed Camelot lookup."""
    
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self.session = session
        self.features_repo = AudioFeaturesRepository(session)
        self._scorer: TransitionScoringService | None = None
        self._built = False
    
    async def _build_scorer(self) -> TransitionScoringService:
        """Build scorer with DB-backed Camelot lookup."""
        if self._scorer is not None and self._built:
            return self._scorer
            
        # Build DB-backed Camelot lookup
        camelot_service = CamelotLookupService(self.session)
        lookup_table = await camelot_service.build_lookup_table()
        
        # Initialize unified scorer
        self._scorer = TransitionScoringService(camelot_lookup=lookup_table)
        self._built = True
        return self._scorer
        
    async def score_transition_by_ids(self, from_track_id: int, to_track_id: int) -> float:
        """Score transition between two tracks by their IDs.
        
        Returns:
            Transition quality score [0, 1]
        """
        feat_a = await self.features_repo.get_by_track(from_track_id)
        if not feat_a:
            raise ValueError(f"No features found for track {from_track_id}")
            
        feat_b = await self.features_repo.get_by_track(to_track_id)  
        if not feat_b:
            raise ValueError(f"No features found for track {to_track_id}")
            
        return await self.score_transition_by_features(feat_a, feat_b)
        
    async def score_transition_by_features(
        self, feat_a: TrackAudioFeaturesComputed, feat_b: TrackAudioFeaturesComputed
    ) -> float:
        """Score transition between two tracks by their feature objects.
        
        Returns:
            Transition quality score [0, 1] 
        """
        scorer = await self._build_scorer()
        
        # Convert ORM features to TransitionScoringService format
        tf_a = self._to_track_features(feat_a)
        tf_b = self._to_track_features(feat_b)
        
        return scorer.score_transition(tf_a, tf_b)
        
    async def score_transition_components_by_ids(
        self, from_track_id: int, to_track_id: int
    ) -> dict[str, float]:
        """Score transition with component breakdown by track IDs.
        
        Returns:
            Dict with keys: total, bpm, harmonic, energy, spectral, groove
        """
        feat_a = await self.features_repo.get_by_track(from_track_id)
        if not feat_a:
            raise ValueError(f"No features found for track {from_track_id}")
            
        feat_b = await self.features_repo.get_by_track(to_track_id)
        if not feat_b:
            raise ValueError(f"No features found for track {to_track_id}")
            
        return await self.score_transition_components_by_features(feat_a, feat_b)
        
    async def score_transition_components_by_features(
        self, feat_a: TrackAudioFeaturesComputed, feat_b: TrackAudioFeaturesComputed
    ) -> dict[str, float]:
        """Score transition with component breakdown by feature objects.
        
        Returns:
            Dict with keys: total, bpm, harmonic, energy, spectral, groove
        """
        scorer = await self._build_scorer()
        
        # Convert ORM features to TransitionScoringService format
        tf_a = self._to_track_features(feat_a)
        tf_b = self._to_track_features(feat_b)
        
        # Compute all components
        bpm_score = scorer.score_bpm(tf_a.bpm, tf_b.bpm)
        harmonic_score = scorer.score_harmonic(
            tf_a.key_code, tf_b.key_code, tf_a.harmonic_density, tf_b.harmonic_density
        )
        energy_score = scorer.score_energy(tf_a.energy_lufs, tf_b.energy_lufs)  
        spectral_score = scorer.score_spectral(tf_a, tf_b)
        groove_score = scorer.score_groove(tf_a.onset_rate, tf_b.onset_rate)
        total_score = scorer.score_transition(tf_a, tf_b)
        
        return {
            "total": round(total_score, 4),
            "bpm": round(bpm_score, 4), 
            "harmonic": round(harmonic_score, 4),
            "energy": round(energy_score, 4),
            "spectral": round(spectral_score, 4),
            "groove": round(groove_score, 4),
        }
        
    @staticmethod
    def _to_track_features(feat: TrackAudioFeaturesComputed) -> TrackFeatures:
        """Convert ORM features to TransitionScoringService TrackFeatures format."""
        # Compute harmonic density from key confidence
        harmonic_density = feat.key_confidence or 0.5
        
        # Compute band ratios from energy bands  
        low = feat.low_energy or 0.33
        mid = feat.mid_energy or 0.33
        high = feat.high_energy or 0.34
        total = low + mid + high
        if total > 0:
            band_ratios = [low / total, mid / total, high / total]
        else:
            band_ratios = [0.33, 0.33, 0.34]
            
        return TrackFeatures(
            bpm=feat.bpm,
            energy_lufs=feat.lufs_i,
            key_code=feat.key_code or 0,
            harmonic_density=harmonic_density,
            centroid_hz=feat.centroid_mean_hz or 2000.0,
            band_ratios=band_ratios,
            onset_rate=feat.onset_rate_mean or 5.0,
        )