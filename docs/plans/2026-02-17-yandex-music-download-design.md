# Yandex Music Track Download Design

**Date:** 2026-02-17
**Status:** Approved
**Author:** Claude Opus 4.6

## Overview

Add functionality to download MP3 files from Yandex Music API and store them locally in iCloud for DJ library management. Extends existing MCP tools with file download capabilities while following the project's Router→Service→Repository architecture.

## Problem Statement

Currently, the system stores only track metadata (title, BPM, key) without actual audio files. The Rekordbox XML export generates virtual file paths (`file://localhost/Music/001.%20Nova.mp3`) that don't point to real files. Users need actual MP3 files to use exported playlists in djay Pro AI or other DJ software.

## Requirements

From user clarifications:
1. **Storage location:** iCloud (`~/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/library/`)
2. **File organization:** Flat structure (all files in one directory)
3. **Duplicate handling:** Skip existing files (check `file_path` in `DjLibraryItem`)
4. **Integration:** Two workflows:
   - Auto-download during playlist import (`download_files=True`)
   - Explicit batch download (`dj_download_tracks`)
5. **Error handling:** Retry with exponential backoff (3 attempts: 1s/2s/4s), continue on errors, return statistics

## Architecture

### Component Hierarchy

```text
MCP Tools (app/mcp/workflows/import_tools.py)
  ├─ dj_import_playlist(download_files=True)  — extend existing
  └─ dj_download_tracks(track_ids)            — new tool
           ↓
DownloadService (app/services/download.py) — new
  ├─ download_tracks_batch(track_ids, prefer_bitrate)
  └─ _download_single_track(track, max_retries=3)
           ↓
DjLibraryItemRepository (app/repositories/dj_library_items.py) — new
  ├─ get_by_track_id(track_id)
  ├─ create_from_download(...)
  └─ update(...)
           ↓
YandexMusicClient (app/services/yandex_music_client.py) — existing
  └─ download_track(track_id, dest_path, prefer_bitrate)
```

### Data Flow

1. **MCP tool** receives `track_ids: list[int]`
2. **DownloadService** queries `DjLibraryItemRepository`:
   - If `file_path` exists → skip (increment `skipped` counter)
   - If not → proceed to download
3. **For each new track:**
   - Get YM `track_id` from `provider_ids` table
   - Generate filename: `{track_id}_{sanitized_title}.mp3`
   - Call `YandexMusicClient.download_track()` with retry logic
   - Calculate SHA256 hash
   - Create `DjLibraryItem` record with file metadata
4. **Return statistics:** `DownloadResult(downloaded, skipped, failed, failed_track_ids, total_bytes)`

## Components

### 1. DjLibraryItemRepository

**File:** `app/repositories/dj_library_items.py`

```python
from app.models.dj import DjLibraryItem
from app.repositories.base import BaseRepository

class DjLibraryItemRepository(BaseRepository[DjLibraryItem]):
    """Repository for DJ library file management."""

    async def get_by_track_id(self, track_id: int) -> DjLibraryItem | None:
        """Find library item for a track."""
        stmt = select(DjLibraryItem).where(DjLibraryItem.track_id == track_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_from_download(
        self,
        track_id: int,
        file_path: str,
        file_size: int,
        file_hash: bytes,
        bitrate_kbps: int,
        mime_type: str = "audio/mpeg",
    ) -> DjLibraryItem:
        """Create library item after successful download."""
        item = DjLibraryItem(
            track_id=track_id,
            file_path=file_path,
            file_size_bytes=file_size,
            file_hash=file_hash,
            bitrate_kbps=bitrate_kbps,
            mime_type=mime_type,
        )
        self.session.add(item)
        await self.session.flush()
        return item
```

### 2. DownloadService

**File:** `app/services/download.py`

```python
from dataclasses import dataclass
from pathlib import Path
import hashlib
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.yandex_music_client import YandexMusicClient
from app.repositories.dj_library_items import DjLibraryItemRepository
from app.repositories.tracks import TrackRepository

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    """Statistics from batch download operation."""
    downloaded: int
    skipped: int
    failed: int
    failed_track_ids: list[int]
    total_bytes: int

class DownloadService:
    """Service for downloading tracks from Yandex Music."""

    def __init__(
        self,
        session: AsyncSession,
        ym_client: YandexMusicClient,
        library_path: Path,
    ):
        self.session = session
        self.ym_client = ym_client
        self.library_path = library_path
        self.library_repo = DjLibraryItemRepository(session)
        self.track_repo = TrackRepository(session)

    async def download_tracks_batch(
        self,
        track_ids: list[int],
        prefer_bitrate: int = 320,
    ) -> DownloadResult:
        """Download multiple tracks with retry and statistics.

        Args:
            track_ids: List of track IDs to download
            prefer_bitrate: Preferred bitrate in kbps (default: 320)

        Returns:
            DownloadResult with download statistics
        """
        # Ensure library directory exists
        self.library_path.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        skipped = 0
        failed = 0
        failed_ids: list[int] = []
        total_bytes = 0

        for track_id in track_ids:
            # Check if already downloaded
            existing = await self.library_repo.get_by_track_id(track_id)
            if existing and existing.file_path:
                logger.info(f"Track {track_id} already downloaded, skipping")
                skipped += 1
                continue

            # Get track from DB
            track = await self.track_repo.get(track_id)
            if not track:
                logger.warning(f"Track {track_id} not found in database")
                failed += 1
                failed_ids.append(track_id)
                continue

            # Download with retry
            success, size = await self._download_single_track(
                track, prefer_bitrate, max_retries=3
            )

            if success:
                downloaded += 1
                total_bytes += size
            else:
                failed += 1
                failed_ids.append(track_id)

        logger.info(
            f"Download batch complete: {downloaded} downloaded, "
            f"{skipped} skipped, {failed} failed"
        )

        return DownloadResult(
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            failed_track_ids=failed_ids,
            total_bytes=total_bytes,
        )

    async def _download_single_track(
        self,
        track,
        prefer_bitrate: int,
        max_retries: int = 3,
    ) -> tuple[bool, int]:
        """Download single track with exponential backoff retry.

        Returns:
            (success: bool, file_size: int)
        """
        for attempt in range(max_retries):
            try:
                # 1. Get Yandex Music track ID from provider_ids
                ym_id = await self._get_yandex_track_id(track.track_id)
                if not ym_id:
                    logger.error(f"No Yandex Music ID for track {track.track_id}")
                    return (False, 0)

                # 2. Generate filename
                filename = self._generate_filename(track)
                dest_path = self.library_path / filename

                # 3. Download via YM client
                size = await self.ym_client.download_track(
                    ym_id, str(dest_path), prefer_bitrate=prefer_bitrate
                )

                # 4. Calculate SHA256 hash
                file_hash = hashlib.sha256(dest_path.read_bytes()).digest()

                # 5. Save to DjLibraryItem
                await self.library_repo.create_from_download(
                    track_id=track.track_id,
                    file_path=str(dest_path),
                    file_size=size,
                    file_hash=file_hash,
                    bitrate_kbps=prefer_bitrate,
                )

                logger.info(f"Downloaded track {track.track_id} ({size} bytes)")
                return (True, size)

            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Download attempt {attempt + 1} failed for track "
                        f"{track.track_id}, retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to download track {track.track_id} after "
                        f"{max_retries} attempts: {e}"
                    )
                    return (False, 0)

        return (False, 0)

    async def _get_yandex_track_id(self, track_id: int) -> str | None:
        """Get Yandex Music track ID from provider_ids table."""
        from app.models.providers import ProviderId
        from sqlalchemy import select

        stmt = (
            select(ProviderId.value)
            .where(ProviderId.track_id == track_id)
            .where(ProviderId.provider == "yandex")
            .where(ProviderId.id_type == "track")
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _generate_filename(self, track) -> str:
        """Generate sanitized filename for track."""
        sanitized = self._sanitize_filename(track.title)
        return f"{track.track_id}_{sanitized}.mp3"

    @staticmethod
    def _sanitize_filename(title: str, max_len: int = 50) -> str:
        """Sanitize title for use in filename."""
        import re
        # Remove special characters: / \ : * ? " < > |
        safe = re.sub(r'[/\\:*?"<>|]', '', title)
        # Replace spaces with underscores
        safe = safe.replace(' ', '_')
        # Lowercase
        safe = safe.lower()
        # Truncate to max_len
        safe = safe[:max_len]
        # Remove trailing underscores
        safe = safe.rstrip('_')
        return safe or "untitled"
```

### 3. MCP Tools

**File:** `app/mcp/workflows/import_tools.py` (extend existing)

```python
from app.services.download import DownloadService, DownloadResult
from app.config import settings
from pathlib import Path

@mcp.tool(
    name="download_tracks",
    description="Download MP3 files for tracks from Yandex Music to iCloud library",
    tags=["download", "yandex"],
    annotations={"readonly": False},
)
async def download_tracks(
    track_ids: list[int],
    prefer_bitrate: int = 320,
    ctx: Context = None,
    track_svc: TrackService = Depends(get_track_service),
    ym_client: YandexMusicClient = Depends(get_ym_client),
) -> DownloadResult:
    """Download tracks from Yandex Music to local library.

    Args:
        track_ids: List of track IDs to download
        prefer_bitrate: Preferred bitrate in kbps (default: 320)

    Returns:
        Download statistics (downloaded, skipped, failed counts)
    """
    library_path = Path(settings.dj_library_path)  # iCloud path from config

    download_svc = DownloadService(
        session=track_svc.session,
        ym_client=ym_client,
        library_path=library_path,
    )

    result = await download_svc.download_tracks_batch(
        track_ids=track_ids,
        prefer_bitrate=prefer_bitrate,
    )

    return result

# Extend existing import_playlist tool
@mcp.tool(name="import_playlist", ...)
async def import_playlist(
    source: str,
    playlist_id: str,
    download_files: bool = False,  # NEW parameter
    ...
) -> ImportResult:
    """Import playlist metadata and optionally download files."""
    # ... existing import logic ...

    if download_files and imported_track_ids:
        library_path = Path(settings.dj_library_path)
        download_svc = DownloadService(
            session=session,
            ym_client=ym_client,
            library_path=library_path,
        )
        download_result = await download_svc.download_tracks_batch(imported_track_ids)
        # Add download stats to ImportResult
        result.downloaded_count = download_result.downloaded
        result.download_failed_count = download_result.failed

    return result
```

## Configuration

**File:** `app/config.py` (add new setting)

```python
class Settings(BaseSettings):
    # ... existing settings ...

    dj_library_path: str = Field(
        default="~/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/library",
        description="Path to DJ library directory for downloaded files"
    )
```

## Error Handling

### Retry Strategy

| Error Type | Retry? | Backoff |
|------------|--------|---------|
| `httpx.ConnectTimeout` | ✅ Yes | Exponential (1s, 2s, 4s) |
| `httpx.ReadTimeout` | ✅ Yes | Exponential |
| `httpx.HTTPStatusError` 5xx | ✅ Yes | Exponential |
| `httpx.HTTPStatusError` 4xx | ❌ No | Skip track |
| `IOError` (disk full) | ❌ No | Abort batch |
| Missing YM track_id | ❌ No | Skip track |

### Error Flow

1. **Network errors (timeout, 5xx):** Retry with exponential backoff (max 3 attempts)
2. **Client errors (4xx):** Log and skip, add to `failed_track_ids`
3. **Missing YM ID:** Log warning, skip, add to `failed_track_ids`
4. **Disk errors:** Log error, abort remaining downloads, return partial results
5. **All failures:** Return `DownloadResult` with `failed` count and `failed_track_ids` list

### Logging

- **INFO:** Batch start/completion, successful downloads, skipped files
- **WARNING:** Retry attempts with delay information
- **ERROR:** Final failures after max retries, missing track IDs, disk errors

## Testing Strategy

### Unit Tests

**File:** `tests/services/test_download_service.py`

```python
class TestDownloadService:
    async def test_download_single_track_success(self, mock_ym_client, tmp_path):
        """Successful download creates file and DjLibraryItem."""

    async def test_download_single_track_retry_succeeds_on_second_attempt(self):
        """Retry after network error succeeds on second attempt."""

    async def test_download_single_track_fails_after_max_retries(self):
        """After 3 failures returns (False, 0)."""

    async def test_download_batch_skips_existing(self):
        """Tracks with file_path in DjLibraryItem are skipped."""

    async def test_download_batch_partial_failure(self):
        """Batch with partial errors returns correct statistics."""

    async def test_sanitize_filename(self):
        """Filename sanitization removes special chars and limits length."""
```

### Integration Tests

**File:** `tests/mcp/test_download_tools.py`

```python
class TestDownloadTools:
    async def test_download_tracks_tool_creates_files(self, client, session):
        """MCP tool download_tracks creates files in library path."""

    async def test_import_playlist_with_download_files_true(self, client):
        """import_playlist(download_files=True) downloads tracks."""

    async def test_download_tracks_returns_statistics(self):
        """Tool returns DownloadResult with correct counts."""
```

### Mocking Strategy

- **YandexMusicClient:** Mock `download_track()` to return fake file size without real HTTP
- **FileSystem:** Use pytest `tmp_path` fixture for isolated test directories
- **Database:** Use existing in-memory SQLite fixtures from `tests/conftest.py`

## File Naming

### Sanitization Rules

```python
def _sanitize_filename(title: str, max_len: int = 50) -> str:
    """
    1. Remove special characters: / \ : * ? " < > |
    2. Replace spaces with underscores
    3. Convert to lowercase
    4. Truncate to max_len (default: 50)
    5. Remove trailing underscores
    6. Return "untitled" if empty after sanitization
    """
```

### Examples

| Input Title | Output Filename |
|-------------|-----------------|
| `"Nova"` | `42_nova.mp3` |
| `"Fire Eyes"` | `137_fire_eyes.mp3` |
| `"Track / Name?"` | `999_track_name.mp3` |
| `"Very Long Track Title That Exceeds Maximum Length"` | `1_very_long_track_title_that_exceeds_maximum.mp3` |

### Collision Handling

If filename already exists (rare due to `track_id` prefix), append counter:
- `42_nova.mp3` → `42_nova_1.mp3` → `42_nova_2.mp3`

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Track without YM ID in `provider_ids` | Skip, add to `failed_track_ids`, log error |
| Title > 255 characters | Truncate to 50 in `sanitize_filename()` |
| Duplicate filename | Append `_{counter}` suffix (rare due to track_id prefix) |
| iCloud directory doesn't exist | Create via `Path.mkdir(parents=True, exist_ok=True)` |
| Disk full (`IOError`) | Abort batch, return partial `DownloadResult` |
| YM API rate limit (HTTP 429) | Retry with exponential backoff (treated as 5xx) |
| Empty track_ids list | Return `DownloadResult(0, 0, 0, [], 0)` immediately |

## Implementation Checklist

- [ ] Create `DjLibraryItemRepository` with tests
- [ ] Create `DownloadService` with unit tests
- [ ] Add `dj_library_path` to Settings
- [ ] Implement `download_tracks` MCP tool
- [ ] Extend `import_playlist` with `download_files` parameter
- [ ] Add integration tests for MCP tools
- [ ] Update Rekordbox XML export to use real file paths from `DjLibraryItem`
- [ ] Update documentation in CLAUDE.md

## Future Enhancements

- [ ] Progress reporting via MCP Context (streaming updates)
- [ ] Concurrent downloads with semaphore (limit parallel requests)
- [ ] Resume partial downloads (check file size before overwriting)
- [ ] Cleanup orphaned files (files without DjLibraryItem record)
- [ ] Support for other providers (Spotify, SoundCloud) via adapter pattern
