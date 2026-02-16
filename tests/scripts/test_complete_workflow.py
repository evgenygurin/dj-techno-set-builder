"""Integration tests for complete workflow."""
import pytest

from scripts.complete_workflow import WorkflowOrchestrator


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

    # Run stage 1
    track_ids = await orchestrator.stage_1_fetch_playlist()

    # Verify
    assert len(track_ids) > 0
    assert orchestrator.checkpoint.exists("playlist")

    # Verify checkpoint can be loaded
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

    # Run stage 1 first time
    track_ids_first = await orchestrator.stage_1_fetch_playlist()

    # Run stage 1 second time (should load from checkpoint)
    track_ids_second = await orchestrator.stage_1_fetch_playlist()

    # Should return same data
    assert track_ids_first == track_ids_second

    # Checkpoint file should exist
    checkpoint_file = orchestrator.checkpoint_dir / "playlist.json"
    assert checkpoint_file.exists()
