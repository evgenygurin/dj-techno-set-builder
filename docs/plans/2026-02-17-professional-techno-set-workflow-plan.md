# Professional Techno Set Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build automated workflow script that creates professional techno DJ sets from Yandex Music playlists with adaptive analysis, GA optimization, and Rekordbox export.

**Architecture:** Python CLI orchestrator script that calls existing services (YandexMusicClient, DownloadService, TrackAnalysisService, SetGenerationService, set_export) sequentially with JSON checkpoints between stages for recovery and review.

**Tech Stack:** Python 3.12+, SQLAlchemy async, existing project services, argparse for CLI

**Design Doc:** [docs/plans/2026-02-17-professional-techno-set-workflow-design.md](./2026-02-17-professional-techno-set-workflow-design.md)

---

## Task 1: Create Orchestrator Skeleton + Checkpoint System

**Files:**
- Create: `scripts/complete_workflow.py`
- Create: `scripts/__init__.py`
- Create: `scripts/checkpoint.py`

**Step 1: Write test for checkpoint save/load**

Create: `tests/scripts/test_checkpoint.py`

```python
"""Tests for checkpoint system."""
import json
from pathlib import Path

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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/scripts/test_checkpoint.py -v
```

Expected: FAIL with "No module named 'scripts.checkpoint'"

**Step 3: Implement minimal CheckpointManager**

Create: `scripts/__init__.py` (empty file)

Create: `scripts/checkpoint.py`

```python
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/scripts/test_checkpoint.py -v
```

Expected: PASS (all 4 tests green)

**Step 5: Create orchestrator skeleton**

Create: `scripts/complete_workflow.py`

```python
"""Complete workflow orchestrator for professional techno set creation."""
import argparse
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

    def run(self) -> None:
        """Run complete workflow from start to finish."""
        logger.info("Starting complete workflow...")

        # Create directory structure
        self.set_dir.mkdir(parents=True, exist_ok=True)
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logger.info("✓ Directory structure created")
        logger.info("Workflow skeleton ready (stages not implemented yet)")

def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Create professional techno DJ set from Yandex Music playlist"
    )
    parser.add_argument(
        "--playlist",
        default="Techno develop Recs",
        help="Yandex Music playlist name (default: Techno develop Recs)",
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
    orchestrator.run()

if __name__ == "__main__":
    main()
```

**Step 6: Test orchestrator skeleton manually**

```bash
python scripts/complete_workflow.py --help
```

Expected: Help message with --playlist and --base-dir options

```bash
python scripts/complete_workflow.py
```

Expected: Creates directory structure, logs success

**Step 7: Commit Task 1**

```bash
git add scripts/ tests/scripts/
git commit -m "feat: add orchestrator skeleton and checkpoint system

- Create CheckpointManager for JSON checkpoint save/load
- Add WorkflowOrchestrator skeleton with directory setup
- Add CLI argument parsing for playlist and base directory
- Tests for checkpoint system (save, load, exists)"
```

---

## Task 2: Implement Stage 1 (Fetch Playlist from Yandex Music)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add stage_1_fetch_playlist method**

Add to `WorkflowOrchestrator` class in `scripts/complete_workflow.py`:

```python
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
    from app.services.yandex_music_client import YandexMusicClient

    # Initialize YM client
    ym_client = YandexMusicClient()

    # Get user's playlists
    playlists = await ym_client.get_playlists_list(user_id=250905515)

    # Find target playlist
    target_playlist = None
    for playlist in playlists:
        if playlist.title == self.playlist_name:
            target_playlist = playlist
            break

    if not target_playlist:
        raise ValueError(f"Playlist '{self.playlist_name}' not found")

    # Get playlist details with tracks
    playlist_details = await ym_client.get_playlist(
        user_id=250905515,
        kind=target_playlist.kind,
    )

    # Extract track IDs
    track_ids = [track.id for track in playlist_details.tracks]

    logger.info(f"✓ Stage 1: Found {len(track_ids)} tracks in playlist")

    # Save checkpoint
    self.checkpoint.save(stage_name, {
        "playlist_name": self.playlist_name,
        "track_ids": track_ids,
        "track_count": len(track_ids),
    })

    return track_ids
```

**Step 2: Update run() method to call stage_1**

Replace `run()` method in `WorkflowOrchestrator`:

```python
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
```

**Step 3: Update main() to use asyncio**

Replace `main()` function:

```python
import asyncio

async def async_main() -> None:
    """Async CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Create professional techno DJ set from Yandex Music playlist"
    )
    parser.add_argument(
        "--playlist",
        default="Techno develop Recs",
        help="Yandex Music playlist name (default: Techno develop Recs)",
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
```

**Step 4: Test Stage 1 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Fetches playlist from YM
- Logs track count
- Creates checkpoint file `checkpoints/playlist.json`

**Step 5: Verify checkpoint**

```bash
cat "/Users/laptop/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/sets/techno-professional-$(date +%Y-%m-%d)/checkpoints/playlist.json"
```

Expected: JSON with `playlist_name`, `track_ids`, `track_count`

**Step 6: Commit Task 2**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stage 1 (fetch playlist from Yandex Music)

- Add stage_1_fetch_playlist() method
- Fetch playlist from YM user 250905515
- Extract track IDs
- Save checkpoint with track_ids
- Update run() to call stage_1
- Convert main() to async with asyncio.run()"
```

---

## Task 3: Implement Stage 2 (Download Tracks)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add stage_2_download_tracks method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_2_download_tracks(self, track_ids: list[int]) -> dict:
    """Stage 2: Download MP3 files from Yandex Music.

    Args:
        track_ids: List of track IDs to download

    Returns:
        Download statistics dict
    """
    stage_name = "downloads"

    # Check if checkpoint exists
    if self.checkpoint.exists(stage_name):
        logger.info("✓ Stage 2: Loading from checkpoint")
        return self.checkpoint.load(stage_name)

    logger.info(f"Stage 2: Downloading {len(track_ids)} tracks...")

    # Import services
    from app.config import get_settings
    from app.database import session_factory
    from app.services.download import DownloadService
    from app.services.yandex_music_client import YandexMusicClient

    settings = get_settings()

    # Create download service
    async with session_factory() as session:
        ym_client = YandexMusicClient()
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
        f"✓ Stage 2: Downloaded {result.downloaded}, "
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
```

**Step 2: Update run() to call stage_2**

Update `run()` method:

```python
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

    # Stage 2: Download tracks
    download_stats = await self.stage_2_download_tracks(track_ids)
    logger.info(
        f"Downloaded {download_stats['downloaded']} tracks "
        f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
    )

    logger.info("Workflow stages 1-2 complete")
```

**Step 3: Test Stage 2 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Downloads all tracks from playlist
- Logs download stats
- Creates checkpoint file `checkpoints/downloads.json`
- MP3 files appear in `tracks/` directory

**Step 4: Commit Task 3**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stage 2 (download tracks)

- Add stage_2_download_tracks() method
- Use DownloadService with YandexMusicClient
- Download to tracks/ directory with 320 kbps bitrate
- Save checkpoint with download statistics
- Update run() to call stage_2"
```

---

## Task 4: Implement Stage 3-4 (Import Metadata + Quick Analysis)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add stage_3_import_metadata method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_3_import_metadata(self, track_ids: list[int]) -> None:
    """Stage 3: Import track metadata into database.

    Args:
        track_ids: List of track IDs to import
    """
    logger.info(f"Stage 3: Importing metadata for {len(track_ids)} tracks...")

    from app.database import session_factory
    from app.repositories.tracks import TrackRepository

    async with session_factory() as session:
        track_repo = TrackRepository(session)

        # Ensure all tracks exist in DB (they should from download stage)
        for track_id in track_ids:
            track = await track_repo.get_by_id(track_id)
            if not track:
                logger.warning(f"Track {track_id} not found in DB (skipping)")

    logger.info("✓ Stage 3: Metadata import complete")
```

**Step 2: Add stage_4_quick_analysis method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_4_quick_analysis(self, track_ids: list[int]) -> dict:
    """Stage 4: Quick audio analysis for all tracks.

    Args:
        track_ids: List of track IDs to analyze

    Returns:
        Analysis results dict
    """
    stage_name = "analysis_stage1"

    # Check if checkpoint exists
    if self.checkpoint.exists(stage_name):
        logger.info("✓ Stage 4: Loading from checkpoint")
        return self.checkpoint.load(stage_name)

    logger.info(f"Stage 4: Quick analysis for {len(track_ids)} tracks...")

    from app.database import session_factory
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.dj_library_items import DjLibraryItemRepository
    from app.repositories.tracks import TrackRepository
    from app.services.track_analysis import TrackAnalysisService

    analyzed_count = 0
    skipped_count = 0
    failed_ids = []

    async with session_factory() as session:
        track_repo = TrackRepository(session)
        features_repo = AudioFeaturesRepository(session)
        library_repo = DjLibraryItemRepository(session)

        analysis_service = TrackAnalysisService(
            track_repo=track_repo,
            features_repo=features_repo,
            sections_repo=None,  # Not needed for quick analysis
        )

        for track_id in track_ids:
            try:
                # Check if already analyzed
                existing = await features_repo.get_by_track_id(track_id)
                if existing:
                    logger.debug(f"Track {track_id} already analyzed, skipping")
                    skipped_count += 1
                    continue

                # Get file path from library
                library_item = await library_repo.get_by_track_id(track_id)
                if not library_item or not library_item.file_path:
                    logger.warning(f"No file path for track {track_id}, skipping")
                    failed_ids.append(track_id)
                    continue

                # Analyze (quick mode: no ML)
                await analysis_service.analyze_track(
                    track_id=track_id,
                    file_path=library_item.file_path,
                    use_ml=False,
                )
                analyzed_count += 1
                logger.info(f"Analyzed track {track_id} ({analyzed_count}/{len(track_ids)})")

            except Exception as e:
                logger.error(f"Failed to analyze track {track_id}: {e}")
                failed_ids.append(track_id)

    logger.info(
        f"✓ Stage 4: Analyzed {analyzed_count}, "
        f"skipped {skipped_count}, failed {len(failed_ids)}"
    )

    # Save checkpoint
    results = {
        "analyzed": analyzed_count,
        "skipped": skipped_count,
        "failed": len(failed_ids),
        "failed_track_ids": failed_ids,
    }
    self.checkpoint.save(stage_name, results)

    return results
```

**Step 3: Update run() to call stages 3-4**

Update `run()` method:

```python
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

    # Stage 2: Download tracks
    download_stats = await self.stage_2_download_tracks(track_ids)
    logger.info(
        f"Downloaded {download_stats['downloaded']} tracks "
        f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
    )

    # Stage 3: Import metadata
    await self.stage_3_import_metadata(track_ids)

    # Stage 4: Quick analysis
    analysis_stats = await self.stage_4_quick_analysis(track_ids)
    logger.info(f"Quick analysis: {analysis_stats['analyzed']} tracks analyzed")

    logger.info("Workflow stages 1-4 complete")
```

**Step 4: Test Stages 3-4 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Imports metadata for all tracks
- Analyzes audio (BPM, key, energy, etc.)
- Logs analysis stats
- Creates checkpoint `checkpoints/analysis_stage1.json`

**Step 5: Commit Task 4**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stages 3-4 (import metadata + quick analysis)

- Add stage_3_import_metadata() method
- Add stage_4_quick_analysis() method
- Use TrackAnalysisService with use_ml=False (quick mode)
- Analyze BPM, key, energy, spectral, beats, groove
- Save checkpoint with analysis statistics
- Update run() to call stages 3-4"
```

---

## Task 5: Implement Stage 5 (Filter & Select Finalists)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add _score_transition helper method**

Add to `WorkflowOrchestrator` class:

```python
def _score_transition(self, features_a: dict, features_b: dict) -> float:
    """Score transition compatibility between two tracks.

    Uses simplified scoring based on BPM, key, and energy.

    Args:
        features_a: Audio features dict for track A
        features_b: Audio features dict for track B

    Returns:
        Compatibility score 0.0-1.0
    """
    # BPM compatibility (Gaussian, sigma=8)
    bpm_diff = abs(features_a["bpm"] - features_b["bpm"])
    bpm_score = max(0.0, 1.0 - (bpm_diff / 16.0))  # 0 if diff > 16

    # Energy compatibility (prefer smooth transitions)
    energy_diff = abs(features_a["energy_lufs"] - features_b["energy_lufs"])
    energy_score = max(0.0, 1.0 - (energy_diff / 12.0))  # 0 if diff > 12 LUFS

    # Key compatibility (simplified Camelot distance)
    # For now, just prefer same key or ±1 semitone
    key_diff = abs(features_a["key_code"] - features_b["key_code"])
    if key_diff == 0:
        key_score = 1.0
    elif key_diff <= 2:
        key_score = 0.7
    else:
        key_score = 0.3

    # Weighted average
    return 0.4 * bpm_score + 0.3 * key_score + 0.3 * energy_score
```

**Step 2: Add stage_5_select_finalists method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_5_select_finalists(
    self,
    track_ids: list[int],
    target_duration_min: int = 105,
    finalist_range: tuple[int, int] = (15, 25),
) -> list[int]:
    """Stage 5: Filter and select finalist tracks.

    Args:
        track_ids: All track IDs from previous stage
        target_duration_min: Target set duration in minutes
        finalist_range: Min-max finalist count

    Returns:
        List of finalist track IDs
    """
    stage_name = "finalists"

    # Check if checkpoint exists
    if self.checkpoint.exists(stage_name):
        logger.info("✓ Stage 5: Loading from checkpoint")
        data = self.checkpoint.load(stage_name)
        return data["track_ids"]

    logger.info("Stage 5: Filtering and selecting finalists...")

    from app.database import session_factory
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.tracks import TrackRepository

    # Techno criteria
    TECHNO_BPM_RANGE = (125, 135)
    CLUB_ENERGY_RANGE = (-14, -8)  # LUFS
    TRACK_DURATION_RANGE = (300, 600)  # 5-10 minutes in seconds

    candidates = []

    async with session_factory() as session:
        track_repo = TrackRepository(session)
        features_repo = AudioFeaturesRepository(session)

        # Load all tracks with features
        for track_id in track_ids:
            track = await track_repo.get_by_id(track_id)
            features = await features_repo.get_by_track_id(track_id)

            if not track or not features:
                continue

            # Filter by techno criteria
            if not (TECHNO_BPM_RANGE[0] <= features.bpm <= TECHNO_BPM_RANGE[1]):
                continue
            if not (CLUB_ENERGY_RANGE[0] <= features.energy_lufs <= CLUB_ENERGY_RANGE[1]):
                continue
            if not (TRACK_DURATION_RANGE[0] <= track.duration_ms / 1000 <= TRACK_DURATION_RANGE[1]):
                continue

            candidates.append({
                "track_id": track_id,
                "bpm": features.bpm,
                "key_code": features.key_code,
                "energy_lufs": features.energy_lufs,
                "duration_s": track.duration_ms / 1000,
            })

    logger.info(f"Filtered to {len(candidates)} techno-compliant candidates")

    # Score all pairs and select finalists
    finalists = []
    total_duration = 0.0
    target_duration_s = target_duration_min * 60

    # Greedy selection: pick tracks with best average transition score
    while len(finalists) < finalist_range[1] and total_duration < target_duration_s:
        if not candidates:
            break

        if not finalists:
            # Start with first candidate
            first = candidates.pop(0)
            finalists.append(first)
            total_duration += first["duration_s"]
        else:
            # Find candidate with best average score to existing finalists
            best_idx = 0
            best_score = -1.0

            for idx, candidate in enumerate(candidates):
                scores = [
                    self._score_transition(finalist, candidate)
                    for finalist in finalists
                ]
                avg_score = sum(scores) / len(scores)

                if avg_score > best_score:
                    best_score = avg_score
                    best_idx = idx

            # Add best candidate
            best = candidates.pop(best_idx)
            finalists.append(best)
            total_duration += best["duration_s"]

    logger.info(
        f"✓ Stage 5: Selected {len(finalists)} finalists "
        f"({total_duration / 60:.1f} minutes)"
    )

    # Extract just track IDs
    finalist_ids = [f["track_id"] for f in finalists]

    # Save checkpoint (REVIEW POINT!)
    self.checkpoint.save(stage_name, {
        "track_ids": finalist_ids,
        "count": len(finalist_ids),
        "total_duration_minutes": total_duration / 60,
    })

    logger.info(
        "→ REVIEW POINT: Check checkpoints/finalists.json and edit if needed"
    )

    return finalist_ids
```

**Step 3: Update run() to call stage_5**

Update `run()` method:

```python
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

    # Stage 2: Download tracks
    download_stats = await self.stage_2_download_tracks(track_ids)
    logger.info(
        f"Downloaded {download_stats['downloaded']} tracks "
        f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
    )

    # Stage 3: Import metadata
    await self.stage_3_import_metadata(track_ids)

    # Stage 4: Quick analysis
    analysis_stats = await self.stage_4_quick_analysis(track_ids)
    logger.info(f"Quick analysis: {analysis_stats['analyzed']} tracks analyzed")

    # Stage 5: Select finalists
    finalist_ids = await self.stage_5_select_finalists(track_ids)
    logger.info(f"Selected {len(finalist_ids)} finalists for deep analysis")

    logger.info("Workflow stages 1-5 complete")
```

**Step 4: Test Stage 5 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Filters tracks by BPM (125-135), energy (-14 to -8 LUFS), duration (5-10 min)
- Selects 15-25 finalists with best transition compatibility
- Logs finalist count and total duration
- Creates checkpoint `checkpoints/finalists.json`

**Step 5: Commit Task 5**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stage 5 (filter and select finalists)

- Add _score_transition() helper for transition compatibility
- Add stage_5_select_finalists() method
- Filter by techno criteria (BPM 125-135, energy -14 to -8, duration 5-10 min)
- Greedy selection algorithm for best transition scores
- Target 15-25 finalists, 90-120 minutes
- Save checkpoint (REVIEW POINT)
- Update run() to call stage_5"
```

---

## Task 6: Implement Stage 6 (Deep Analysis for Finalists)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add stage_6_deep_analysis method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_6_deep_analysis(self, finalist_ids: list[int]) -> dict:
    """Stage 6: Deep audio analysis for finalist tracks.

    Args:
        finalist_ids: List of finalist track IDs

    Returns:
        Analysis results dict
    """
    stage_name = "analysis_stage2"

    # Check if checkpoint exists
    if self.checkpoint.exists(stage_name):
        logger.info("✓ Stage 6: Loading from checkpoint")
        return self.checkpoint.load(stage_name)

    logger.info(f"Stage 6: Deep analysis for {len(finalist_ids)} finalists...")
    logger.info("This will take ~3-5 minutes per track (ML stem separation)")

    from app.database import session_factory
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.dj_library_items import DjLibraryItemRepository
    from app.repositories.sections import SectionsRepository
    from app.repositories.tracks import TrackRepository
    from app.services.track_analysis import TrackAnalysisService

    analyzed_count = 0
    skipped_count = 0
    failed_ids = []

    async with session_factory() as session:
        track_repo = TrackRepository(session)
        features_repo = AudioFeaturesRepository(session)
        sections_repo = SectionsRepository(session)
        library_repo = DjLibraryItemRepository(session)

        analysis_service = TrackAnalysisService(
            track_repo=track_repo,
            features_repo=features_repo,
            sections_repo=sections_repo,
        )

        for idx, track_id in enumerate(finalist_ids, 1):
            try:
                # Get file path
                library_item = await library_repo.get_by_track_id(track_id)
                if not library_item or not library_item.file_path:
                    logger.warning(f"No file path for track {track_id}, skipping")
                    failed_ids.append(track_id)
                    continue

                # Check if deep analysis already done
                # (we can check for stems-derived features later)

                logger.info(f"Deep analysis {idx}/{len(finalist_ids)}: track {track_id}")

                # Re-analyze with ML (will update existing features)
                await analysis_service.analyze_track(
                    track_id=track_id,
                    file_path=library_item.file_path,
                    use_ml=True,
                )
                analyzed_count += 1

            except Exception as e:
                logger.error(f"Failed deep analysis for track {track_id}: {e}")
                failed_ids.append(track_id)

    logger.info(
        f"✓ Stage 6: Analyzed {analyzed_count}, "
        f"skipped {skipped_count}, failed {len(failed_ids)}"
    )

    # Save checkpoint
    results = {
        "analyzed": analyzed_count,
        "skipped": skipped_count,
        "failed": len(failed_ids),
        "failed_track_ids": failed_ids,
    }
    self.checkpoint.save(stage_name, results)

    return results
```

**Step 2: Update run() to call stage_6**

Update `run()` method:

```python
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

    # Stage 2: Download tracks
    download_stats = await self.stage_2_download_tracks(track_ids)
    logger.info(
        f"Downloaded {download_stats['downloaded']} tracks "
        f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
    )

    # Stage 3: Import metadata
    await self.stage_3_import_metadata(track_ids)

    # Stage 4: Quick analysis
    analysis_stats = await self.stage_4_quick_analysis(track_ids)
    logger.info(f"Quick analysis: {analysis_stats['analyzed']} tracks analyzed")

    # Stage 5: Select finalists
    finalist_ids = await self.stage_5_select_finalists(track_ids)
    logger.info(f"Selected {len(finalist_ids)} finalists for deep analysis")

    # Stage 6: Deep analysis
    deep_stats = await self.stage_6_deep_analysis(finalist_ids)
    logger.info(f"Deep analysis: {deep_stats['analyzed']} tracks analyzed with ML")

    logger.info("Workflow stages 1-6 complete")
```

**Step 3: Test Stage 6 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Deep analysis with Demucs stem separation
- Takes ~3-5 minutes per finalist track
- Logs progress for each track
- Creates checkpoint `checkpoints/analysis_stage2.json`

**Step 4: Commit Task 6**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stage 6 (deep analysis for finalists)

- Add stage_6_deep_analysis() method
- Use TrackAnalysisService with use_ml=True (ML stem separation)
- Analyze stems (kick, bass, melody, vocals) via Demucs
- Extract kick prominence and harmonic-to-noise ratio
- Save checkpoint with analysis statistics
- Update run() to call stage_6"
```

---

## Task 7: Implement Stage 7 (Generate Set with GA)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add stage_7_generate_set method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_7_generate_set(self, finalist_ids: list[int]) -> int:
    """Stage 7: Generate optimized DJ set using genetic algorithm.

    Args:
        finalist_ids: List of finalist track IDs

    Returns:
        Generated set ID
    """
    stage_name = "set_result"

    # Check if checkpoint exists
    if self.checkpoint.exists(stage_name):
        logger.info("✓ Stage 7: Loading from checkpoint")
        data = self.checkpoint.load(stage_name)
        return data["set_id"]

    logger.info("Stage 7: Generating optimized set with genetic algorithm...")

    from app.database import session_factory
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.dj_library_items import DjLibraryItemRepository
    from app.repositories.dj_sets import (
        DjSetItemRepository,
        DjSetRepository,
        DjSetVersionRepository,
    )
    from app.repositories.tracks import TrackRepository
    from app.services.set_generation import SetGenerationService

    async with session_factory() as session:
        set_repo = DjSetRepository(session)
        version_repo = DjSetVersionRepository(session)
        item_repo = DjSetItemRepository(session)
        track_repo = TrackRepository(session)
        features_repo = AudioFeaturesRepository(session)
        library_repo = DjLibraryItemRepository(session)

        set_gen_service = SetGenerationService(
            set_repo=set_repo,
            version_repo=version_repo,
            item_repo=item_repo,
            track_repo=track_repo,
            features_repo=features_repo,
        )

        # Create set record
        dj_set = await set_repo.create(
            name=self.set_name,
            description=f"Professional techno set from playlist '{self.playlist_name}'",
            energy_arc="classic",
        )

        logger.info(f"Created set record: {dj_set.dj_set_id}")

        # Generate optimized version with GA
        version = await set_gen_service.generate_set(
            dj_set_id=dj_set.dj_set_id,
            track_ids=finalist_ids,
            energy_arc="classic",
            target_duration_minutes=105,
        )

        logger.info(
            f"✓ Stage 7: Generated set version {version.version_number} "
            f"with {len(finalist_ids)} tracks"
        )

    # Save checkpoint
    self.checkpoint.save(stage_name, {
        "set_id": dj_set.dj_set_id,
        "version_id": version.dj_set_version_id,
        "version_number": version.version_number,
        "track_count": len(finalist_ids),
    })

    return dj_set.dj_set_id
```

**Step 2: Update run() to call stage_7**

Update `run()` method:

```python
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

    # Stage 2: Download tracks
    download_stats = await self.stage_2_download_tracks(track_ids)
    logger.info(
        f"Downloaded {download_stats['downloaded']} tracks "
        f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
    )

    # Stage 3: Import metadata
    await self.stage_3_import_metadata(track_ids)

    # Stage 4: Quick analysis
    analysis_stats = await self.stage_4_quick_analysis(track_ids)
    logger.info(f"Quick analysis: {analysis_stats['analyzed']} tracks analyzed")

    # Stage 5: Select finalists
    finalist_ids = await self.stage_5_select_finalists(track_ids)
    logger.info(f"Selected {len(finalist_ids)} finalists for deep analysis")

    # Stage 6: Deep analysis
    deep_stats = await self.stage_6_deep_analysis(finalist_ids)
    logger.info(f"Deep analysis: {deep_stats['analyzed']} tracks analyzed with ML")

    # Stage 7: Generate set
    set_id = await self.stage_7_generate_set(finalist_ids)
    logger.info(f"Generated optimized set: {set_id}")

    logger.info("Workflow stages 1-7 complete")
```

**Step 3: Test Stage 7 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Creates DjSet record in database
- Runs GA optimization for track ordering
- Logs set ID and version number
- Creates checkpoint `checkpoints/set_result.json`

**Step 4: Commit Task 7**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stage 7 (generate set with GA)

- Add stage_7_generate_set() method
- Use SetGenerationService for GA optimization
- Create DjSet record with name and description
- Generate optimized version with classic energy arc
- Save checkpoint with set_id and version info
- Update run() to call stage_7"
```

---

## Task 8: Implement Stage 8 (Export to Rekordbox/M3U/JSON)

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add stage_8_export method**

Add to `WorkflowOrchestrator` class:

```python
async def stage_8_export(self, set_id: int) -> dict[str, Path]:
    """Stage 8: Export set to Rekordbox XML, M3U, and JSON.

    Args:
        set_id: DJ set ID to export

    Returns:
        Dict mapping format name to file path
    """
    stage_name = "exports"

    # Check if checkpoint exists
    if self.checkpoint.exists(stage_name):
        logger.info("✓ Stage 8: Loading from checkpoint")
        data = self.checkpoint.load(stage_name)
        return {k: Path(v) for k, v in data["file_paths"].items()}

    logger.info("Stage 8: Exporting set to Rekordbox XML, M3U, JSON...")

    from app.database import session_factory
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.dj_library_items import DjLibraryItemRepository
    from app.repositories.dj_sets import (
        DjSetItemRepository,
        DjSetRepository,
        DjSetVersionRepository,
    )
    from app.repositories.tracks import TrackRepository
    from app.services.set_export import (
        export_json_guide,
        export_m3u,
        export_rekordbox_xml,
    )

    file_paths = {}

    async with session_factory() as session:
        set_repo = DjSetRepository(session)
        version_repo = DjSetVersionRepository(session)
        item_repo = DjSetItemRepository(session)
        track_repo = TrackRepository(session)
        features_repo = AudioFeaturesRepository(session)
        library_repo = DjLibraryItemRepository(session)

        # Get set and latest version
        dj_set = await set_repo.get_by_id(set_id)
        if not dj_set:
            raise ValueError(f"Set {set_id} not found")

        versions = await version_repo.list_by_set(set_id)
        if not versions:
            raise ValueError(f"No versions found for set {set_id}")

        latest_version = versions[0]  # Already sorted by version_number DESC

        # Get set items (ordered)
        items, _ = await item_repo.list_by_version(
            latest_version.dj_set_version_id,
            offset=0,
            limit=1000,
        )

        # Build track data for export
        tracks_data = []
        for item in items:
            track = await track_repo.get_by_id(item.track_id)
            features = await features_repo.get_by_track_id(item.track_id)
            library_item = await library_repo.get_by_track_id(item.track_id)

            if not track or not features or not library_item:
                logger.warning(f"Missing data for track {item.track_id}, skipping")
                continue

            tracks_data.append({
                "track_id": track.track_id,
                "title": track.title,
                "artists": ", ".join([a.name for a in track.artists]) if track.artists else "",
                "duration_s": track.duration_ms / 1000,
                "path": library_item.file_path,
                "bpm": features.bpm,
                "key": features.key_code,  # Will be converted to Camelot
                "energy": features.energy_lufs,
            })

        # Export Rekordbox XML
        xml_path = self.set_dir / f"{self.set_name}.xml"
        xml_content = export_rekordbox_xml(
            tracks=tracks_data,
            set_name=self.set_name,
        )
        xml_path.write_text(xml_content)
        file_paths["rekordbox_xml"] = xml_path
        logger.info(f"✓ Exported Rekordbox XML: {xml_path}")

        # Export M3U
        m3u_path = self.set_dir / f"{self.set_name}.m3u8"
        m3u_content = export_m3u(
            tracks=tracks_data,
            set_name=self.set_name,
        )
        m3u_path.write_text(m3u_content)
        file_paths["m3u"] = m3u_path
        logger.info(f"✓ Exported M3U: {m3u_path}")

        # Export JSON guide
        json_path = self.set_dir / f"{self.set_name}_guide.json"
        json_content = export_json_guide(
            tracks=tracks_data,
            set_name=self.set_name,
        )
        json_path.write_text(json_content)
        file_paths["json_guide"] = json_path
        logger.info(f"✓ Exported JSON guide: {json_path}")

    logger.info("✓ Stage 8: All exports complete")

    # Save checkpoint
    self.checkpoint.save(stage_name, {
        "file_paths": {k: str(v) for k, v in file_paths.items()},
    })

    return file_paths
```

**Step 2: Update run() to call stage_8**

Update `run()` method:

```python
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

    # Stage 2: Download tracks
    download_stats = await self.stage_2_download_tracks(track_ids)
    logger.info(
        f"Downloaded {download_stats['downloaded']} tracks "
        f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
    )

    # Stage 3: Import metadata
    await self.stage_3_import_metadata(track_ids)

    # Stage 4: Quick analysis
    analysis_stats = await self.stage_4_quick_analysis(track_ids)
    logger.info(f"Quick analysis: {analysis_stats['analyzed']} tracks analyzed")

    # Stage 5: Select finalists
    finalist_ids = await self.stage_5_select_finalists(track_ids)
    logger.info(f"Selected {len(finalist_ids)} finalists for deep analysis")

    # Stage 6: Deep analysis
    deep_stats = await self.stage_6_deep_analysis(finalist_ids)
    logger.info(f"Deep analysis: {deep_stats['analyzed']} tracks analyzed with ML")

    # Stage 7: Generate set
    set_id = await self.stage_7_generate_set(finalist_ids)
    logger.info(f"Generated optimized set: {set_id}")

    # Stage 8: Export
    exports = await self.stage_8_export(set_id)
    logger.info("Exported files:")
    for format_name, path in exports.items():
        logger.info(f"  - {format_name}: {path}")

    logger.info("=" * 60)
    logger.info("✓ WORKFLOW COMPLETE!")
    logger.info(f"Set directory: {self.set_dir}")
    logger.info("Next steps:")
    logger.info("  1. Review JSON guide for DJ notes")
    logger.info("  2. Import Rekordbox XML into Rekordbox")
    logger.info("  3. Load M3U into djay Pro")
    logger.info("=" * 60)
```

**Step 3: Test Stage 8 manually**

```bash
python scripts/complete_workflow.py
```

Expected:
- Exports Rekordbox XML with full metadata
- Exports Extended M3U with DJ metadata
- Exports JSON guide with transitions and notes
- Logs file paths
- Creates checkpoint `checkpoints/exports.json`

**Step 4: Commit Task 8**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: implement Stage 8 (export to Rekordbox/M3U/JSON)

- Add stage_8_export() method
- Use export_rekordbox_xml(), export_m3u(), export_json_guide()
- Export to set directory with set name
- Save checkpoint with file paths
- Update run() to call stage_8 and print completion summary
- Complete workflow now runs all 8 stages end-to-end"
```

---

## Task 9: Add Error Handling and Logging

**Files:**
- Modify: `scripts/complete_workflow.py`

**Step 1: Add workflow.log file handler**

Update `WorkflowOrchestrator.__init__`:

```python
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

    # Set up file logging
    self.set_dir.mkdir(parents=True, exist_ok=True)
    log_file = self.set_dir / "workflow.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(file_handler)

    logger.info(f"Initialized workflow for set: {self.set_name}")
    logger.info(f"Output directory: {self.set_dir}")
    logger.info(f"Log file: {log_file}")
```

**Step 2: Wrap run() with try-except**

Update `run()` method:

```python
async def run(self) -> None:
    """Run complete workflow from start to finish."""
    try:
        logger.info("Starting complete workflow...")

        # Create directory structure
        self.set_dir.mkdir(parents=True, exist_ok=True)
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logger.info("✓ Directory structure created")

        # Stage 1: Fetch playlist
        track_ids = await self.stage_1_fetch_playlist()
        logger.info(f"Playlist contains {len(track_ids)} tracks")

        # Stage 2: Download tracks
        download_stats = await self.stage_2_download_tracks(track_ids)
        logger.info(
            f"Downloaded {download_stats['downloaded']} tracks "
            f"({download_stats['total_bytes'] / 1024 / 1024:.1f} MB)"
        )

        # Validate: at least 15 tracks downloaded
        if download_stats['downloaded'] < 15:
            raise ValueError(
                f"Only {download_stats['downloaded']} tracks downloaded, "
                "need at least 15 for a set"
            )

        # Stage 3: Import metadata
        await self.stage_3_import_metadata(track_ids)

        # Stage 4: Quick analysis
        analysis_stats = await self.stage_4_quick_analysis(track_ids)
        logger.info(f"Quick analysis: {analysis_stats['analyzed']} tracks analyzed")

        # Stage 5: Select finalists
        finalist_ids = await self.stage_5_select_finalists(track_ids)
        logger.info(f"Selected {len(finalist_ids)} finalists for deep analysis")

        # Validate: finalists in range
        if not (15 <= len(finalist_ids) <= 25):
            logger.warning(
                f"Finalist count {len(finalist_ids)} outside expected range 15-25"
            )

        # Stage 6: Deep analysis
        deep_stats = await self.stage_6_deep_analysis(finalist_ids)
        logger.info(f"Deep analysis: {deep_stats['analyzed']} tracks analyzed with ML")

        # Stage 7: Generate set
        set_id = await self.stage_7_generate_set(finalist_ids)
        logger.info(f"Generated optimized set: {set_id}")

        # Stage 8: Export
        exports = await self.stage_8_export(set_id)
        logger.info("Exported files:")
        for format_name, path in exports.items():
            logger.info(f"  - {format_name}: {path}")

        logger.info("=" * 60)
        logger.info("✓ WORKFLOW COMPLETE!")
        logger.info(f"Set directory: {self.set_dir}")
        logger.info("Next steps:")
        logger.info("  1. Review JSON guide for DJ notes")
        logger.info("  2. Import Rekordbox XML into Rekordbox")
        logger.info("  3. Load M3U into djay Pro")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        logger.error("Check workflow.log for details")
        logger.error(f"You can resume from last checkpoint in: {self.checkpoint_dir}")
        raise
```

**Step 3: Test error handling**

```bash
# Test with invalid playlist name (should fail at Stage 1)
python scripts/complete_workflow.py --playlist "Nonexistent Playlist"
```

Expected: Error logged to workflow.log, exception raised

**Step 4: Commit Task 9**

```bash
git add scripts/complete_workflow.py
git commit -m "feat: add error handling and file logging

- Add workflow.log file handler to WorkflowOrchestrator
- Wrap run() in try-except for graceful error handling
- Add validation gates (min 15 downloads, finalist range check)
- Log errors with traceback to workflow.log
- Print checkpoint directory on failure for resume"
```

---

## Task 10: Add Integration Test

**Files:**
- Create: `tests/workflows/test_complete_workflow.py`
- Create: `tests/workflows/__init__.py`

**Step 1: Write integration test skeleton**

Create: `tests/workflows/__init__.py` (empty file)

Create: `tests/workflows/test_complete_workflow.py`

```python
"""Integration tests for complete workflow orchestrator."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.complete_workflow import WorkflowOrchestrator

@pytest.fixture
def temp_workflow_dir(tmp_path):
    """Create temporary workflow directory."""
    return tmp_path

@pytest.fixture
def mock_ym_client():
    """Mock Yandex Music client."""
    client = AsyncMock()

    # Mock playlist
    mock_playlist = MagicMock()
    mock_playlist.title = "Test Playlist"
    mock_playlist.kind = 123

    client.get_playlists_list.return_value = [mock_playlist]

    # Mock playlist details with tracks
    mock_playlist_details = MagicMock()
    mock_track_1 = MagicMock()
    mock_track_1.id = 1
    mock_track_2 = MagicMock()
    mock_track_2.id = 2
    mock_playlist_details.tracks = [mock_track_1, mock_track_2]

    client.get_playlist.return_value = mock_playlist_details

    return client

@pytest.mark.asyncio
async def test_stage_1_fetch_playlist(temp_workflow_dir, mock_ym_client):
    """Test Stage 1 fetches playlist and saves checkpoint."""
    orchestrator = WorkflowOrchestrator(
        base_dir=temp_workflow_dir,
        playlist_name="Test Playlist",
    )

    with patch("scripts.complete_workflow.YandexMusicClient", return_value=mock_ym_client):
        track_ids = await orchestrator.stage_1_fetch_playlist()

    # Verify track IDs returned
    assert track_ids == [1, 2]

    # Verify checkpoint created
    assert orchestrator.checkpoint.exists("playlist")
    checkpoint_data = orchestrator.checkpoint.load("playlist")
    assert checkpoint_data["track_ids"] == [1, 2]
    assert checkpoint_data["track_count"] == 2

@pytest.mark.asyncio
async def test_checkpoint_resume(temp_workflow_dir):
    """Test workflow resumes from checkpoint."""
    orchestrator = WorkflowOrchestrator(
        base_dir=temp_workflow_dir,
        playlist_name="Test Playlist",
    )

    # Manually create checkpoint
    orchestrator.checkpoint.save("playlist", {
        "playlist_name": "Test Playlist",
        "track_ids": [10, 20, 30],
        "track_count": 3,
    })

    # Call stage_1 — should load from checkpoint, not hit YM API
    track_ids = await orchestrator.stage_1_fetch_playlist()

    # Verify loaded from checkpoint
    assert track_ids == [10, 20, 30]
```

**Step 2: Run test**

```bash
pytest tests/workflows/test_complete_workflow.py -v
```

Expected: PASS (2 tests green)

**Step 3: Commit Task 10**

```bash
git add tests/workflows/
git commit -m "test: add integration tests for workflow orchestrator

- Test Stage 1 fetch playlist with mocked YM client
- Test checkpoint resume (load instead of re-fetch)
- Use AsyncMock for YandexMusicClient
- Verify checkpoint save/load behavior"
```

---

## Task 11: Documentation and README

**Files:**
- Create: `scripts/README.md`

**Step 1: Write scripts README**

Create: `scripts/README.md`

```markdown
# Complete Workflow Scripts

Automated workflows for professional DJ set creation.

## complete_workflow.py

Creates professional techno DJ sets from Yandex Music playlists with adaptive audio analysis, genetic algorithm optimization, and multi-format export.

### Usage

```bash
python scripts/complete_workflow.py \
  --playlist "Techno develop Recs" \
  --base-dir "/path/to/output"
```

### Arguments

- `--playlist`: Yandex Music playlist name (default: "Techno develop Recs")
- `--base-dir`: Base directory for sets (default: iCloud path)

### Workflow Stages

1. **Fetch Playlist**: Get tracks from Yandex Music
2. **Download Tracks**: Download MP3s (320 kbps)
3. **Import Metadata**: Ensure tracks in database
4. **Quick Analysis**: BPM, key, energy, spectral (all tracks)
5. **Select Finalists**: Filter by techno criteria, select 15-25 tracks
6. **Deep Analysis**: ML stem separation (finalists only)
7. **Generate Set**: GA optimization with classic energy arc
8. **Export**: Rekordbox XML, M3U, JSON guide

### Checkpoints

Checkpoint files saved to `sets/<set-name>/checkpoints/`:

- `playlist.json` — track IDs from playlist
- `downloads.json` — download statistics
- `analysis_stage1.json` — quick analysis results
- `finalists.json` — selected finalist track IDs (**REVIEW POINT**)
- `analysis_stage2.json` — deep analysis results
- `set_result.json` — generated set ID
- `exports.json` — export file paths

**Resume from checkpoint:** Re-run the script — it will auto-detect checkpoints and resume.

### Output Structure

```text
sets/techno-professional-2026-02-17/
├── tracks/
│   ├── 12345_fire_eyes.mp3
│   └── ...
├── checkpoints/
│   ├── playlist.json
│   └── ...
├── techno-professional-2026-02-17.xml      (Rekordbox)
├── techno-professional-2026-02-17.m3u8     (Extended M3U)
├── techno-professional-2026-02-17_guide.json
└── workflow.log
```

### Requirements

- Python 3.12+
- `uv sync --extra audio --extra ml`
- Yandex Music account with playlist access

### Techno Filtering Criteria

- **BPM**: 125-135
- **Energy**: -14 to -8 LUFS (club-ready)
- **Duration**: 5-10 minutes
- **Key**: Minor keys preferred (Camelot 1A-12A)

### Estimated Runtime

- Stage 1: ~10 seconds
- Stage 2: ~2-5 minutes (depends on track count and bitrate)
- Stage 3: ~5 seconds
- Stage 4: ~30-60 seconds per track (quick analysis)
- Stage 5: ~10 seconds
- Stage 6: ~3-5 minutes per finalist (ML stem separation)
- Stage 7: ~30 seconds (GA optimization)
- Stage 8: ~5 seconds

**Total**: ~45-90 minutes for 50 tracks → 20 finalists

### Troubleshooting

**Playlist not found:**
- Check playlist name spelling
- Verify playlist is public or owned by user 250905515

**Download failures:**
- Check network connection
- Verify Yandex Music credentials
- Check `workflow.log` for details

**Analysis errors:**
- Ensure `audio` and `ml` extras installed: `uv sync --extra audio --extra ml`
- Check audio file integrity (corrupt downloads)

**Insufficient finalists:**
- Relax techno criteria in code (BPM range, energy range)
- Use different source playlist with more techno tracks
```bash

**Step 2: Commit Task 11**

```bash
git add scripts/README.md
git commit -m "docs: add README for complete_workflow script

- Document usage, arguments, workflow stages
- Explain checkpoint system and resume behavior
- Show output structure
- List techno filtering criteria
- Add estimated runtime breakdown
- Include troubleshooting section"
```

---

## Execution Plan Complete

**Plan saved to:** `docs/plans/2026-02-17-professional-techno-set-workflow-plan.md`

**Summary:**
- 11 tasks covering full workflow implementation
- Checkpoint system for recovery and review
- 8-stage pipeline: fetch → download → analyze → generate → export
- Integration tests for Stage 1 and checkpoint resume
- Complete documentation in `scripts/README.md`

**Estimated Total Time:** 3-4 hours for implementation + testing

---

**Next Steps: Choose Execution Approach**

**Option 1: Subagent-Driven (this session)**
- I dispatch fresh subagent per task
- Review between tasks
- Fast iteration
- **REQUIRED SUB-SKILL:** superpowers:subagent-driven-development

**Option 2: Parallel Session (separate)**
- Open new session with executing-plans
- Batch execution with checkpoints
- **REQUIRED SUB-SKILL:** New session uses superpowers:executing-plans

**Which approach do you prefer?**
