"""Tests for AnalysisOrchestrator — orchestration logic with mocked audio utils."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import NotFoundError
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis import AnalysisOrchestrator


def _make_fake_features() -> MagicMock:
    """Minimal mock of TrackFeatures for orchestrator tests."""
    features = MagicMock()
    features.bpm.bpm = 138.0
    features.key.key_code = 10
    return features


def _build_orchestrator(
    *, track_exists: bool = True
) -> tuple[AnalysisOrchestrator, MagicMock, MagicMock]:
    """Build orchestrator with mocked repos. Returns (orchestrator, track_repo, run_repo)."""
    track_repo = MagicMock()
    track = MagicMock(track_id=80001) if track_exists else None
    track_repo.get_by_id = AsyncMock(return_value=track)

    features_repo = MagicMock()
    features_repo.save_features = AsyncMock()

    sections_repo = MagicMock()

    run_repo = MagicMock()
    run = MagicMock(run_id=80010)
    run_repo.create = AsyncMock(return_value=run)
    run_repo.mark_completed = AsyncMock()
    run_repo.mark_failed = AsyncMock()

    orch = AnalysisOrchestrator(track_repo, features_repo, sections_repo, run_repo)
    return orch, track_repo, run_repo


class TestAnalysisOrchestrator:
    def test_construction(self) -> None:
        orch, _, _ = _build_orchestrator()
        assert orch.track_repo is not None
        assert orch.run_repo is not None
        assert orch.analysis_svc is not None

    async def test_analyze_not_found_raises(self) -> None:
        orch, _, _ = _build_orchestrator(track_exists=False)
        request = AnalysisRequest(audio_path="/fake/track.wav")
        with pytest.raises(NotFoundError):
            await orch.analyze(80099, request)

    async def test_analyze_creates_run_and_completes(self) -> None:
        orch, _, run_repo = _build_orchestrator()
        request = AnalysisRequest(audio_path="/fake/track.wav")

        with patch.object(orch.analysis_svc, "analyze_track", new_callable=AsyncMock) as mock_at:
            mock_at.return_value = _make_fake_features()
            result = await orch.analyze(80001, request)

        assert isinstance(result, AnalysisResponse)
        assert result.status == "completed"
        assert result.bpm == 138.0
        assert result.key_code == 10
        assert result.run_id == 80010
        run_repo.create.assert_awaited_once()
        run_repo.mark_completed.assert_awaited_once_with(80010)
        run_repo.mark_failed.assert_not_awaited()

    async def test_analyze_full_delegates_to_analyze_track_full(self) -> None:
        orch, _, _run_repo = _build_orchestrator()
        request = AnalysisRequest(audio_path="/fake/track.wav", full_analysis=True)

        with patch.object(
            orch.analysis_svc, "analyze_track_full", new_callable=AsyncMock
        ) as mock_atf:
            mock_atf.return_value = _make_fake_features()
            result = await orch.analyze(80001, request)

        assert result.status == "completed"
        mock_atf.assert_awaited_once_with(80001, "/fake/track.wav", 80010)

    async def test_analyze_marks_failed_on_exception(self) -> None:
        orch, _, run_repo = _build_orchestrator()
        request = AnalysisRequest(audio_path="/fake/track.wav")

        with patch.object(orch.analysis_svc, "analyze_track", new_callable=AsyncMock) as mock_at:
            mock_at.side_effect = RuntimeError("audio crash")
            result = await orch.analyze(80001, request)

        assert result.status == "failed"
        assert result.bpm is None
        assert result.key_code is None
        run_repo.mark_failed.assert_awaited_once_with(80010)
        run_repo.mark_completed.assert_not_awaited()

    async def test_run_receives_correct_parameters(self) -> None:
        orch, _, run_repo = _build_orchestrator()
        request = AnalysisRequest(
            audio_path="/fake/track.wav",
            pipeline_name="custom-v2",
            pipeline_version="3.0",
            full_analysis=True,
        )

        with patch.object(
            orch.analysis_svc, "analyze_track_full", new_callable=AsyncMock
        ) as mock_atf:
            mock_atf.return_value = _make_fake_features()
            await orch.analyze(80001, request)

        run_repo.create.assert_awaited_once_with(
            pipeline_name="custom-v2",
            pipeline_version="3.0",
            parameters={"full_analysis": True},
            code_ref="custom-v2@3.0",
            status="running",
        )
