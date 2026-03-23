#!/usr/bin/env python3
"""Export Shizzz playlist as M3U8 for Rekordbox."""

import asyncio
from pathlib import Path

from app.core.config import settings
from app.infrastructure.database import close_db, init_db, session_factory
from app.infrastructure.repositories.dj.library_items import DjLibraryItemRepository
from app.infrastructure.repositories.catalog.tracks import TrackRepository

# All track IDs from import (in playlist order)
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
    """Export playlist as M3U8."""
    library_path = Path(settings.dj_library_path).expanduser()
    m3u_path = library_path / "Shizzz.m3u8"

    print(f"Exporting playlist to: {m3u_path}")

    await init_db()

    async with session_factory() as session:
        track_repo = TrackRepository(session)
        library_repo = DjLibraryItemRepository(session)

        # Build M3U8 content
        lines = ["#EXTM3U\n"]

        for idx, track_id in enumerate(TRACK_IDS, 1):
            track = await track_repo.get_by_id(track_id)
            if not track:
                print(f"  ✗ Track {track_id} not found")
                continue

            library_item = await library_repo.get_by_track_id(track_id)
            if not library_item or not library_item.file_path:
                print(f"  ✗ No file for {track.title}")
                continue

            # Extract filename from full path
            filename = Path(library_item.file_path).name

            # EXTINF: duration_seconds, artist - title
            duration_sec = track.duration_ms // 1000
            lines.append(f"#EXTINF:{duration_sec},{track.title}\n")
            lines.append(f"{filename}\n")

            print(f"  [{idx}/{len(TRACK_IDS)}] {track.title}")

        # Write M3U8 file
        m3u_path.write_text("".join(lines), encoding="utf-8")

        print(f"\n✓ Playlist exported: {m3u_path.name}")
        print(f"✓ Tracks: {len(TRACK_IDS)}")
        print("\nImport in Rekordbox:")
        print(f"  File → Import → Playlist → {m3u_path}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
