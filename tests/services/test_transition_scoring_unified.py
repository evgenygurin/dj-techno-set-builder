"""Tests for UnifiedTransitionScoringService — sections loading in score_components_by_ids."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def _make_feat_mock(track_id: int, key_code: int = 0) -> MagicMock:
    """Create a minimal TrackAudioFeaturesComputed mock."""
    f = MagicMock()
    f.track_id = track_id
    f.bpm = 128.0
    f.lufs_i = -14.0
    f.key_code = key_code
    f.chroma_entropy = 0.7
    f.key_confidence = None
    f.low_energy = 0.3
    f.mid_energy = 0.5
    f.high_energy = 0.2
    f.mfcc_vector = None
    f.centroid_mean_hz = 2000.0
    f.onset_rate_mean = 5.0
    f.kick_prominence = 0.5
    f.hnr_mean_db = 0.0
    f.slope_db_per_oct = 0.0
    f.hp_ratio = 0.5
    return f


def _make_section(section_type: int, start_ms: int = 0, end_ms: int = 30000) -> MagicMock:
    sec = MagicMock()
    sec.section_type = section_type
    sec.start_ms = start_ms
    sec.end_ms = end_ms
    return sec


async def test_score_components_by_ids_calls_sections_repo() -> None:
    """score_components_by_ids should call sections_repo.get_latest_by_track_ids."""
    session = AsyncMock()

    feat_a = _make_feat_mock(track_id=1)
    feat_b = _make_feat_mock(track_id=2)

    sections_map: dict[int, list[MagicMock]] = {1: [], 2: []}

    with (
        patch(
            "app.services.transition_scoring_unified.AudioFeaturesRepository"
        ) as mock_feat_repo_cls,
        patch(
            "app.services.transition_scoring_unified.SectionsRepository"
        ) as mock_sec_repo_cls,
        patch(
            "app.services.transition_scoring_unified.CamelotLookupService"
        ) as mock_lookup_cls,
    ):
        mock_feat_repo = AsyncMock()
        mock_feat_repo.get_by_track.side_effect = [feat_a, feat_b]
        mock_feat_repo_cls.return_value = mock_feat_repo

        mock_sec_repo = AsyncMock()
        mock_sec_repo.get_latest_by_track_ids.return_value = sections_map
        mock_sec_repo_cls.return_value = mock_sec_repo

        mock_lookup = AsyncMock()
        mock_lookup.build_lookup_table.return_value = {}
        mock_lookup_cls.return_value = mock_lookup

        from app.services.transition_scoring_unified import (
            UnifiedTransitionScoringService,
        )

        svc = UnifiedTransitionScoringService(session)
        result = await svc.score_components_by_ids(1, 2)

    mock_sec_repo.get_latest_by_track_ids.assert_called_once_with([1, 2])
    assert "total" in result
    assert "structure" in result


async def test_structure_score_nonzero_with_outro_intro_sections() -> None:
    """Structure component should be non-neutral when outro->intro sections present."""
    session = AsyncMock()

    feat_a = _make_feat_mock(track_id=10)  # outro track
    feat_b = _make_feat_mock(track_id=20)  # intro track

    # SectionType: 0=intro, 4=outro
    outro_section = _make_section(section_type=4, start_ms=180000, end_ms=210000)
    intro_section = _make_section(section_type=0, start_ms=0, end_ms=32000)

    sections_map: dict[int, list[MagicMock]] = {10: [outro_section], 20: [intro_section]}

    with (
        patch(
            "app.services.transition_scoring_unified.AudioFeaturesRepository"
        ) as mock_feat_repo_cls,
        patch(
            "app.services.transition_scoring_unified.SectionsRepository"
        ) as mock_sec_repo_cls,
        patch(
            "app.services.transition_scoring_unified.CamelotLookupService"
        ) as mock_lookup_cls,
    ):
        mock_feat_repo = AsyncMock()
        mock_feat_repo.get_by_track.side_effect = [feat_a, feat_b]
        mock_feat_repo_cls.return_value = mock_feat_repo

        mock_sec_repo = AsyncMock()
        mock_sec_repo.get_latest_by_track_ids.return_value = sections_map
        mock_sec_repo_cls.return_value = mock_sec_repo

        mock_lookup = AsyncMock()
        mock_lookup.build_lookup_table.return_value = {}
        mock_lookup_cls.return_value = mock_lookup

        from app.services.transition_scoring_unified import (
            UnifiedTransitionScoringService,
        )

        svc = UnifiedTransitionScoringService(session)
        result = await svc.score_components_by_ids(10, 20)

    # outro->intro is the best pairing, score_structure should be > 0.5 (neutral)
    assert result["structure"] > 0.5, f"Expected structure > 0.5, got {result['structure']}"
