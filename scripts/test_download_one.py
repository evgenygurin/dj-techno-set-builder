#!/usr/bin/env python3
"""Test downloading a single track."""

import asyncio
import sys
from pathlib import Path

from app.config import settings
from app.database import close_db, init_db, session_factory
from app.services.download import DownloadService
from app.clients.yandex_music import YandexMusicClient


async def main() -> None:
    """Test download for one track."""
    track_id = 146616736  # Brandon - Peace Of Mind

    print(f"Testing download for track_id={track_id}")
    print(f"YM Token: {settings.yandex_music_token[:20]}...")
    print(f"Library path (raw): {settings.dj_library_path}")

    library_path = Path(settings.dj_library_path).expanduser()
    print(f"Library path (expanded): {library_path}")
    print(f"Library exists: {library_path.exists()}")

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

        try:
            result = await download_svc.download_tracks_batch(
                track_ids=[track_id],
                prefer_bitrate=320,
            )
            print(f"\n✓ Download result: {result}")

            if result.failed > 0:
                print(f"✗ Failed to download track {track_id}")
                sys.exit(1)
            else:
                print(f"✓ Success! Check {library_path}")

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
