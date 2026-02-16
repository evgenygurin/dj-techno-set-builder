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
            assert data is not None
            return data["track_ids"]  # type: ignore[no-any-return]

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

    async def stage_2_import_metadata(self, track_ids: list[int]) -> dict[str, object]:
        """Stage 2: Import track metadata into database.

        Args:
            track_ids: List of Yandex Music track IDs to import

        Returns:
            Import statistics dict
        """
        stage_name = "metadata"

        # Check if checkpoint exists
        if self.checkpoint.exists(stage_name):
            logger.info("✓ Stage 2: Loading from checkpoint")
            data = self.checkpoint.load(stage_name)
            return data if data else {}

        logger.info(f"Stage 2: Importing metadata for {len(track_ids)} tracks...")

        # Import services
        from app.config import settings
        from app.database import session_factory
        from app.models.ingestion import ProviderTrackId
        from app.repositories.tracks import TrackRepository
        from app.services.yandex_music_client import YandexMusicClient, parse_ym_track

        imported = 0
        skipped = 0
        failed_ids = []

        async with session_factory() as session:
            ym_client = YandexMusicClient(token=settings.yandex_music_token)
            track_repo = TrackRepository(session)

            # Fetch metadata batch from YM
            ym_track_ids = [str(tid) for tid in track_ids]
            tracks_data = await ym_client.fetch_tracks_metadata(ym_track_ids)

            for track_data in tracks_data:
                try:
                    # Parse YM track
                    parsed = parse_ym_track(track_data)

                    # Check if already exists
                    existing = await track_repo.get_by_id(int(parsed.yandex_track_id))
                    if existing:
                        skipped += 1
                        continue

                    # Create Track record (simplified — no artists/albums for now)
                    track = await track_repo.create(
                        track_id=int(parsed.yandex_track_id),
                        title=parsed.title,
                        duration_ms=parsed.duration_ms or 0,
                    )

                    # Create ProviderTrackId link (provider_id=4 is yandex_music)
                    session.add(
                        ProviderTrackId(
                            track_id=track.track_id,
                            provider_id=4,  # yandex_music
                            provider_track_id=parsed.yandex_track_id,
                        )
                    )

                    imported += 1

                except Exception as e:
                    logger.error(f"Failed to import track: {e}")
                    failed_ids.append(int(track_data.get("id", 0)))

            await session.commit()

        logger.info(f"✓ Stage 2: Imported {imported}, skipped {skipped}, failed {len(failed_ids)}")

        # Save checkpoint
        stats = {
            "imported": imported,
            "skipped": skipped,
            "failed": len(failed_ids),
            "failed_track_ids": failed_ids,
        }
        self.checkpoint.save(stage_name, stats)

        return stats

    async def stage_3_download_tracks(self, track_ids: list[int]) -> dict[str, object]:
        """Stage 3: Download MP3 files from Yandex Music.

        Args:
            track_ids: List of track IDs to download

        Returns:
            Download statistics dict
        """
        stage_name = "downloads"

        # Check if checkpoint exists
        if self.checkpoint.exists(stage_name):
            logger.info("✓ Stage 3: Loading from checkpoint")
            data = self.checkpoint.load(stage_name)
            return data if data else {}

        logger.info(f"Stage 3: Downloading {len(track_ids)} tracks...")

        # Import services
        from app.config import settings
        from app.database import session_factory
        from app.services.download import DownloadService
        from app.services.yandex_music_client import YandexMusicClient

        # Create download service
        async with session_factory() as session:
            ym_client = YandexMusicClient(token=settings.yandex_music_token)
            download_service = DownloadService(
                session=session,
                ym_client=ym_client,
                library_path=self.tracks_dir,
            )

            # Download batch
            result = await download_service.download_tracks_batch(
                track_ids=track_ids,
                prefer_bitrate=320,
            )

        logger.info(
            f"✓ Stage 3: Downloaded {result.downloaded}, "
            f"skipped {result.skipped}, failed {result.failed}"
        )

        # Save checkpoint
        stats = {
            "downloaded": result.downloaded,
            "skipped": result.skipped,
            "failed": result.failed,
            "failed_track_ids": result.failed_track_ids,
            "total_bytes": result.total_bytes,
        }
        self.checkpoint.save(stage_name, stats)

        return stats

    async def stage_4_quick_analysis(self, track_ids: list[int]) -> dict[str, object]:
        """Stage 4: Quick audio analysis (BPM, key, energy) for all tracks.

        Args:
            track_ids: List of track IDs to analyze

        Returns:
            Analysis statistics dict
        """
        stage_name = "quick_analysis"

        # Check if checkpoint exists
        if self.checkpoint.exists(stage_name):
            logger.info("✓ Stage 4: Loading from checkpoint")
            data = self.checkpoint.load(stage_name)
            return data if data else {}

        logger.info(f"Stage 4: Quick analysis for {len(track_ids)} tracks...")

        # Import services and repos
        from app.database import session_factory
        from app.repositories.audio_features import AudioFeaturesRepository
        from app.repositories.runs import FeatureRunRepository
        from app.repositories.tracks import TrackRepository
        from app.services.track_analysis import TrackAnalysisService

        analyzed = 0
        skipped = 0
        failed_ids = []

        async with session_factory() as session:
            # Create repositories
            track_repo = TrackRepository(session)
            features_repo = AudioFeaturesRepository(session)
            run_repo = FeatureRunRepository(session)

            # Create FeatureExtractionRun
            run = await run_repo.create(
                pipeline_name="complete_workflow",
                pipeline_version="1.0",
                parameters={"stage": "quick_analysis", "use_ml": False},
            )
            run_id = run.run_id
            await session.commit()

            # Create analysis service
            analysis_service = TrackAnalysisService(
                track_repo=track_repo,
                features_repo=features_repo,
            )

            for track_id in track_ids:
                try:
                    # Get track from DB
                    track = await track_repo.get_by_id(track_id)
                    if not track:
                        logger.warning(f"Track {track_id} not found in database")
                        failed_ids.append(track_id)
                        continue

                    # Check if already analyzed
                    existing = await features_repo.get_by_track(track_id, run_id)
                    if existing:
                        skipped += 1
                        continue

                    # Generate filename (same pattern as DownloadService)
                    sanitized = self._sanitize_title(track.title)
                    filename = f"{track.track_id}_{sanitized}.mp3"
                    audio_path = self.tracks_dir / filename

                    if not audio_path.exists():
                        logger.warning(f"Audio file not found: {audio_path}")
                        failed_ids.append(track_id)
                        continue

                    # Quick analysis
                    await analysis_service.analyze_track(
                        track_id=track_id,
                        audio_path=audio_path,
                        run_id=run_id,
                    )
                    analyzed += 1

                except Exception as e:
                    logger.error(f"Failed to analyze track {track_id}: {e}")
                    failed_ids.append(track_id)

            # Mark run as completed
            await run_repo.mark_completed(run_id)
            await session.commit()

        logger.info(f"✓ Stage 4: Analyzed {analyzed}, skipped {skipped}, failed {len(failed_ids)}")

        # Save checkpoint
        stats = {
            "analyzed": analyzed,
            "skipped": skipped,
            "failed": len(failed_ids),
            "failed_track_ids": failed_ids,
            "run_id": run_id,
        }
        self.checkpoint.save(stage_name, stats)

        return stats

    @staticmethod
    def _sanitize_title(title: str, max_len: int = 50) -> str:
        """Sanitize title for use in filename (matches DownloadService).

        Removes special characters, replaces spaces with underscores,
        converts to lowercase, truncates to max_len.

        Args:
            title: Track title to sanitize
            max_len: Maximum length (default: 50)

        Returns:
            Sanitized filename-safe string, or "untitled" if empty
        """
        import re

        # Remove special characters: / \ : * ? " < > |
        safe = re.sub(r'[/\\:*?"<>|]', '', title)
        # Replace spaces with underscores
        safe = safe.replace(' ', '_')
        # Replace multiple underscores with single
        safe = re.sub(r'_+', '_', safe)
        # Lowercase
        safe = safe.lower()
        # Truncate to max_len
        safe = safe[:max_len]
        # Remove trailing underscores
        safe = safe.rstrip('_')
        return safe or "untitled"

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

        # Stage 2: Import metadata
        import_stats = await self.stage_2_import_metadata(track_ids)
        logger.info(f"Imported {import_stats['imported']} tracks metadata")

        # Stage 3: Download tracks
        download_stats = await self.stage_3_download_tracks(track_ids)
        total_mb = download_stats['total_bytes'] / 1024 / 1024  # type: ignore[operator]
        logger.info(
            f"Downloaded {download_stats['downloaded']} tracks "
            f"({total_mb:.1f} MB)"
        )

        # Stage 4: Quick analysis
        analysis_stats = await self.stage_4_quick_analysis(track_ids)
        logger.info(f"Analyzed {analysis_stats['analyzed']} tracks")

        logger.info("Workflow stages 1-4 complete")

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
