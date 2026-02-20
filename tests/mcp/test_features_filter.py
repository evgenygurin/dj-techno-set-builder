"""Tests for AudioFeaturesRepository.filter_by_criteria — SQL-level filtering."""

from unittest.mock import AsyncMock, patch

from app.repositories.audio_features import AudioFeaturesRepository


async def test_filter_by_criteria_builds_filters():
    """filter_by_criteria calls self.list with correct filters."""
    session = AsyncMock()
    repo = AudioFeaturesRepository(session)

    # Patch the list method to intercept the filters
    with patch.object(repo, "list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = ([], 0)

        _results, _total = await repo.filter_by_criteria(
            bpm_min=138.0,
            bpm_max=145.0,
            key_codes=[8, 9],
            energy_min=-10.0,
            energy_max=-5.0,
            offset=0,
            limit=50,
        )

        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["offset"] == 0
        assert call_kwargs["limit"] == 50
        # 5 filters: bpm_min, bpm_max, key_codes IN, energy_min, energy_max
        assert len(call_kwargs["filters"]) == 5


async def test_filter_by_criteria_no_filters():
    """No criteria means no filters — returns all."""
    session = AsyncMock()
    repo = AudioFeaturesRepository(session)

    with patch.object(repo, "list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = ([], 0)

        await repo.filter_by_criteria(offset=0, limit=50)

        call_kwargs = mock_list.call_args[1]
        assert len(call_kwargs["filters"]) == 0


async def test_filter_by_criteria_partial_filters():
    """Only bpm_min filter."""
    session = AsyncMock()
    repo = AudioFeaturesRepository(session)

    with patch.object(repo, "list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = ([], 0)

        await repo.filter_by_criteria(bpm_min=138.0, offset=0, limit=50)

        call_kwargs = mock_list.call_args[1]
        assert len(call_kwargs["filters"]) == 1
