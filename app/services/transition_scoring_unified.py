"""Unified transition scoring — single entry-point for GA / API / MCP.

All production paths MUST use this service (or call
``orm_features_to_track_features`` + ``TransitionScoringService`` directly)
to guarantee consistent results across entry-points.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.repositories.audio_features import AudioFeaturesRepository
from app.services.camelot_lookup import CamelotLookupService
from app.services.transition_scoring import TransitionScoringService
from app.utils.audio.feature_conversion import orm_features_to_track_features

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.features import TrackAudioFeaturesComputed
    from app.services.transition_scoring import TrackFeatures


class UnifiedTransitionScoringService:
    """DB-backed transition scoring with Camelot lookup + lazy initialisation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._features_repo = AudioFeaturesRepository(session)
        self._scorer: TransitionScoringService | None = None

    # ------------------------------------------------------------------
    # Lazy builder
    # ------------------------------------------------------------------

    async def _get_scorer(self) -> TransitionScoringService:
        if self._scorer is not None:
            return self._scorer
        lookup = await CamelotLookupService(self._session).build_lookup_table()
        self._scorer = TransitionScoringService(camelot_lookup=lookup)
        return self._scorer

    # ------------------------------------------------------------------
    # Public API — by track IDs
    # ------------------------------------------------------------------

    async def score_by_ids(self, from_id: int, to_id: int) -> float:
        """Return overall transition score ``[0, 1]`` between two track IDs."""
        feat_a, feat_b = await self._load_pair(from_id, to_id)
        return await self.score_by_features(feat_a, feat_b)

    async def score_components_by_ids(self, from_id: int, to_id: int) -> dict[str, float]:
        """Return per-component breakdown ``{total, bpm, harmonic, …}``."""
        feat_a, feat_b = await self._load_pair(from_id, to_id)
        return await self.score_components_by_features(feat_a, feat_b)

    # ------------------------------------------------------------------
    # Public API — by ORM feature objects (avoids extra DB round-trip)
    # ------------------------------------------------------------------

    async def score_by_features(
        self,
        feat_a: TrackAudioFeaturesComputed,
        feat_b: TrackAudioFeaturesComputed,
    ) -> float:
        scorer = await self._get_scorer()
        tf_a = orm_features_to_track_features(feat_a)
        tf_b = orm_features_to_track_features(feat_b)
        return scorer.score_transition(tf_a, tf_b)

    async def score_components_by_features(
        self,
        feat_a: TrackAudioFeaturesComputed,
        feat_b: TrackAudioFeaturesComputed,
    ) -> dict[str, float]:
        scorer = await self._get_scorer()
        tf_a = orm_features_to_track_features(feat_a)
        tf_b = orm_features_to_track_features(feat_b)
        return _score_components(scorer, tf_a, tf_b)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_pair(
        self, from_id: int, to_id: int
    ) -> tuple[TrackAudioFeaturesComputed, TrackAudioFeaturesComputed]:
        feat_a = await self._features_repo.get_by_track(from_id)
        if not feat_a:
            msg = f"No features found for track {from_id}"
            raise ValueError(msg)
        feat_b = await self._features_repo.get_by_track(to_id)
        if not feat_b:
            msg = f"No features found for track {to_id}"
            raise ValueError(msg)
        return feat_a, feat_b


# ------------------------------------------------------------------
# Free helper — kept outside the class so it's easy to test
# ------------------------------------------------------------------


def _score_components(
    scorer: TransitionScoringService,
    tf_a: TrackFeatures,
    tf_b: TrackFeatures,
) -> dict[str, float]:
    """Return rounded component dict for a pair of ``TrackFeatures``."""
    return {
        "total": round(scorer.score_transition(tf_a, tf_b), 4),
        "bpm": round(scorer.score_bpm(tf_a.bpm, tf_b.bpm), 4),
        "harmonic": round(
            scorer.score_harmonic(
                tf_a.key_code,
                tf_b.key_code,
                tf_a.harmonic_density,
                tf_b.harmonic_density,
                tf_a.hnr_db,
                tf_b.hnr_db,
            ),
            4,
        ),
        "energy": round(scorer.score_energy(tf_a.energy_lufs, tf_b.energy_lufs), 4),
        "spectral": round(scorer.score_spectral(tf_a, tf_b), 4),
        "groove": round(
            scorer.score_groove(
                tf_a.onset_rate,
                tf_b.onset_rate,
                tf_a.kick_prominence,
                tf_b.kick_prominence,
            ),
            4,
        ),
        "structure": round(
            scorer.score_structure(tf_a.last_section, tf_b.first_section), 4
        ),
    }
