from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.errors import NotFoundError  # noqa: E402
from app.services.track_analysis import TrackAnalysisService  # noqa: E402
from app.utils.audio import (  # noqa: E402
    AudioSignal,
    BandEnergyResult,
    BeatsResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SectionResult,
    SpectralResult,
    TrackFeatures,
)


def _fake_features(*, with_beats: bool = False) -> TrackFeatures:
    beats = None
    if with_beats:
        beats = BeatsResult(
            beat_times=np.array([0.43, 0.86, 1.29], dtype=np.float32),
            downbeat_times=np.array([0.43], dtype=np.float32),
            onset_rate_mean=2.3,
            onset_rate_max=3.5,
            pulse_clarity=0.7,
            kick_prominence=0.5,
            hp_ratio=1.2,
            onset_envelope=np.zeros(100, dtype=np.float32),
        )
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
            energy_slope_mean=-0.001,
        ),
        spectral=SpectralResult(
            centroid_mean_hz=1500.0,
            rolloff_85_hz=5000.0,
            rolloff_95_hz=8000.0,
            flatness_mean=0.3,
            flux_mean=0.5,
            flux_std=0.1,
            contrast_mean_db=20.0,
            slope_db_per_oct=-4.2,
            hnr_mean_db=12.5,
        ),
        beats=beats,
    )


class TestTrackAnalysisService:
    @pytest.fixture
    def service(self) -> TrackAnalysisService:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=MagicMock(track_id=1))
        features_repo = MagicMock()
        features_repo.save_features = AsyncMock()
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
        service.features_repo.save_features.assert_awaited_once()

    async def test_raises_not_found(self) -> None:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=None)
        features_repo = MagicMock()
        svc = TrackAnalysisService(track_repo, features_repo)
        with pytest.raises(NotFoundError):
            await svc.analyze_track(999, "/fake.wav", run_id=1)

    @patch("app.services.track_analysis.extract_all_features")
    async def test_persists_beats_when_present(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        mock_extract.return_value = _fake_features(with_beats=True)
        result = await service.analyze_track(1, "/fake/path.wav", run_id=1)
        assert result.beats is not None
        assert result.beats.onset_rate_mean == 2.3
        assert result.beats.pulse_clarity == 0.7
        # save_features receives the full TrackFeatures object
        call_args = service.features_repo.save_features.call_args
        assert call_args.args == (1, 1, result)

    @patch("app.services.track_analysis.extract_all_features")
    async def test_beats_none_when_absent(
        self, mock_extract: MagicMock, service: TrackAnalysisService
    ) -> None:
        mock_extract.return_value = _fake_features(with_beats=False)
        result = await service.analyze_track(1, "/fake/path.wav", run_id=1)
        assert result.beats is None
        call_args = service.features_repo.save_features.call_args
        assert call_args.args == (1, 1, result)

    async def test_analyze_track_full_persists_section_pulse_clarity(self) -> None:
        track_repo = MagicMock()
        track_repo.get_by_id = AsyncMock(return_value=MagicMock(track_id=1))
        features_repo = MagicMock()
        features_repo.save_features = AsyncMock()
        sections_repo = MagicMock()
        sections_repo.create = AsyncMock()
        svc = TrackAnalysisService(track_repo, features_repo, sections_repo)

        features = _fake_features(with_beats=True)
        dummy_signal = AudioSignal(
            samples=np.zeros(44100, dtype=np.float32),
            sample_rate=44100,
            duration_s=1.0,
        )
        sections = [
            SectionResult(
                section_type=2,
                start_s=0.0,
                end_s=1.0,
                duration_s=1.0,
                energy_mean=0.8,
                energy_max=0.9,
                energy_slope=0.1,
                boundary_confidence=0.7,
                centroid_hz=2500.0,
                flux=0.08,
                onset_rate=2.0,
                pulse_clarity=0.77,
            )
        ]

        with (
            patch.object(svc, "_extract_full_sync", return_value=features),
            patch("app.services.track_analysis.load_audio", return_value=dummy_signal),
            patch(
                "app.utils.audio.structure.segment_structure",
                return_value=sections,
            ) as mock_segment,
        ):
            await svc.analyze_track_full(1, "/fake/path.wav", run_id=42)

        call_kwargs = mock_segment.call_args.kwargs
        assert call_kwargs["track_pulse_clarity"] == pytest.approx(features.beats.pulse_clarity)
        assert call_kwargs["beat_times"] is not None

        persisted = sections_repo.create.await_args.kwargs
        assert persisted["section_onset_rate"] == pytest.approx(2.0)
        assert persisted["section_pulse_clarity"] == pytest.approx(0.77)
