#!/usr/bin/env python3
"""Download all 30 tracks from Shizzz playlist."""

import asyncio
from pathlib import Path

from app.config import settings
from app.database import close_db, init_db, session_factory
from app.services.download import DownloadService
from app.services.yandex_music_client import YandexMusicClient

# All track IDs from import
TRACK_IDS = [
    146616736, 146616737, 146616738, 146616739, 146616740,
    146616741, 146616742, 146616743, 146616744, 146616745,
    146616746, 146616747, 146616748, 146616749, 146616750,
    146616751, 146616752, 146616753, 146616754, 146616755,
    146616756, 146616757, 146616758, 146616759, 146616760,
    146616761, 146616762, 146616763, 146616764, 146616765,
]


async def main() -> None:
    """Download all tracks."""
    print(f"Downloading {len(TRACK_IDS)} tracks from Shizzz playlist")

    library_path = Path(settings.dj_library_path).expanduser()
    print(f"Library: {library_path}\n")

    await init_db()

    async with session_factory() as session:
        ym_client = YandexMusicClient(
            token=settings.yandex_music_token,
            user_id=settings.yandex_music_user_id,
        )

        download_svc = DownloadService(
            session=session,
            ym_client=ym_client,
            library_path=library_path,
        )

        result = await download_svc.download_tracks_batch(
            track_ids=TRACK_IDS,
            prefer_bitrate=320,
        )

        print(f"\n{'='*60}")
        print(f"✓ Downloaded: {result.downloaded}")
        print(f"○ Skipped:    {result.skipped}")
        print(f"✗ Failed:     {result.failed}")
        print(f"📦 Total:      {result.total_bytes / 1024 / 1024:.1f} MB")
        print(f"{'='*60}")

        if result.failed > 0:
            print(f"\nFailed track IDs: {result.failed_track_ids[:5]}...")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
