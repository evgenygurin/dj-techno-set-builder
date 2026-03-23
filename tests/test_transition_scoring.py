from unittest.mock import AsyncMock, MagicMock

import pytest

essentia = pytest.importorskip("essentia")

from app.core.models.features import TrackAudioFeaturesComputed  # noqa: E402
from app.services.audio.persistence import TransitionPersistenceService  # noqa: E402


def _mock_features(track_id: int, bpm: float = 140.0, key_code: int = 18) -> MagicMock:
    """Create a mock TrackAudioFeaturesComputed row."""
    feat = MagicMock(spec=TrackAudioFeaturesComputed)
    feat.track_id = track_id
    feat.bpm = bpm
    feat.tempo_confidence = 0.9
    feat.bpm_stability = 0.95
    feat.is_variable_tempo = False
    feat.key_code = key_code
    feat.key_confidence = 0.85
    feat.is_atonal = False
    feat.sub_energy = 0.3
    feat.low_energy = 0.7
    feat.lowmid_energy = 0.5
    feat.mid_energy = 0.4
    feat.highmid_energy = 0.2
    feat.high_energy = 0.1
    feat.low_high_ratio = 7.0
    feat.sub_lowmid_ratio = 0.6
    feat.centroid_mean_hz = 1500.0
    feat.rolloff_85_hz = 5000.0
    feat.rolloff_95_hz = 8000.0
    feat.flatness_mean = 0.3
    feat.flux_mean = 0.5
    feat.flux_std = 0.1
    feat.contrast_mean_db = 20.0
    feat.energy_mean = 0.4
    feat.chroma = "[0,0,0,0,0,0,0,0,0,0,0,0]"
    feat.chroma_entropy = 0.5
    return feat


class TestTransitionPersistenceService:
    @pytest.fixture
    def service(self) -> TransitionPersistenceService:
        features_repo = MagicMock()
        transitions_repo = MagicMock()
        transitions_repo.create = AsyncMock()
        candidates_repo = MagicMock()
        candidates_repo.create = AsyncMock()
        return TransitionPersistenceService(features_repo, transitions_repo, candidates_repo)

    async def test_score_pair(self, service: TransitionPersistenceService) -> None:
        feat_a = _mock_features(1, bpm=140.0, key_code=18)
        feat_b = _mock_features(2, bpm=142.0, key_code=18)
        service.features_repo.get_by_track = AsyncMock(side_effect=[feat_a, feat_b])

        result = await service.score_pair(
            from_track_id=1,
            to_track_id=2,
            run_id=1,
        )
        assert result.transition_quality > 0
        assert result.bpm_distance == pytest.approx(2.0)
        service.transitions_repo.create.assert_awaited_once()

    async def test_score_pair_missing_features(
        self, service: TransitionPersistenceService
    ) -> None:
        service.features_repo.get_by_track = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="No features"):
            await service.score_pair(from_track_id=1, to_track_id=2, run_id=1)
