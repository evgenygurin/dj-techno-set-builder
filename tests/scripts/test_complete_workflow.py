"""Integration tests for complete workflow."""

from unittest.mock import AsyncMock, patch

import pytest

from scripts.complete_workflow import WorkflowOrchestrator

_FAKE_PLAYLISTS = [
    {"title": "Techno develop", "kind": 1259},
    {"title": "Other", "kind": 999},
]

_FAKE_TRACKS = [
    {"id": "100", "title": "Track A"},
    {"id": "200", "title": "Track B"},
    {"id": "300", "title": "Track C"},
]


@pytest.mark.asyncio
async def test_stage_1_fetch_playlist(tmp_path):
    """Test Stage 1 can fetch playlist and save checkpoint."""
    orchestrator = WorkflowOrchestrator(
        base_dir=tmp_path,
        playlist_name="Techno develop",
    )

    # Create directories
    orchestrator.set_dir.mkdir(parents=True)
    orchestrator.checkpoint_dir.mkdir(parents=True)

    with (
        patch(
            "app.clients.yandex_music.YandexMusicClient.fetch_user_playlists",
            new_callable=AsyncMock,
            return_value=_FAKE_PLAYLISTS,
        ),
        patch(
            "app.clients.yandex_music.YandexMusicClient.fetch_playlist_tracks",
            new_callable=AsyncMock,
            return_value=_FAKE_TRACKS,
        ),
    ):
        # Run stage 1
        track_ids = await orchestrator.stage_1_fetch_playlist()

    # Verify
    assert track_ids == [100, 200, 300]
    assert orchestrator.checkpoint.exists("playlist")

    # Verify checkpoint can be loaded (no HTTP calls needed)
    track_ids_loaded = await orchestrator.stage_1_fetch_playlist()
    assert track_ids == track_ids_loaded


@pytest.mark.asyncio
async def test_checkpoint_recovery(tmp_path):
    """Test that checkpoint system enables recovery."""
    orchestrator = WorkflowOrchestrator(
        base_dir=tmp_path,
        playlist_name="Techno develop",
    )

    # Create directories
    orchestrator.set_dir.mkdir(parents=True)
    orchestrator.checkpoint_dir.mkdir(parents=True)

    with (
        patch(
            "app.clients.yandex_music.YandexMusicClient.fetch_user_playlists",
            new_callable=AsyncMock,
            return_value=_FAKE_PLAYLISTS,
        ),
        patch(
            "app.clients.yandex_music.YandexMusicClient.fetch_playlist_tracks",
            new_callable=AsyncMock,
            return_value=_FAKE_TRACKS,
        ),
    ):
        # Run stage 1 first time
        track_ids_first = await orchestrator.stage_1_fetch_playlist()

    # Run stage 1 second time (should load from checkpoint, no HTTP needed)
    track_ids_second = await orchestrator.stage_1_fetch_playlist()

    # Should return same data
    assert track_ids_first == track_ids_second

    # Checkpoint file should exist
    checkpoint_file = orchestrator.checkpoint_dir / "playlist.json"
    assert checkpoint_file.exists()
