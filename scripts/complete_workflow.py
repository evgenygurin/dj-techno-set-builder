"""Complete workflow orchestrator for professional techno set creation."""
import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from scripts.checkpoint import CheckpointManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

class WorkflowOrchestrator:
    """Orchestrates complete techno set creation workflow."""

    def __init__(self, base_dir: Path, playlist_name: str):
        """Initialize workflow orchestrator.

        Args:
            base_dir: Base directory for sets (iCloud path)
            playlist_name: Name of Yandex Music playlist
        """
        self.base_dir = Path(base_dir)
        self.playlist_name = playlist_name

        # Generate set name: techno-professional-YYYY-MM-DD
        self.set_name = f"techno-professional-{datetime.now().strftime('%Y-%m-%d')}"
        self.set_dir = self.base_dir / "sets" / self.set_name
        self.tracks_dir = self.set_dir / "tracks"
        self.checkpoint_dir = self.set_dir / "checkpoints"

        # Initialize checkpoint manager
        self.checkpoint = CheckpointManager(self.checkpoint_dir)

        logger.info(f"Initialized workflow for set: {self.set_name}")
        logger.info(f"Output directory: {self.set_dir}")

    async def stage_1_fetch_playlist(self) -> list[int]:
        """Stage 1: Fetch playlist from Yandex Music.

        Returns:
            List of track IDs from playlist
        """
        stage_name = "playlist"

        # Check if checkpoint exists
        if self.checkpoint.exists(stage_name):
            logger.info("✓ Stage 1: Loading from checkpoint")
            data = self.checkpoint.load(stage_name)
            return data["track_ids"]

        logger.info("Stage 1: Fetching playlist from Yandex Music...")

        # Import here to avoid circular dependency
        from app.config import settings
        from app.services.yandex_music_client import YandexMusicClient

        ym_client = YandexMusicClient(token=settings.yandex_music_token)

        # Get user's playlists
        playlists = await ym_client.fetch_user_playlists(user_id="250905515")

        # Find target playlist
        target_playlist = None
        for playlist in playlists:
            if playlist.get("title") == self.playlist_name:
                target_playlist = playlist
                break

        if not target_playlist:
            raise ValueError(f"Playlist '{self.playlist_name}' not found")

        # Get playlist tracks
        tracks = await ym_client.fetch_playlist_tracks(
            user_id="250905515",
            kind=str(target_playlist["kind"]),
        )

        # Extract track IDs
        track_ids = [int(track["id"]) for track in tracks]

        logger.info(f"✓ Stage 1: Found {len(track_ids)} tracks in playlist")

        # Save checkpoint
        self.checkpoint.save(stage_name, {
            "playlist_name": self.playlist_name,
            "track_ids": track_ids,
            "track_count": len(track_ids),
        })

        return track_ids

    async def run(self) -> None:
        """Run complete workflow from start to finish."""
        logger.info("Starting complete workflow...")

        # Create directory structure
        self.set_dir.mkdir(parents=True, exist_ok=True)
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logger.info("✓ Directory structure created")

        # Stage 1: Fetch playlist
        track_ids = await self.stage_1_fetch_playlist()
        logger.info(f"Playlist contains {len(track_ids)} tracks")

        logger.info("Workflow stage 1 complete")

async def async_main() -> None:
    """Async CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Create professional techno DJ set from Yandex Music playlist"
    )
    parser.add_argument(
        "--playlist",
        default="Techno develop",
        help="Yandex Music playlist name (default: Techno develop)",
    )
    parser.add_argument(
        "--base-dir",
        default="/Users/laptop/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder",
        help="Base directory for sets (default: iCloud)",
    )

    args = parser.parse_args()

    orchestrator = WorkflowOrchestrator(
        base_dir=Path(args.base_dir),
        playlist_name=args.playlist,
    )
    await orchestrator.run()

def main() -> None:
    """CLI entry point."""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
