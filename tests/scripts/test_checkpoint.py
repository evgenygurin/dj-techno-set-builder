"""Tests for checkpoint system."""

import json

import pytest

from scripts.checkpoint import CheckpointManager


@pytest.fixture
def checkpoint_dir(tmp_path):
    """Create temporary checkpoint directory."""
    return tmp_path / "checkpoints"


def test_save_checkpoint(checkpoint_dir):
    """Test saving checkpoint to JSON file."""
    manager = CheckpointManager(checkpoint_dir)
    data = {"track_ids": [1, 2, 3], "count": 3}

    manager.save("stage1", data)

    assert (checkpoint_dir / "stage1.json").exists()
    saved = json.loads((checkpoint_dir / "stage1.json").read_text())
    assert saved == data


def test_load_checkpoint_exists(checkpoint_dir):
    """Test loading existing checkpoint."""
    checkpoint_dir.mkdir(parents=True)
    test_data = {"status": "complete"}
    (checkpoint_dir / "stage2.json").write_text(json.dumps(test_data))

    manager = CheckpointManager(checkpoint_dir)
    result = manager.load("stage2")

    assert result == test_data


def test_load_checkpoint_missing(checkpoint_dir):
    """Test loading non-existent checkpoint returns None."""
    manager = CheckpointManager(checkpoint_dir)
    result = manager.load("nonexistent")
    assert result is None


def test_checkpoint_exists(checkpoint_dir):
    """Test checkpoint existence check."""
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "exists.json").write_text("{}")

    manager = CheckpointManager(checkpoint_dir)
    assert manager.exists("exists")
    assert not manager.exists("missing")
