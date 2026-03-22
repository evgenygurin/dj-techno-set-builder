#!/usr/bin/env python3
"""Import Shizzz playlist - simplified version with embedded data."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import close_db, init_db, session_factory
from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider

# Track IDs and metadata from Yandex Music playlist "Shizzz"
TRACKS = [
    (146616735, "Brandon - Peace Of Mind (Keep Talking)", 172500),
    (142830757, "Groove Delight - ELAS", 211870),
    (144949931, "Breaking Beattz - Empurra", 169840),
    (130394268, "gleb filipchenkow - Muito", 333750),
    (140950962, "Cave Studio - Look At Me", 188300),
    (131895504, "PELYUH - Bad", 170990),
    (71298728, "Cloverdale - Bakerstreet", 166000),
    (91254259, "Nasser Baker - Preacher Preach", 223980),
    (117311940, "Valmaiin - Diabolica", 436370),
    (102414832, "Ernie Black - Hit The Club", 154340),
    (146801510, "Bonafique - WHAT!", 199350),
    (134234664, "PRYCEWELL - LOCA", 201610),
    (135373461, "Jus Deelax - Don't Touch That", 166290),
    (144289210, "Dan Korshunov - Сколько их было", 104000),
    (146315911, "slxmy - VETTEL", 223380),
    (143707302, "Moreart - Tom Ford", 132970),
    (129782210, "qwerty_lxd - discoteque", 101650),
    (137242384, "ICEGERGERT - Plan G", 132000),
    (146687313, "PEREKUPCHINO - WINNER", 106660),
    (137843513, "Frida Darko - Goldkette", 235120),
    (138786753, "AG Swifty - On The Run", 268340),
    (145180963, "BENZCOUNTGANG - Op", 136720),
    (139747130, "LNRT - Players Only", 145450),
    (141538070, "Mk - Rhyme Dust", 181380),
    (144305882, "Tim Taste - Just Now", 362170),
    (138910021, "FOVOS - Freak in me", 157930),
    (140481435, "Victor Ruiz - All Night Long", 229660),
    (128377081, "Arturo (RU) - Autofocus", 403200),
    (132758441, "Roddy Lima - 2015", 167420),
    (85616789, "Zafer Atabey - Vertigo", 244390),
]


async def get_or_create_provider(session: AsyncSession) -> int:
    """Get or create Yandex Music provider."""
    stmt = select(Provider).where(Provider.provider_code == "ym")
    result = await session.execute(stmt)
    provider = result.scalar_one_or_none()

    if provider:
        return provider.provider_id

    # Get max provider_id and increment
    max_id_stmt = select(Provider.provider_id).order_by(Provider.provider_id.desc()).limit(1)
    max_result = await session.execute(max_id_stmt)
    max_id = max_result.scalar_one_or_none() or 0

    new_provider = Provider(
        provider_id=max_id + 1,
        provider_code="ym",
        name="Yandex Music",
    )
    session.add(new_provider)
    await session.flush()
    print(f"Created Yandex Music provider (id={new_provider.provider_id})")
    return new_provider.provider_id


async def import_track(
    session: AsyncSession,
    provider_id: int,
    ym_track_id: int,
    title: str,
    duration_ms: int,
) -> int | None:
    """Import single track and create provider link."""
    # Check if track already exists with this YM ID
    stmt = (
        select(ProviderTrackId.track_id)
        .where(ProviderTrackId.provider_id == provider_id)
        .where(ProviderTrackId.provider_track_id == str(ym_track_id))
    )
    result = await session.execute(stmt)
    existing_id = result.scalar_one_or_none()

    if existing_id:
        print(f"  Track '{title}' already exists (track_id={existing_id})")
        return existing_id

    try:
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
            provider_track_id=str(ym_track_id),
            provider_country="RU",
        )
        session.add(provider_link)
        await session.flush()

        print(f"  ✓ Imported '{title}' (track_id={track.track_id}, ym_id={ym_track_id})")
        return track.track_id

    except Exception as e:
        print(f"  ✗ Failed to import '{title}': {e}")
        return None


async def main() -> None:
    """Import Shizzz playlist."""
    print(f"Importing {len(TRACKS)} tracks from Shizzz playlist\n")

    await init_db()

    async with session_factory() as session:
        provider_id = await get_or_create_provider(session)
        print(f"Using provider_id={provider_id}\n")

        imported_ids = []
        failed_count = 0

        for idx, (ym_id, title, duration) in enumerate(TRACKS, 1):
            print(f"[{idx}/{len(TRACKS)}] {title}")

            track_id = await import_track(session, provider_id, ym_id, title, duration)

            if track_id:
                imported_ids.append(track_id)
            else:
                failed_count += 1

        await session.commit()

        print(f"\n✓ Successfully imported {len(imported_ids)} tracks!")
        print(f"✗ Failed: {failed_count}")

        if imported_ids:
            print(
                f"\nLocal track IDs: {imported_ids[:5]}..."
                if len(imported_ids) > 5
                else f"\nLocal track IDs: {imported_ids}"
            )
            print("\nYou can now download MP3 files using:")
            print(f"  dj_download_tracks with track_ids={imported_ids}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
