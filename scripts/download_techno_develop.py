"""Download missing tracks from 'Techno develop' YM playlist.

Creates Track records, ProviderTrackId mappings, downloads MP3s,
and creates DjLibraryItem entries.
"""

import asyncio
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

from sqlalchemy import select, text

# fmt: off
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# fmt: on

from app.core.config import settings
from app.infrastructure.database import (
    close_db,
    init_db,
    session_factory,
)
from app.core.models.catalog import Track
from app.core.models.dj import DjLibraryItem
from app.core.models.ingestion import ProviderTrackId
from app.services.yandex_music_client import YandexMusicClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

LIBRARY_PATH = Path(settings.dj_library_path).expanduser()
YM_PLAYLIST_FILE = (
    "/Users/laptop/.claude/projects/-Users-laptop-dev-dj-techno-set-builder/"
    "d6825a6c-eb75-4149-a47d-aa30e22ffbd3/tool-results/"
    "mcp-dj-techno-ym_get_playlist_by_id-1771454073728.txt"
)


def sanitize(title: str, max_len: int = 50) -> str:
    safe = re.sub(r'[/\\:*?"<>|]', "", title)
    safe = safe.replace(" ", "_")
    safe = re.sub(r"_+", "_", safe).lower()[:max_len].rstrip("_")
    return safe or "untitled"


async def main() -> None:
    await init_db()
    LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    # Load playlist data
    with open(YM_PLAYLIST_FILE) as f:
        data = json.load(f)
    ym_tracks = data["result"]["tracks"]
    log.info("YM playlist: %d tracks", len(ym_tracks))

    ym_client = YandexMusicClient(token=settings.yandex_music_token)

    ok = 0
    skip = 0
    fail = 0

    async with session_factory() as session:
        # Get yandex provider_id
        prov_row = await session.execute(
            text("SELECT provider_id FROM providers WHERE provider_code = 'ym'")
        )
        provider_id = prov_row.scalar()
        if not provider_id:
            log.error("Provider 'yandex' not found!")
            return

        for i, entry in enumerate(ym_tracks):
            track_data = entry.get("track", entry)
            ym_id = str(track_data.get("id", track_data.get("trackId")))
            title = track_data.get("title", "untitled")
            dur_ms = track_data.get("durationMs", 0)
            artists = ", ".join(a.get("name", "?") for a in track_data.get("artists", []))

            # Check if already in DB
            existing = await session.execute(
                select(ProviderTrackId.track_id).where(
                    ProviderTrackId.provider_id == provider_id,
                    ProviderTrackId.provider_track_id == ym_id,
                )
            )
            existing_tid = existing.scalar_one_or_none()
            if existing_tid:
                # Check if file exists
                lib_row = await session.execute(
                    select(DjLibraryItem).where(DjLibraryItem.track_id == existing_tid)
                )
                if lib_row.scalar_one_or_none():
                    skip += 1
                    continue
                # Track in DB but no file — download
                track = await session.get(Track, existing_tid)
                if not track:
                    skip += 1
                    continue
            else:
                # Create track record
                track = Track(
                    title=title,
                    title_sort=title.lower(),
                    duration_ms=dur_ms,
                    status=0,  # 0=active, 1=archived
                )
                session.add(track)
                await session.flush()

                # Create provider mapping
                ptid = ProviderTrackId(
                    track_id=track.track_id,
                    provider_id=provider_id,
                    provider_track_id=ym_id,
                )
                session.add(ptid)
                await session.flush()

            # Download MP3
            filename = f"{track.track_id}_{sanitize(title)}.mp3"
            dest = LIBRARY_PATH / filename

            if dest.exists():
                # File exists, just create library item
                file_size = dest.stat().st_size
                file_hash = hashlib.sha256(dest.read_bytes()).digest()
            else:
                try:
                    file_size = await ym_client.download_track(
                        ym_id, str(dest), prefer_bitrate=320
                    )
                    file_hash = hashlib.sha256(dest.read_bytes()).digest()
                except Exception as e:
                    log.error("[%d/%d] FAIL %s (%s): %s", i + 1, len(ym_tracks), title, ym_id, e)
                    fail += 1
                    await asyncio.sleep(2)
                    continue

            # Create library item
            lib_item = DjLibraryItem(
                track_id=track.track_id,
                file_path=str(dest),
                file_size_bytes=file_size,
                file_hash=file_hash,
                bitrate_kbps=320,
                mime_type="audio/mpeg",
            )
            session.add(lib_item)
            await session.flush()
            ok += 1

            if (i + 1) % 10 == 0:
                await session.commit()
                log.info(
                    "[%d/%d] ok=%d skip=%d fail=%d | %s — %s",
                    i + 1,
                    len(ym_tracks),
                    ok,
                    skip,
                    fail,
                    artists,
                    title,
                )

            await asyncio.sleep(1)  # rate limit

        await session.commit()

    log.info("DONE: %d downloaded, %d skipped, %d failed", ok, skip, fail)
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
