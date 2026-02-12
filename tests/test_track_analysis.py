from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.errors import NotFoundError  # noqa: E402
from app.services.track_analysis import TrackAnalysisService  # noqa: E402
from app.utils.audio import (  # noqa: E402
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)


def _fake_features() -> TrackFeatures:
    return TrackFeatures(
        bpm=BpmResult(bpm=140.0, confidence=0.9, stability=0.95, is_variable=False),
        key=KeyResult(
            key="A",
            scale="minor",
            key_code=18,
            confidence=0.85,
            is_atonal=False,
            chroma=np.zeros(12, dtype=np.float32),
        ),
        loudness=LoudnessResult(
            lufs_i=-8.0,
            lufs_s_mean=-7.5,
            lufs_m_max=-5.0,
            rms_dbfs=-10.0,
            true_peak_db=-1.0,
            crest_factor_db=9.0,
            lra_lu=6.0,
        ),
        band_energy=BandEnergyResult(
            sub=0.3,
            low=0.7,
            low_mid=0.5,
            mid=0.4,
            high_mid=0.2,
            high=0.1,
            low_high_ratio=7.0,
            sub_lowmid_ratio=0.6,
        ),
        spectral=SpectralResult(
            centroid_mean_hz=1500.0,
            rolloff_85_hz=5000.0,
            rolloff_95_hz=8000.0,
            flatness_mean=0.3,
            flux_mean=0.5,
            flux_std=0.1,
            contrast_mean_db=20.0,
        ),
    )


class TestTrackAnalysisService:
    @pytest.fixture
    def service(self) -> TrackAnalysisService:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=MagicMock(track_id=1))
        features_repo = MagicMock()
        features_repo.create = AsyncMock()
        return TrackAnalysisService(track_repo, features_repo)

    @patch("app.services.track_analysis.extract_all_features")
    async def test_analyze_track_returns_features(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        mock_extract.return_value = _fake_features()
        result = await service.analyze_track(1, "/fake/path.wav", run_id=1)
        assert isinstance(result, TrackFeatures)
        assert result.bpm.bpm == 140.0

    @patch("app.services.track_analysis.extract_all_features")
    async def test_persists_to_repo(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        mock_extract.return_value = _fake_features()
        await service.analyze_track(1, "/fake/path.wav", run_id=1)
        service.features_repo.create.assert_awaited_once()

    async def test_raises_not_found(self) -> None:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=None)
        features_repo = MagicMock()
        svc = TrackAnalysisService(track_repo, features_repo)
        with pytest.raises(NotFoundError):
            await svc.analyze_track(999, "/fake.wav", run_id=1)
