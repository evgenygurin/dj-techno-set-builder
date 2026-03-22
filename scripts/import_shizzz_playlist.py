#!/usr/bin/env python3
"""Import Shizzz playlist from Yandex Music to local database."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import close_db, init_db, session_factory
from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider


async def get_or_create_provider(session: AsyncSession, code: str, name: str) -> int:
    """Get existing provider or create new one."""
    stmt = select(Provider).where(Provider.provider_code == code)
    result = await session.execute(stmt)
    provider = result.scalar_one_or_none()

    if provider:
        return provider.provider_id

    # Get max provider_id and increment
    max_id_stmt = select(Provider.provider_id).order_by(Provider.provider_id.desc())
    max_result = await session.execute(max_id_stmt)
    max_id = max_result.scalar_one_or_none() or 0

    new_provider = Provider(
        provider_id=max_id + 1,
        provider_code=code,
        name=name,
    )
    session.add(new_provider)
    await session.flush()
    return new_provider.provider_id


async def import_track_from_ym(
    session: AsyncSession,
    provider_id: int,
    ym_track_id: str,
    title: str,
    duration_ms: int,
) -> int:
    """Import single track and create provider link."""
    # Check if track already exists with this YM ID
    stmt = (
        select(ProviderTrackId.track_id)
        .where(ProviderTrackId.provider_id == provider_id)
        .where(ProviderTrackId.provider_track_id == ym_track_id)
    )
    result = await session.execute(stmt)
    existing_id = result.scalar_one_or_none()

    if existing_id:
        print(f"  Track '{title}' already exists (track_id={existing_id})")
        return existing_id

    # Create new track
    track = Track(
        title=title,
        title_sort=title.lower(),
        duration_ms=duration_ms,
        status=1,  # Active
    )
    session.add(track)
    await session.flush()

    # Create provider link
    provider_link = ProviderTrackId(
        track_id=track.track_id,
        provider_id=provider_id,
        provider_track_id=ym_track_id,
        provider_country="RU",
    )
    session.add(provider_link)
    await session.flush()

    print(f"  ✓ Imported '{title}' (track_id={track.track_id}, ym_id={ym_track_id})")
    return track.track_id


async def main() -> None:
    """Import Shizzz playlist."""
    # Read playlist data from JSON file
    script_dir = Path(__file__).parent
    data_file = script_dir / "shizzz_playlist_data.json"

    if not data_file.exists():
        print(f"Error: Playlist data file not found: {data_file}")
        return

    print(f"Reading playlist data from: {data_file.name}")

    with open(data_file) as f:
        data = json.load(f)

    tracks = data["result"]["tracks"]
    print(f"Found {len(tracks)} tracks in playlist 'Shizzz'\n")

    # Initialize database
    await init_db()

    async with session_factory() as session:
        # Get or create Yandex Music provider
        provider_id = await get_or_create_provider(session, "yandex", "Yandex Music")
        print(f"Using provider_id={provider_id} for Yandex Music\n")

        imported_ids = []

        # Import each track
        for idx, track_data in enumerate(tracks, 1):
            track_info = track_data["track"]
            ym_id = str(track_info["id"])
            title = track_info["title"]
            duration_ms = track_info["durationMs"]

            # Add artist name to title for better identification
            if track_info.get("artists"):
                artist_name = track_info["artists"][0]["name"]
                display_title = f"{artist_name} - {title}"
            else:
                display_title = title

            print(f"[{idx}/{len(tracks)}] {display_title}")

            track_id = await import_track_from_ym(
                session,
                provider_id,
                ym_id,
                display_title,
                duration_ms,
            )
            imported_ids.append(track_id)

        await session.commit()
        print(f"\n✓ Successfully imported {len(imported_ids)} tracks!")
        print(
            f"Track IDs: {imported_ids[:5]}..."
            if len(imported_ids) > 5
            else f"Track IDs: {imported_ids}"
        )

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
