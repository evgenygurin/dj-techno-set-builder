"""Checkpoint system for workflow recovery."""
import json
from pathlib import Path

class CheckpointManager:
    """Manages JSON checkpoints for workflow stages."""

    def __init__(self, checkpoint_dir: Path):
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoint JSON files
        """
        self.checkpoint_dir = Path(checkpoint_dir)

    def save(self, stage_name: str, data: dict) -> None:
        """Save checkpoint data to JSON file.

        Args:
            stage_name: Name of the stage (becomes filename)
            data: Dictionary to save as JSON
        """
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_dir / f"{stage_name}.json"
        path.write_text(json.dumps(data, indent=2))

    def load(self, stage_name: str) -> dict | None:
        """Load checkpoint data from JSON file.

        Args:
            stage_name: Name of the stage to load

        Returns:
            Dictionary from JSON, or None if checkpoint doesn't exist
        """
        path = self.checkpoint_dir / f"{stage_name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def exists(self, stage_name: str) -> bool:
        """Check if checkpoint exists.

        Args:
            stage_name: Name of the stage to check

        Returns:
            True if checkpoint file exists
        """
        path = self.checkpoint_dir / f"{stage_name}.json"
        return path.exists()
