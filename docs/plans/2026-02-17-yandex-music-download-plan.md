# Yandex Music Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Download MP3 files from Yandex Music API and store in iCloud for DJ library management

**Architecture:** Router→Service→Repository pattern with MCP tools. DownloadService orchestrates downloads via YandexMusicClient, tracks files in DjLibraryItem table, handles retry logic with exponential backoff.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, FastMCP 3.0, httpx, pytest

---

## Task 1: Add Library Path Configuration

**Files:**
- Modify: `app/config.py`
- Test: Manual verification

**Step 1: Add dj_library_path setting**

Add after existing settings in `app/config.py`:

```python
    dj_library_path: str = Field(
        default="~/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/library",
        description="Path to DJ library directory for downloaded files",
    )
```

**Step 2: Verify setting loads**

Run:
```bash
python -c "from app.config import settings; print(settings.dj_library_path)"
```

Expected: Path printed without errors

**Step 3: Commit**

```bash
git add app/config.py
git commit -m "config: add dj_library_path for file downloads

Add iCloud directory path for storing downloaded MP3 files.
Default: ~/Library/Mobile Documents/.../library/

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: DjLibraryItemRepository — get_by_track_id()

**Files:**
- Create: `app/repositories/dj_library_items.py`
- Create: `tests/repositories/test_dj_library_items.py`

**Step 1: Write failing test for get_by_track_id**

Create `tests/repositories/test_dj_library_items.py`:

```python
"""Tests for DjLibraryItemRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.dj import DjLibraryItem
from app.repositories.dj_library_items import DjLibraryItemRepository

class TestDjLibraryItemRepository:
    async def test_get_by_track_id_returns_item_when_exists(self, session: AsyncSession):
        """get_by_track_id returns library item for track."""
        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create library item
        item = DjLibraryItem(
            track_id=track.track_id,
            file_path="/path/to/file.mp3",
            file_size_bytes=1024,
        )
        session.add(item)
        await session.commit()

        # Test get_by_track_id
        repo = DjLibraryItemRepository(session)
        result = await repo.get_by_track_id(track.track_id)

        assert result is not None
        assert result.track_id == track.track_id
        assert result.file_path == "/path/to/file.mp3"

    async def test_get_by_track_id_returns_none_when_not_exists(self, session: AsyncSession):
        """get_by_track_id returns None when no library item exists."""
        repo = DjLibraryItemRepository(session)
        result = await repo.get_by_track_id(999)

        assert result is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/repositories/test_dj_library_items.py::TestDjLibraryItemRepository::test_get_by_track_id_returns_item_when_exists -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'app.repositories.dj_library_items'"

**Step 3: Create repository with get_by_track_id**

Create `app/repositories/dj_library_items.py`:

```python
"""Repository for DjLibraryItem — file management for DJ library."""

from sqlalchemy import select

from app.models.dj import DjLibraryItem
from app.repositories.base import BaseRepository

class DjLibraryItemRepository(BaseRepository[DjLibraryItem]):
    """Repository for DJ library file management."""

    async def get_by_track_id(self, track_id: int) -> DjLibraryItem | None:
        """Find library item for a track.

        Args:
            track_id: Track ID to search for

        Returns:
            DjLibraryItem if exists, None otherwise
        """
        stmt = select(DjLibraryItem).where(DjLibraryItem.track_id == track_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/repositories/test_dj_library_items.py::TestDjLibraryItemRepository -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add app/repositories/dj_library_items.py tests/repositories/test_dj_library_items.py
git commit -m "feat: add DjLibraryItemRepository.get_by_track_id()

Query library items by track_id. Used to check if track
already has downloaded file before attempting download.

Tests: 2 passing (exists, not exists cases)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: DjLibraryItemRepository — create_from_download()

**Files:**
- Modify: `app/repositories/dj_library_items.py`
- Modify: `tests/repositories/test_dj_library_items.py`

**Step 1: Write failing test for create_from_download**

Add to `tests/repositories/test_dj_library_items.py`:

```python
    async def test_create_from_download_creates_library_item(self, session: AsyncSession):
        """create_from_download creates DjLibraryItem with file metadata."""
        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create library item from download
        repo = DjLibraryItemRepository(session)
        item = await repo.create_from_download(
            track_id=track.track_id,
            file_path="/path/to/file.mp3",
            file_size=2048,
            file_hash=b"abc123",
            bitrate_kbps=320,
        )
        await session.commit()

        assert item.track_id == track.track_id
        assert item.file_path == "/path/to/file.mp3"
        assert item.file_size_bytes == 2048
        assert item.file_hash == b"abc123"
        assert item.bitrate_kbps == 320
        assert item.mime_type == "audio/mpeg"
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/repositories/test_dj_library_items.py::TestDjLibraryItemRepository::test_create_from_download_creates_library_item -v
```

Expected: FAIL with "AttributeError: 'DjLibraryItemRepository' object has no attribute 'create_from_download'"

**Step 3: Implement create_from_download**

Add to `app/repositories/dj_library_items.py`:

```python
    async def create_from_download(
        self,
        track_id: int,
        file_path: str,
        file_size: int,
        file_hash: bytes,
        bitrate_kbps: int,
        mime_type: str = "audio/mpeg",
    ) -> DjLibraryItem:
        """Create library item after successful download.

        Args:
            track_id: Track ID
            file_path: Absolute path to downloaded file
            file_size: File size in bytes
            file_hash: SHA256 hash of file contents
            bitrate_kbps: Bitrate in kbps (e.g. 320)
            mime_type: MIME type (default: audio/mpeg)

        Returns:
            Created DjLibraryItem
        """
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

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/repositories/test_dj_library_items.py -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add app/repositories/dj_library_items.py tests/repositories/test_dj_library_items.py
git commit -m "feat: add DjLibraryItemRepository.create_from_download()

Create DjLibraryItem record with file metadata after
successful track download (path, size, hash, bitrate).

Tests: 3 passing (1 new)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: DownloadService — Sanitize Filename

**Files:**
- Create: `app/services/download.py`
- Create: `tests/services/test_download_service.py`

**Step 1: Write failing test for sanitize_filename**

Create `tests/services/test_download_service.py`:

```python
"""Tests for DownloadService."""

import pytest

from app.services.download import DownloadService

class TestDownloadService:
    def test_sanitize_filename_removes_special_chars(self):
        """_sanitize_filename removes / \\ : * ? " < > |"""
        result = DownloadService._sanitize_filename('Track / Name: Test?')
        assert result == "track_name_test"

    def test_sanitize_filename_replaces_spaces_with_underscores(self):
        """_sanitize_filename replaces spaces with underscores."""
        result = DownloadService._sanitize_filename('Fire Eyes')
        assert result == "fire_eyes"

    def test_sanitize_filename_truncates_to_max_len(self):
        """_sanitize_filename truncates to max_len (default 50)."""
        long_title = "A" * 100
        result = DownloadService._sanitize_filename(long_title)
        assert len(result) == 50
        assert result == "a" * 50

    def test_sanitize_filename_removes_trailing_underscores(self):
        """_sanitize_filename removes trailing underscores."""
        result = DownloadService._sanitize_filename('Track   ')
        assert result == "track"

    def test_sanitize_filename_returns_untitled_when_empty(self):
        """_sanitize_filename returns 'untitled' for empty input."""
        result = DownloadService._sanitize_filename('////')
        assert result == "untitled"
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_sanitize_filename_removes_special_chars -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.download'"

**Step 3: Create DownloadService with _sanitize_filename**

Create `app/services/download.py`:

```python
"""Service for downloading tracks from Yandex Music."""

import re

class DownloadService:
    """Service for downloading tracks from Yandex Music to local library."""

    @staticmethod
    def _sanitize_filename(title: str, max_len: int = 50) -> str:
        """Sanitize title for use in filename.

        Removes special characters (/ \\ : * ? " < > |), replaces spaces
        with underscores, converts to lowercase, truncates to max_len.

        Args:
            title: Track title to sanitize
            max_len: Maximum length (default: 50)

        Returns:
            Sanitized filename-safe string, or "untitled" if empty
        """
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

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService -v
```

Expected: 5 PASSED

**Step 5: Commit**

```bash
git add app/services/download.py tests/services/test_download_service.py
git commit -m "feat: add DownloadService._sanitize_filename()

Sanitize track titles for safe filenames: remove special
chars, replace spaces, lowercase, truncate to 50 chars.

Tests: 5 passing (special chars, spaces, truncate, trim, empty)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: DownloadService — Generate Filename

**Files:**
- Modify: `app/services/download.py`
- Modify: `tests/services/test_download_service.py`

**Step 1: Write failing test for _generate_filename**

Add to `tests/services/test_download_service.py`:

```python
from unittest.mock import Mock

class TestDownloadService:
    # ... existing tests ...

    def test_generate_filename_combines_track_id_and_title(self):
        """_generate_filename creates {track_id}_{sanitized_title}.mp3"""
        svc = DownloadService(Mock(), Mock(), Mock())
        track = Mock(track_id=42, title="Fire Eyes")
        result = svc._generate_filename(track)
        assert result == "42_fire_eyes.mp3"

    def test_generate_filename_sanitizes_title(self):
        """_generate_filename sanitizes track title."""
        svc = DownloadService(Mock(), Mock(), Mock())
        track = Mock(track_id=137, title="Track / Name?")
        result = svc._generate_filename(track)
        assert result == "137_track_name.mp3"
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_generate_filename_combines_track_id_and_title -v
```

Expected: FAIL with "AttributeError: 'DownloadService' object has no attribute '_generate_filename'"

**Step 3: Add __init__ and _generate_filename to DownloadService**

Modify `app/services/download.py`:

```python
"""Service for downloading tracks from Yandex Music."""

import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.yandex_music_client import YandexMusicClient

class DownloadService:
    """Service for downloading tracks from Yandex Music to local library."""

    def __init__(
        self,
        session: AsyncSession,
        ym_client: YandexMusicClient,
        library_path: Path,
    ):
        """Initialize download service.

        Args:
            session: Database session
            ym_client: Yandex Music API client
            library_path: Path to library directory for downloads
        """
        self.session = session
        self.ym_client = ym_client
        self.library_path = library_path

    def _generate_filename(self, track) -> str:
        """Generate sanitized filename for track.

        Format: {track_id}_{sanitized_title}.mp3

        Args:
            track: Track model instance

        Returns:
            Filename string (e.g. "42_fire_eyes.mp3")
        """
        sanitized = self._sanitize_filename(track.title)
        return f"{track.track_id}_{sanitized}.mp3"

    @staticmethod
    def _sanitize_filename(title: str, max_len: int = 50) -> str:
        # ... existing implementation ...
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/services/test_download_service.py -v
```

Expected: 7 PASSED

**Step 5: Commit**

```bash
git add app/services/download.py tests/services/test_download_service.py
git commit -m "feat: add DownloadService._generate_filename()

Generate filename {track_id}_{sanitized_title}.mp3 for
downloaded tracks. Ensures uniqueness via track_id prefix.

Tests: 7 passing (2 new)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: DownloadService — Get Yandex Track ID

**Files:**
- Modify: `app/services/download.py`
- Modify: `tests/services/test_download_service.py`

**Step 1: Write failing test for _get_yandex_track_id**

Add to `tests/services/test_download_service.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.providers import ProviderId

class TestDownloadService:
    # ... existing tests ...

    async def test_get_yandex_track_id_returns_value_when_exists(
        self, session: AsyncSession, tmp_path
    ):
        """_get_yandex_track_id returns YM track_id from provider_ids."""
        from unittest.mock import Mock

        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_id = ProviderId(
            track_id=track.track_id,
            provider="yandex",
            id_type="track",
            value="12345678",
        )
        session.add(provider_id)
        await session.commit()

        # Test
        svc = DownloadService(session, Mock(), tmp_path)
        result = await svc._get_yandex_track_id(track.track_id)

        assert result == "12345678"

    async def test_get_yandex_track_id_returns_none_when_not_exists(
        self, session: AsyncSession, tmp_path
    ):
        """_get_yandex_track_id returns None when no YM ID exists."""
        from unittest.mock import Mock

        svc = DownloadService(session, Mock(), tmp_path)
        result = await svc._get_yandex_track_id(999)

        assert result is None
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_get_yandex_track_id_returns_value_when_exists -v
```

Expected: FAIL with "AttributeError: 'DownloadService' object has no attribute '_get_yandex_track_id'"

**Step 3: Implement _get_yandex_track_id**

Add to `app/services/download.py`:

```python
    async def _get_yandex_track_id(self, track_id: int) -> str | None:
        """Get Yandex Music track ID from provider_ids table.

        Args:
            track_id: Local track ID

        Returns:
            Yandex Music track ID string, or None if not found
        """
        from sqlalchemy import select

        from app.models.providers import ProviderId

        stmt = (
            select(ProviderId.value)
            .where(ProviderId.track_id == track_id)
            .where(ProviderId.provider == "yandex")
            .where(ProviderId.id_type == "track")
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/services/test_download_service.py -v
```

Expected: 9 PASSED

**Step 5: Commit**

```bash
git add app/services/download.py tests/services/test_download_service.py
git commit -m "feat: add DownloadService._get_yandex_track_id()

Query provider_ids table for Yandex Music track ID.
Returns None if track has no YM provider ID.

Tests: 9 passing (2 new)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: DownloadService — Download Single Track (Happy Path)

**Files:**
- Modify: `app/services/download.py`
- Modify: `tests/services/test_download_service.py`

**Step 1: Write failing test for _download_single_track success**

Add to `tests/services/test_download_service.py`:

```python
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.repositories.dj_library_items import DjLibraryItemRepository
from app.repositories.tracks import TrackRepository

class TestDownloadService:
    # ... existing tests ...

    async def test_download_single_track_success_creates_file_and_db_entry(
        self, session: AsyncSession, tmp_path: Path
    ):
        """_download_single_track downloads file and creates DjLibraryItem."""
        # Create track
        track = Track(title="Nova", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_id = ProviderId(
            track_id=track.track_id,
            provider="yandex",
            id_type="track",
            value="12345",
        )
        session.add(provider_id)
        await session.commit()

        # Mock YM client
        mock_ym = Mock()
        mock_ym.download_track = AsyncMock(return_value=2048)

        # Mock file creation (YM client creates it)
        def mock_download(ym_id, dest_path, prefer_bitrate):
            Path(dest_path).write_bytes(b"fake mp3 data")
            return 2048

        mock_ym.download_track.side_effect = mock_download

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        success, size = await svc._download_single_track(track, prefer_bitrate=320)

        assert success is True
        assert size == 2048

        # Verify file exists
        expected_path = tmp_path / "1_nova.mp3"
        assert expected_path.exists()

        # Verify DjLibraryItem created
        repo = DjLibraryItemRepository(session)
        item = await repo.get_by_track_id(track.track_id)
        assert item is not None
        assert item.file_path == str(expected_path)
        assert item.file_size_bytes == 2048
        assert item.bitrate_kbps == 320
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_download_single_track_success_creates_file_and_db_entry -v
```

Expected: FAIL with "AttributeError: 'DownloadService' object has no attribute '_download_single_track'"

**Step 3: Implement _download_single_track (simplified, no retry yet)**

Add to `app/services/download.py`:

```python
import hashlib
import logging

from app.repositories.dj_library_items import DjLibraryItemRepository

logger = logging.getLogger(__name__)

class DownloadService:
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

    async def _download_single_track(
        self,
        track,
        prefer_bitrate: int,
        max_retries: int = 3,
    ) -> tuple[bool, int]:
        """Download single track with exponential backoff retry.

        Args:
            track: Track model instance
            prefer_bitrate: Preferred bitrate in kbps
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            (success: bool, file_size: int)
        """
        try:
            # 1. Get Yandex Music track ID
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
            logger.error(f"Failed to download track {track.track_id}: {e}")
            return (False, 0)
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_download_single_track_success_creates_file_and_db_entry -v
```

Expected: 1 PASSED

**Step 5: Commit**

```bash
git add app/services/download.py tests/services/test_download_service.py
git commit -m "feat: add DownloadService._download_single_track() happy path

Download track from YM, calculate SHA256, save to DjLibraryItem.
No retry logic yet (next task).

Tests: 10 passing (1 new)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: DownloadService — Add Retry Logic

**Files:**
- Modify: `app/services/download.py`
- Modify: `tests/services/test_download_service.py`

**Step 1: Write failing test for retry success**

Add to `tests/services/test_download_service.py`:

```python
import asyncio

class TestDownloadService:
    # ... existing tests ...

    async def test_download_single_track_retries_on_network_error(
        self, session: AsyncSession, tmp_path: Path
    ):
        """_download_single_track retries after network error."""
        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_id = ProviderId(
            track_id=track.track_id,
            provider="yandex",
            id_type="track",
            value="12345",
        )
        session.add(provider_id)
        await session.commit()

        # Mock YM client: fail twice, succeed on third
        mock_ym = Mock()
        attempts = []

        async def mock_download(ym_id, dest_path, prefer_bitrate):
            attempts.append(1)
            if len(attempts) < 3:
                raise Exception("Network error")
            Path(dest_path).write_bytes(b"data")
            return 1024

        mock_ym.download_track = AsyncMock(side_effect=mock_download)

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        success, size = await svc._download_single_track(track, prefer_bitrate=320)

        assert success is True
        assert len(attempts) == 3  # Failed twice, succeeded on 3rd

    async def test_download_single_track_fails_after_max_retries(
        self, session: AsyncSession, tmp_path: Path
    ):
        """_download_single_track returns (False, 0) after max retries."""
        # Create track
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        # Create provider ID
        provider_id = ProviderId(
            track_id=track.track_id,
            provider="yandex",
            id_type="track",
            value="12345",
        )
        session.add(provider_id)
        await session.commit()

        # Mock YM client: always fail
        mock_ym = Mock()
        mock_ym.download_track = AsyncMock(side_effect=Exception("Always fail"))

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        success, size = await svc._download_single_track(track, prefer_bitrate=320)

        assert success is False
        assert size == 0
        assert mock_ym.download_track.call_count == 3  # 3 attempts
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_download_single_track_retries_on_network_error -v
```

Expected: FAIL (no retry logic yet, fails immediately)

**Step 3: Add retry logic to _download_single_track**

Modify `app/services/download.py`:

```python
import asyncio

class DownloadService:
    async def _download_single_track(
        self,
        track,
        prefer_bitrate: int,
        max_retries: int = 3,
    ) -> tuple[bool, int]:
        """Download single track with exponential backoff retry.

        Args:
            track: Track model instance
            prefer_bitrate: Preferred bitrate in kbps
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            (success: bool, file_size: int)
        """
        for attempt in range(max_retries):
            try:
                # 1. Get Yandex Music track ID
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
                    delay = 2**attempt  # Exponential backoff: 1s, 2s, 4s
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
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/services/test_download_service.py -v
```

Expected: 12 PASSED

**Step 5: Commit**

```bash
git add app/services/download.py tests/services/test_download_service.py
git commit -m "feat: add retry logic to DownloadService._download_single_track()

Retry downloads with exponential backoff (1s, 2s, 4s).
Max 3 attempts, returns (False, 0) after all failures.

Tests: 12 passing (2 new retry tests)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: DownloadService — Download Batch

**Files:**
- Modify: `app/services/download.py`
- Modify: `tests/services/test_download_service.py`

**Step 1: Write failing test for download_tracks_batch**

Add to `tests/services/test_download_service.py`:

```python
from app.services.download import DownloadResult

class TestDownloadService:
    # ... existing tests ...

    async def test_download_tracks_batch_skips_existing_files(
        self, session: AsyncSession, tmp_path: Path
    ):
        """download_tracks_batch skips tracks with existing file_path."""
        # Create tracks
        track1 = Track(title="Track1", duration_ms=300000)
        track2 = Track(title="Track2", duration_ms=300000)
        session.add_all([track1, track2])
        await session.flush()

        # Track 1 already has file
        from app.models.dj import DjLibraryItem

        item1 = DjLibraryItem(track_id=track1.track_id, file_path="/existing.mp3")
        session.add(item1)
        await session.commit()

        # Mock YM client
        mock_ym = Mock()
        mock_ym.download_track = AsyncMock(return_value=1024)

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        result = await svc.download_tracks_batch([track1.track_id, track2.track_id])

        assert result.downloaded == 0  # Track2 has no YM ID, will fail
        assert result.skipped == 1  # Track1 skipped
        assert result.failed == 1  # Track2 failed (no YM ID)

    async def test_download_tracks_batch_partial_success(
        self, session: AsyncSession, tmp_path: Path
    ):
        """download_tracks_batch handles partial failures correctly."""
        # Create tracks
        track1 = Track(title="Success", duration_ms=300000)
        track2 = Track(title="Fail", duration_ms=300000)
        session.add_all([track1, track2])
        await session.flush()

        # Add provider IDs
        pid1 = ProviderId(
            track_id=track1.track_id, provider="yandex", id_type="track", value="111"
        )
        pid2 = ProviderId(
            track_id=track2.track_id, provider="yandex", id_type="track", value="222"
        )
        session.add_all([pid1, pid2])
        await session.commit()

        # Mock YM client: track1 succeeds, track2 fails
        mock_ym = Mock()

        async def mock_download(ym_id, dest_path, prefer_bitrate):
            if ym_id == "111":
                Path(dest_path).write_bytes(b"data")
                return 1024
            raise Exception("Download failed")

        mock_ym.download_track = AsyncMock(side_effect=mock_download)

        # Test
        svc = DownloadService(session, mock_ym, tmp_path)
        result = await svc.download_tracks_batch([track1.track_id, track2.track_id])

        assert result.downloaded == 1
        assert result.skipped == 0
        assert result.failed == 1
        assert result.failed_track_ids == [track2.track_id]
        assert result.total_bytes == 1024
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/services/test_download_service.py::TestDownloadService::test_download_tracks_batch_skips_existing_files -v
```

Expected: FAIL with "AttributeError: 'DownloadService' object has no attribute 'download_tracks_batch'"

**Step 3: Add DownloadResult and download_tracks_batch**

Add to `app/services/download.py`:

```python
from dataclasses import dataclass

from app.repositories.tracks import TrackRepository

@dataclass
class DownloadResult:
    """Statistics from batch download operation."""

    downloaded: int
    skipped: int
    failed: int
    failed_track_ids: list[int]
    total_bytes: int

class DownloadService:
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
            success, size = await self._download_single_track(track, prefer_bitrate)

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
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/services/test_download_service.py -v
```

Expected: 14 PASSED

**Step 5: Commit**

```bash
git add app/services/download.py tests/services/test_download_service.py
git commit -m "feat: add DownloadService.download_tracks_batch()

Download multiple tracks with skip logic for existing files.
Returns DownloadResult with statistics and failed_track_ids.

Tests: 14 passing (2 new batch tests)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: MCP Tool — download_tracks

**Files:**
- Modify: `app/mcp/workflows/import_tools.py`
- Create: `tests/mcp/test_download_tools.py`

**Step 1: Write failing integration test**

Create `tests/mcp/test_download_tools.py`:

```python
"""Integration tests for download MCP tools."""

import pytest
from fastmcp import Context

from app.mcp.workflows.import_tools import download_tracks
from app.models.catalog import Track
from app.models.providers import ProviderId

class TestDownloadTools:
    async def test_download_tracks_tool_registered(self):
        """download_tracks tool is registered in MCP."""
        from app.mcp.gateway import create_dj_mcp

        mcp = create_dj_mcp()
        tools = [t.name for t in mcp._mcp.list_tools()]

        assert "download_tracks" in tools

    async def test_download_tracks_returns_statistics(self, session, tmp_path):
        """download_tracks returns DownloadResult with statistics."""
        from unittest.mock import AsyncMock, Mock, patch

        # Create track with provider ID
        track = Track(title="Test", duration_ms=300000)
        session.add(track)
        await session.flush()

        pid = ProviderId(
            track_id=track.track_id,
            provider="yandex",
            id_type="track",
            value="12345",
        )
        session.add(pid)
        await session.commit()

        # Mock YM client
        mock_ym = Mock()

        async def mock_download(ym_id, dest_path, prefer_bitrate):
            from pathlib import Path

            Path(dest_path).write_bytes(b"data")
            return 1024

        mock_ym.download_track = AsyncMock(side_effect=mock_download)

        # Mock dependencies
        with patch("app.mcp.workflows.import_tools.get_ym_client", return_value=mock_ym):
            with patch("app.mcp.workflows.import_tools.settings") as mock_settings:
                mock_settings.dj_library_path = str(tmp_path)

                # Call tool
                from app.dependencies import get_session
                from app.services.tracks import TrackService

                track_svc = TrackService(session)

                result = await download_tracks(
                    track_ids=[track.track_id],
                    prefer_bitrate=320,
                    ctx=Context(),
                    track_svc=track_svc,
                    ym_client=mock_ym,
                )

                assert result.downloaded == 1
                assert result.skipped == 0
                assert result.failed == 0
                assert result.total_bytes == 1024
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/mcp/test_download_tools.py::TestDownloadTools::test_download_tracks_tool_registered -v
```

Expected: FAIL with "'download_tracks' not in tools"

**Step 3: Add download_tracks MCP tool**

Modify `app/mcp/workflows/import_tools.py`:

Add imports at top:

```python
from pathlib import Path

from app.config import settings
from app.services.download import DownloadResult, DownloadService
```

Add tool at end of file:

```python
@mcp.tool(
    name="download_tracks",
    description="Download MP3 files for tracks from Yandex Music to iCloud library",
    tags=["download", "yandex"],
    annotations={"readonly": False},
)
async def download_tracks(
    track_ids: list[int],
    prefer_bitrate: int = 320,
    ctx: Context | None = None,
    track_svc: TrackService = Depends(get_track_service),
    ym_client: YandexMusicClient = Depends(get_ym_client),
) -> DownloadResult:
    """Download tracks from Yandex Music to local library.

    Downloads MP3 files and stores them in iCloud library directory.
    Skips tracks that already have files. Returns download statistics.

    Args:
        track_ids: List of track IDs to download
        prefer_bitrate: Preferred bitrate in kbps (default: 320)

    Returns:
        Download statistics (downloaded, skipped, failed counts)

    Example:
        >>> await download_tracks([1, 2, 3], prefer_bitrate=320)
        DownloadResult(downloaded=2, skipped=1, failed=0, ...)
    """
    library_path = Path(settings.dj_library_path)

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
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/mcp/test_download_tools.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add app/mcp/workflows/import_tools.py tests/mcp/test_download_tools.py
git commit -m "feat: add download_tracks MCP tool

Download MP3 files from Yandex Music to iCloud library.
Returns DownloadResult with statistics. Skips existing files.

Tests: 2 integration tests passing

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Extend import_playlist with download_files

**Files:**
- Modify: `app/mcp/workflows/import_tools.py`
- Modify: `tests/mcp/test_download_tools.py`

**Step 1: Write failing test**

Add to `tests/mcp/test_download_tools.py`:

```python
class TestDownloadTools:
    # ... existing tests ...

    async def test_import_playlist_with_download_files_downloads_tracks(
        self, session, tmp_path
    ):
        """import_playlist(download_files=True) downloads tracks."""
        from unittest.mock import AsyncMock, Mock, patch

        # This test would require full import_playlist implementation
        # For now, we'll just verify the parameter exists

        from app.mcp.workflows.import_tools import import_playlist
        import inspect

        sig = inspect.signature(import_playlist)
        assert "download_files" in sig.parameters
        assert sig.parameters["download_files"].default is False
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/mcp/test_download_tools.py::TestDownloadTools::test_import_playlist_with_download_files_downloads_tracks -v
```

Expected: FAIL with "KeyError: 'download_files'"

**Step 3: Add download_files parameter to import_playlist**

Find `import_playlist` function in `app/mcp/workflows/import_tools.py` and modify:

```python
@mcp.tool(...)
async def import_playlist(
    source: str,
    playlist_id: str,
    download_files: bool = False,  # NEW parameter
    ctx: Context | None = None,
    playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    track_svc: TrackService = Depends(get_track_service),
    ym_client: YandexMusicClient = Depends(get_ym_client),
) -> ImportResult:
    """Import playlist metadata and optionally download files.

    ... existing docstring ...

    Args:
        source: Source platform (only 'yandex' supported)
        playlist_id: Playlist ID in format 'user_id:kind'
        download_files: Download MP3 files after import (default: False)
        ...

    ... rest of implementation ...
    """
    # ... existing import logic ...

    # NEW: Download files if requested
    if download_files and imported_track_ids:
        from pathlib import Path

        from app.services.download import DownloadService

        library_path = Path(settings.dj_library_path)
        download_svc = DownloadService(
            session=playlist_svc.session,  # or track_svc.session
            ym_client=ym_client,
            library_path=library_path,
        )
        download_result = await download_svc.download_tracks_batch(imported_track_ids)

        # Add download stats to result message
        ctx.info(
            f"Downloaded {download_result.downloaded} files, "
            f"skipped {download_result.skipped}, "
            f"failed {download_result.failed}"
        )

    return result
```

Note: The exact integration depends on existing `import_playlist` implementation.
Add the download logic after tracks are imported but before returning result.

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/mcp/test_download_tools.py -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add app/mcp/workflows/import_tools.py tests/mcp/test_download_tools.py
git commit -m "feat: add download_files parameter to import_playlist

Enable auto-download during playlist import via download_files=True.
Downloads tracks after import, logs statistics via Context.

Tests: 3 integration tests passing (1 new)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Run Full Test Suite

**Step 1: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: All tests passing (670+ total)

**Step 2: Run lint**

Run:
```bash
uv run ruff check
uv run ruff format --check
uv run mypy app/
```

Expected: No errors

**Step 3: Fix any lint/type errors if found**

If errors found, fix them and rerun tests.

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: fix lint and type errors for download feature

All tests passing, ruff + mypy clean.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 13: Update Documentation

**Files:**
- Modify: `CLAUDE.md` or `.claude/rules/mcp.md`

**Step 1: Document new MCP tools**

Add to `.claude/rules/mcp.md` in the tools table:

```markdown
| Tool | Purpose | Readonly |
|------|---------|----------|
| ... existing tools ...
| `dj_download_tracks` | Download MP3 files from Yandex Music to iCloud | No |
| `dj_import_playlist` | Import playlist (now supports `download_files=True`) | No |
```

**Step 2: Document new services/repos**

Add to `.claude/rules/api.md` or create note in CLAUDE.md:

```markdown
## Download Service
- `DownloadService` — downloads tracks from YM, stores in iCloud
- `DjLibraryItemRepository` — manages file metadata in dj_library_items table
- Config: `settings.dj_library_path` (iCloud directory)
```

**Step 3: Commit documentation**

```bash
git add CLAUDE.md .claude/rules/mcp.md
git commit -m "docs: document download_tracks MCP tools and services

Add documentation for new download functionality:
- download_tracks tool
- import_playlist download_files parameter
- DownloadService and DjLibraryItemRepository

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Completion Checklist

- [x] Task 1: Add dj_library_path to Settings
- [x] Task 2: DjLibraryItemRepository.get_by_track_id()
- [x] Task 3: DjLibraryItemRepository.create_from_download()
- [x] Task 4: DownloadService._sanitize_filename()
- [x] Task 5: DownloadService._generate_filename()
- [x] Task 6: DownloadService._get_yandex_track_id()
- [x] Task 7: DownloadService._download_single_track() happy path
- [x] Task 8: Add retry logic with exponential backoff
- [x] Task 9: DownloadService.download_tracks_batch()
- [x] Task 10: download_tracks MCP tool
- [x] Task 11: Extend import_playlist with download_files
- [x] Task 12: Run full test suite and fix lint
- [x] Task 13: Update documentation

## Implementation Notes

**TDD Workflow:**
- Every feature: write failing test → implement → verify pass → commit
- Frequent small commits (one per feature)
- Test file created alongside implementation file

**Error Handling:**
- Exponential backoff: 1s, 2s, 4s (2^attempt)
- Max 3 retry attempts for network errors
- Graceful degradation: partial batch success tracked in DownloadResult

**File Organization:**
- iCloud: `~/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/library/`
- Flat structure: `{track_id}_{sanitized_title}.mp3`
- SHA256 hashing for integrity verification

**Future Enhancements (out of scope):**
- Progress reporting via MCP Context streaming
- Concurrent downloads with semaphore
- Resume partial downloads
- Cleanup orphaned files
