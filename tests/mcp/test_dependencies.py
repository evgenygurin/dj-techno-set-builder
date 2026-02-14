"""Tests for MCP dependency injection providers."""

from __future__ import annotations

from app.mcp.dependencies import (
    get_analysis_service,
    get_features_service,
    get_playlist_service,
    get_session,
    get_set_generation_service,
    get_set_service,
    get_track_service,
    get_transition_service,
    get_ym_client,
)
from app.mcp.types import (
    AnalysisResult,
    ExportResult,
    ImportResult,
    PlaylistStatus,
    SearchStrategy,
    SetBuildResult,
    SimilarTracksResult,
    TrackDetails,
    TransitionScoreResult,
)


def test_types_are_importable():
    """All Pydantic types should be importable."""
    assert PlaylistStatus is not None
    assert TrackDetails is not None
    assert ImportResult is not None
    assert AnalysisResult is not None
    assert SimilarTracksResult is not None
    assert SearchStrategy is not None
    assert SetBuildResult is not None
    assert TransitionScoreResult is not None
    assert ExportResult is not None


def test_dependency_functions_are_importable():
    """All DI functions should be importable."""
    assert get_session is not None
    assert get_track_service is not None
    assert get_playlist_service is not None
    assert get_features_service is not None
    assert get_analysis_service is not None
    assert get_set_service is not None
    assert get_set_generation_service is not None
    assert get_transition_service is not None
    assert get_ym_client is not None


def test_playlist_status_model():
    """PlaylistStatus should serialize correctly."""
    status = PlaylistStatus(
        playlist_id=1,
        name="Test",
        total_tracks=10,
        analyzed_tracks=5,
        bpm_range=(126.0, 134.0),
        keys=["Am", "Cm"],
        avg_energy=-8.5,
        duration_minutes=45.0,
    )
    assert status.playlist_id == 1
    assert status.bpm_range == (126.0, 134.0)
    data = status.model_dump()
    assert data["keys"] == ["Am", "Cm"]


def test_track_details_defaults():
    """TrackDetails optional fields should default to None/False."""
    track = TrackDetails(track_id=1, title="Test Track", artists="DJ Test")
    assert track.duration_ms is None
    assert track.bpm is None
    assert track.key is None
    assert track.energy_lufs is None
    assert track.has_features is False


def test_transition_score_result_model():
    """TransitionScoreResult should hold all score components."""
    score = TransitionScoreResult(
        from_track_id=1,
        to_track_id=2,
        from_title="Track A",
        to_title="Track B",
        total=0.85,
        bpm=0.95,
        harmonic=0.80,
        energy=0.90,
        spectral=0.75,
        groove=0.85,
    )
    assert score.total == 0.85
    assert score.from_track_id == 1
    assert score.to_track_id == 2


def test_export_result_model():
    """ExportResult should store export details."""
    result = ExportResult(
        set_id=1,
        format="m3u",
        track_count=12,
        content="#EXTM3U\n#EXTINF:300,Track 1\n/music/track1.mp3",
    )
    assert result.format == "m3u"
    assert result.track_count == 12
    assert result.content.startswith("#EXTM3U")


def test_search_strategy_model():
    """SearchStrategy should hold LLM-generated search parameters."""
    strategy = SearchStrategy(
        queries=["dark techno 130 bpm", "industrial techno Am"],
        target_bpm_range=(128.0, 134.0),
        target_keys=["Am", "Cm", "Em"],
        target_energy_range=(-10.0, -6.0),
        reasoning="Targeting dark techno tracks in minor keys",
    )
    assert len(strategy.queries) == 2
    assert strategy.target_bpm_range == (128.0, 134.0)


def test_set_build_result_defaults():
    """SetBuildResult energy_curve should default to empty list."""
    result = SetBuildResult(
        set_id=1,
        version_id=1,
        track_count=10,
        total_score=8.5,
        avg_transition_score=0.85,
    )
    assert result.energy_curve == []


def test_analysis_result_defaults():
    """AnalysisResult optional fields should have correct defaults."""
    result = AnalysisResult(
        playlist_id=1,
        analyzed_count=8,
        failed_count=2,
    )
    assert result.bpm_range is None
    assert result.keys == []


def test_import_result_model():
    """ImportResult should hold import statistics."""
    result = ImportResult(
        playlist_id=1,
        imported_count=15,
        skipped_count=3,
        enriched_count=12,
    )
    assert result.imported_count == 15
    assert result.skipped_count == 3


def test_similar_tracks_result_model():
    """SimilarTracksResult should hold candidate statistics."""
    result = SimilarTracksResult(
        playlist_id=1,
        candidates_found=50,
        candidates_selected=10,
        added_count=8,
    )
    assert result.candidates_found == 50
    assert result.added_count == 8
