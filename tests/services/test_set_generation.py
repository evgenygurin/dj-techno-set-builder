"""Tests for SetGenerationService playlist filtering and sections batch loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.errors import ValidationError
from app.services.set_generation import SetGenerationService


def _make_features_mock(track_id: int, bpm: float = 128.0) -> MagicMock:
    """Create a minimal TrackAudioFeaturesComputed mock."""
    f = MagicMock()
    f.track_id = track_id
    f.bpm = bpm
    f.energy_mean = 0.5
    f.lufs_i = -9.0
    f.key_code = 0
    return f


def _make_playlist_item(track_id: int) -> MagicMock:
    item = MagicMock()
    item.track_id = track_id
    return item


def _make_service(
    *,
    all_features: list[MagicMock],
    playlist_items: list[MagicMock] | None = None,
    sections_map: dict[int, list[MagicMock]] | None = None,
) -> SetGenerationService:
    """Build a SetGenerationService with mocked repositories."""
    set_repo = AsyncMock()
    set_repo.get_by_id.return_value = MagicMock(set_id=1)

    version_repo = AsyncMock()
    version_repo.create.return_value = MagicMock(set_version_id=99, generator_run={})

    item_repo = AsyncMock()
    item_repo.create = AsyncMock()

    features_repo = AsyncMock()
    features_repo.list_all.return_value = all_features

    sections_repo: AsyncMock | None = None
    if sections_map is not None:
        sections_repo = AsyncMock()
        sections_repo.get_latest_by_track_ids.return_value = sections_map

    playlist_repo: AsyncMock | None = None
    if playlist_items is not None:
        playlist_repo = AsyncMock()
        playlist_repo.list_by_playlist.return_value = (playlist_items, len(playlist_items))

    return SetGenerationService(
        set_repo=set_repo,
        version_repo=version_repo,
        item_repo=item_repo,
        features_repo=features_repo,
        sections_repo=sections_repo,
        playlist_repo=playlist_repo,
    )


def _patch_ga_and_matrix() -> tuple[MagicMock, MagicMock, AsyncMock]:
    """Create mock objects for GeneticSetGenerator, matrix builder, and CamelotLookup."""
    mock_gen = MagicMock()
    mock_result = MagicMock()
    mock_result.best_order = [0, 1]
    mock_result.best_fitness = 0.8
    mock_result.fitness_history = [0.5, 0.8]
    mock_result.generations_run = 10
    mock_result.track_ids = [1, 2]
    mock_result.score = 0.8
    mock_result.transition_scores = [0.9]
    mock_result.energy_arc_score = 0.7
    mock_result.bpm_smoothness_score = 0.6
    mock_gen.run.return_value = mock_result

    mock_gen_cls = MagicMock(return_value=mock_gen)
    mock_matrix = AsyncMock(return_value=np.array([[0.0, 0.9], [0.8, 0.0]]))
    mock_lookup = AsyncMock()
    mock_lookup.build_lookup_table.return_value = {}

    return mock_gen_cls, mock_matrix, mock_lookup


async def test_playlist_filter_limits_tracks() -> None:
    """When playlist_id given, only playlist tracks should enter the GA."""
    all_features = [_make_features_mock(i) for i in range(1, 6)]
    playlist_items = [_make_playlist_item(1), _make_playlist_item(3)]

    svc = _make_service(all_features=all_features, playlist_items=playlist_items)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(
        playlist_id=42,
        population_size=10,
        generations=10,
        track_count=2,
    )

    mock_gen_cls, mock_matrix, _ = _patch_ga_and_matrix()

    with (
        patch("app.services.set_generation.GeneticSetGenerator", mock_gen_cls),
        patch.object(svc, "_build_transition_matrix_scored", mock_matrix),
    ):
        await svc.generate(1, req)

    # playlist_repo.list_by_playlist must have been called with playlist_id=42
    assert svc.playlist_repo is not None
    svc.playlist_repo.list_by_playlist.assert_called_once_with(42, limit=1000)


async def test_empty_playlist_raises_validation_error() -> None:
    """Empty playlist (no tracks with features) should raise ValidationError."""
    all_features = [_make_features_mock(1), _make_features_mock(2)]
    playlist_items = [_make_playlist_item(99)]  # track 99 has no features

    svc = _make_service(all_features=all_features, playlist_items=playlist_items)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(playlist_id=5, population_size=10, generations=10)

    with pytest.raises(ValidationError, match="No tracks with audio features in playlist 5"):
        await svc.generate(1, req)


async def test_no_playlist_id_uses_all_tracks() -> None:
    """Without playlist_id, all tracks should be used (backward compat)."""
    all_features = [_make_features_mock(i) for i in range(1, 4)]
    svc = _make_service(all_features=all_features)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(population_size=10, generations=10, track_count=3)

    mock_gen_cls, mock_matrix, _ = _patch_ga_and_matrix()
    mock_result = mock_gen_cls.return_value.run.return_value
    mock_result.best_order = [0, 1, 2]
    mock_result.track_ids = [1, 2, 3]
    mock_matrix.return_value = np.ones((3, 3)) - np.eye(3)

    with (
        patch("app.services.set_generation.GeneticSetGenerator", mock_gen_cls),
        patch.object(svc, "_build_transition_matrix_scored", mock_matrix),
    ):
        await svc.generate(1, req)

    # playlist_repo is None → list_by_playlist was never called
    assert svc.playlist_repo is None


async def test_sections_repo_called_with_track_ids() -> None:
    """sections_repo.get_latest_by_track_ids should be called with all track IDs."""
    all_features = [_make_features_mock(10), _make_features_mock(20)]
    sections_map: dict[int, list[MagicMock]] = {10: [], 20: []}

    svc = _make_service(all_features=all_features, sections_map=sections_map)

    from app.schemas.set_generation import SetGenerationRequest

    req = SetGenerationRequest(population_size=10, generations=10, track_count=2)

    mock_gen_cls, mock_matrix, _ = _patch_ga_and_matrix()

    with (
        patch("app.services.set_generation.GeneticSetGenerator", mock_gen_cls),
        patch.object(svc, "_build_transition_matrix_scored", mock_matrix),
    ):
        await svc.generate(1, req)

    assert svc.sections_repo is not None
    svc.sections_repo.get_latest_by_track_ids.assert_called_once()
    call_args = svc.sections_repo.get_latest_by_track_ids.call_args[0][0]
    assert set(call_args) == {10, 20}
