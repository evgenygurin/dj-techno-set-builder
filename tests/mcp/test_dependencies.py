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
    ExportResult,
    SearchStrategy,
    SetBuildResult,
    SimilarTracksResult,
    TransitionScoreResult,
)


def test_types_are_importable():
    """All Pydantic types should be importable."""
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
