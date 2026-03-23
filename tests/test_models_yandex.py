import pytest
from sqlalchemy.exc import IntegrityError

from app.core.models import Track, YandexMetadata


async def test_create_yandex_metadata(session):
    """YandexMetadata stores Yandex-specific track data."""
    track = Track(title="Test", duration_ms=300000)
    session.add(track)
    await session.flush()

    meta = YandexMetadata(
        track_id=track.track_id,
        yandex_track_id="103119407",
        yandex_album_id="36081872",
        album_title="Techgnosis, Vol. 6",
        album_genre="techno",
        label_name="Techgnosis",
        duration_ms=347150,
    )
    session.add(meta)
    await session.flush()

    assert meta.track_id == track.track_id
    assert meta.album_genre == "techno"
    assert meta.yandex_track_id == "103119407"


async def test_yandex_metadata_unique_yandex_track_id(session):
    """Duplicate yandex_track_id violates unique constraint."""
    t1 = Track(title="A", duration_ms=300000)
    t2 = Track(title="B", duration_ms=300000)
    session.add_all([t1, t2])
    await session.flush()

    meta1 = YandexMetadata(track_id=t1.track_id, yandex_track_id="111")
    session.add(meta1)
    await session.flush()

    meta2 = YandexMetadata(
        track_id=t2.track_id,
        yandex_track_id="111",  # same ym id
    )
    session.add(meta2)
    with pytest.raises(IntegrityError):
        await session.flush()
