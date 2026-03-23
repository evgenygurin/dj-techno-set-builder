from app.core.models import Track
from app.infrastructure.repositories.yandex_metadata import YandexMetadataRepository


async def test_get_by_yandex_track_id_returns_none(session):
    repo = YandexMetadataRepository(session)
    assert await repo.get_by_yandex_track_id("999") is None


async def test_upsert_creates(session):
    track = Track(title="Test", duration_ms=300000)
    session.add(track)
    await session.flush()

    repo = YandexMetadataRepository(session)
    meta = await repo.upsert(
        track_id=track.track_id,
        yandex_track_id="103119407",
        album_genre="techno",
        label_name="Techgnosis",
    )
    assert meta.yandex_track_id == "103119407"
    assert meta.album_genre == "techno"


async def test_upsert_updates_existing(session):
    track = Track(title="Test", duration_ms=300000)
    session.add(track)
    await session.flush()

    repo = YandexMetadataRepository(session)
    await repo.upsert(
        track_id=track.track_id,
        yandex_track_id="103119407",
        album_genre="techno",
    )

    meta = await repo.upsert(
        track_id=track.track_id,
        yandex_track_id="103119407",
        album_genre="melodic techno",
    )
    assert meta.album_genre == "melodic techno"


async def test_list_unenriched(session):
    """Returns track_ids that have no YandexMetadata."""
    t1 = Track(title="Enriched", duration_ms=300000)
    t2 = Track(title="Not enriched", duration_ms=300000)
    session.add_all([t1, t2])
    await session.flush()

    repo = YandexMetadataRepository(session)
    await repo.upsert(track_id=t1.track_id, yandex_track_id="111")

    unenriched = await repo.list_unenriched_track_ids()
    assert t2.track_id in unenriched
    assert t1.track_id not in unenriched
