import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.metadata_beatport import BeatportMetadata
from app.models.metadata_soundcloud import SoundCloudMetadata


async def test_create_soundcloud_metadata(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    sc = SoundCloudMetadata(
        track_id=track.track_id,
        soundcloud_track_id="123456789",
        bpm=128,
        genre="Techno",
    )
    session.add(sc)
    await session.flush()
    assert sc.track_id == track.track_id


async def test_soundcloud_track_id_unique(session: AsyncSession) -> None:
    t1 = Track(title="T1", duration_ms=300000)
    t2 = Track(title="T2", duration_ms=300000)
    session.add_all([t1, t2])
    await session.flush()
    session.add(SoundCloudMetadata(track_id=t1.track_id, soundcloud_track_id="same"))
    session.add(SoundCloudMetadata(track_id=t2.track_id, soundcloud_track_id="same"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_beatport_metadata(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    bp = BeatportMetadata(
        track_id=track.track_id,
        beatport_track_id="98765",
        bpm=132.0,
        key_code=5,
        genre_name="Techno",
    )
    session.add(bp)
    await session.flush()
    assert bp.track_id == track.track_id


async def test_beatport_key_code_constraint(session: AsyncSession) -> None:
    """key_code must be between 0 and 23."""
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    bp = BeatportMetadata(
        track_id=track.track_id,
        beatport_track_id="111",
        key_code=99,
    )
    session.add(bp)
    with pytest.raises(IntegrityError):
        await session.flush()
