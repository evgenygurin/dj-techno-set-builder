#!/usr/bin/env python3
"""Download all tracks from 'Techno Develop Recs' playlist (playlist_id=2).

Reads track_ids from the DB, downloads MP3s to a dedicated directory.
Safe to resume — skips already downloaded tracks (checks dj_library_items + file on disk).
Uses WAL mode and per-track sessions to avoid DB lock issues.
"""

import asyncio
import hashlib
import logging
import re
import time
from pathlib import Path

from sqlalchemy import select, text

from app.config import settings
from app.database import close_db, init_db, session_factory
from app.models.catalog import Track
from app.models.dj import DjPlaylistItem
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.repositories.dj_library_items import DjLibraryItemRepository
from app.clients.yandex_music import create_ym_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PLAYLIST_ID = 2
DEST_DIR = Path(settings.dj_library_path).expanduser().parent / "techno-develop-recs"
MAX_RETRIES = 3


async def enable_wal_mode() -> None:
    """Enable WAL journal mode for concurrent read/write access."""
    async with session_factory() as session:
        await session.execute(text("PRAGMA journal_mode=WAL"))
        await session.execute(text("PRAGMA busy_timeout=30000"))
        await session.commit()
    logger.info("SQLite WAL mode enabled, busy_timeout=30s")


async def get_playlist_track_ids(playlist_id: int) -> list[int]:
    """Fetch all track IDs for a playlist from DB."""
    async with session_factory() as session:
        stmt = (
            select(DjPlaylistItem.track_id)
            .where(DjPlaylistItem.playlist_id == playlist_id)
            .order_by(DjPlaylistItem.sort_index)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _sanitize_filename(title: str, max_len: int = 50) -> str:
    safe = re.sub(r'[/\\:*?"<>|]', "", title)
    safe = safe.replace(" ", "_")
    safe = re.sub(r"_+", "_", safe)
    safe = safe.lower()[:max_len].rstrip("_")
    return safe or "untitled"


def _file_exists_on_disk(track_id: int) -> bool:
    """Check if file already exists in DEST_DIR."""
    return bool(list(DEST_DIR.glob(f"{track_id}_*.mp3")))


async def download_single_track(
    track_id: int,
    ym_client: YandexMusicClient,
) -> tuple[bool, int]:
    """Download one track with its own session. Returns (success, bytes)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session_factory() as session:
                # Check library_items (already recorded)
                lib_repo = DjLibraryItemRepository(session)
                existing = await lib_repo.get_by_track_id(track_id)
                if existing and existing.file_path:
                    return (True, 0)  # skip

                # Get track metadata
                track = (
                    await session.execute(select(Track).where(Track.track_id == track_id))
                ).scalar_one_or_none()
                if not track:
                    logger.warning("Track %d not in DB", track_id)
                    return (False, 0)

                # Get YM track ID
                stmt = (
                    select(ProviderTrackId.provider_track_id)
                    .join(Provider)
                    .where(ProviderTrackId.track_id == track_id)
                    .where(Provider.provider_code == "ym")
                )
                ym_id = (await session.execute(stmt)).scalar_one_or_none()
                if not ym_id:
                    logger.warning("Track %d: no YM mapping", track_id)
                    return (False, 0)

                # Generate filename & download
                filename = f"{track.track_id}_{_sanitize_filename(track.title)}.mp3"
                dest_path = DEST_DIR / filename

                if dest_path.exists():
                    # File on disk but not in DB — register it
                    file_hash = hashlib.sha256(dest_path.read_bytes()).digest()
                    size = dest_path.stat().st_size
                else:
                    size = await ym_client.download_track(
                        ym_id, str(dest_path), prefer_bitrate=320
                    )
                    file_hash = hashlib.sha256(dest_path.read_bytes()).digest()

                # Save to dj_library_items
                await lib_repo.create_from_download(
                    track_id=track_id,
                    file_path=str(dest_path),
                    file_size=size,
                    file_hash=file_hash,
                    bitrate_kbps=320,
                )
                await session.commit()
                logger.info("Downloaded track %d (%d bytes)", track_id, size)
                return (True, size)

        except Exception as e:
            err_msg = str(e)
            if "database is locked" in err_msg and attempt < MAX_RETRIES:
                delay = 2**attempt
                logger.info(
                    "Track %d: DB locked, retry %d/%d in %ds",
                    track_id,
                    attempt,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Track %d failed (attempt %d): %s", track_id, attempt, e)
                return (False, 0)

    return (False, 0)


async def main() -> None:
    """Download all playlist tracks one-by-one with resilient sessions."""
    await init_db()
    await enable_wal_mode()

    track_ids = await get_playlist_track_ids(PLAYLIST_ID)
    logger.info("Playlist %d: %d tracks", PLAYLIST_ID, len(track_ids))

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Destination: %s", DEST_DIR)

    # Skip already downloaded
    already_on_disk = sum(1 for tid in track_ids if _file_exists_on_disk(tid))
    logger.info("Already on disk: %d / %d", already_on_disk, len(track_ids))

    ym_client = YandexMusicClient(
        token=settings.yandex_music_token,
        user_id=settings.yandex_music_user_id,
    )

    total_dl = total_skip = total_fail = total_bytes = 0
    start = time.monotonic()

    try:
        for i, track_id in enumerate(track_ids, 1):
            if _file_exists_on_disk(track_id):
                total_skip += 1
                # Still ensure it's in DB (register if missing)
                await download_single_track(track_id, ym_client)
                continue

            success, nbytes = await download_single_track(track_id, ym_client)
            if success:
                total_dl += 1
                total_bytes += nbytes
            else:
                total_fail += 1

            # Progress every 25 tracks
            if i % 25 == 0:
                elapsed = time.monotonic() - start
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(track_ids) - i) / rate if rate > 0 else 0
                logger.info(
                    "Progress: %d/%d (%.0f%%) | +%d dl, %d skip, %d fail | ETA: %.0f min",
                    i,
                    len(track_ids),
                    100 * i / len(track_ids),
                    total_dl,
                    total_skip,
                    total_fail,
                    eta / 60,
                )
    finally:
        await ym_client.close()

    elapsed = time.monotonic() - start
    print(f"\n{'=' * 60}")
    print(f"Downloaded:  {total_dl}")
    print(f"Skipped:     {total_skip}")
    print(f"Failed:      {total_fail}")
    print(f"Total size:  {total_bytes / 1024 / 1024:.1f} MB")
    print(f"Time:        {elapsed / 60:.1f} min")
    print(f"Directory:   {DEST_DIR}")
    print(f"{'=' * 60}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
