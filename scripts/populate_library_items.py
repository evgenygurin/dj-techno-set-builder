#!/usr/bin/env python3
"""Populate dj_library_items from downloaded MP3 files."""

import asyncio
import hashlib
from pathlib import Path

from app.core.config import settings
from app.infrastructure.database import close_db, init_db, session_factory
from app.infrastructure.repositories.dj_library_items import DjLibraryItemRepository

# All track IDs from import
TRACK_IDS = [
    146616736,
    146616737,
    146616738,
    146616739,
    146616740,
    146616741,
    146616742,
    146616743,
    146616744,
    146616745,
    146616746,
    146616747,
    146616748,
    146616749,
    146616750,
    146616751,
    146616752,
    146616753,
    146616754,
    146616755,
    146616756,
    146616757,
    146616758,
    146616759,
    146616760,
    146616761,
    146616762,
    146616763,
    146616764,
    146616765,
]


async def main() -> None:
    """Populate library items from files."""
    library_path = Path(settings.dj_library_path).expanduser()

    print(f"Scanning: {library_path}\n")

    await init_db()

    async with session_factory() as session:
        library_repo = DjLibraryItemRepository(session)

        created = 0
        skipped = 0

        for track_id in TRACK_IDS:
            # Find file by track_id prefix
            files = list(library_path.glob(f"{track_id}_*.mp3"))

            if not files:
                print(f"  ✗ No file for track_id={track_id}")
                skipped += 1
                continue

            file_path = files[0]
            file_size = file_path.stat().st_size
            file_hash = hashlib.sha256(file_path.read_bytes()).digest()

            # Create library item
            await library_repo.create_from_download(
                track_id=track_id,
                file_path=str(file_path),
                file_size=file_size,
                file_hash=file_hash,
                bitrate_kbps=320,
            )

            print(f"  ✓ {file_path.name} ({file_size / 1024 / 1024:.1f} MB)")
            created += 1

        await session.commit()

        print(f"\n{'=' * 60}")
        print(f"✓ Created: {created}")
        print(f"○ Skipped: {skipped}")
        print(f"{'=' * 60}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
