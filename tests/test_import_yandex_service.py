from unittest.mock import AsyncMock

from sqlalchemy import text

from app.core.models import Track


async def test_enrich_track_creates_metadata(session, seed_providers):
    """Enriching a track creates YandexMetadata + links Artist/Genre/Label/Release."""
    from app.services.import_yandex import ImportYandexService

    track = Track(title="Jouska — Octopus Neuroplasticity", duration_ms=347150)
    session.add(track)
    await session.flush()

    mock_ym_track = {
        "id": 103119407,
        "title": "Octopus Neuroplasticity",
        "artists": [{"id": 3976138, "name": "Jouska", "various": False}],
        "albums": [
            {
                "id": 36081872,
                "title": "Techgnosis, Vol. 6",
                "type": "compilation",
                "genre": "techno",
                "labels": ["Techgnosis"],
                "year": 2022,
                "releaseDate": "2022-03-21T00:00:00+03:00",
                "trackPosition": {"volume": 1, "index": 4},
            }
        ],
        "durationMs": 347150,
    }

    mock_client = AsyncMock()
    mock_client.search_tracks.return_value = [mock_ym_track]

    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id)
    assert result is True

    # Verify YandexMetadata
    from app.infrastructure.repositories.yandex_metadata import YandexMetadataRepository

    meta = await YandexMetadataRepository(session).get_by_track_id(track.track_id)
    assert meta is not None
    assert meta.album_genre == "techno"

    # Verify Artist linked
    r = await session.execute(
        text("SELECT count(*) FROM track_artists WHERE track_id = :tid"),
        {"tid": track.track_id},
    )
    assert r.scalar() >= 1

    # Verify Genre linked
    r = await session.execute(
        text("SELECT count(*) FROM track_genres WHERE track_id = :tid"),
        {"tid": track.track_id},
    )
    assert r.scalar() >= 1


async def test_enrich_track_not_found_on_ym(session):
    """Returns False if track not found on Yandex Music."""
    from app.services.import_yandex import ImportYandexService

    track = Track(title="Nonexistent — Track", duration_ms=300000)
    session.add(track)
    await session.flush()

    mock_client = AsyncMock()
    mock_client.search_tracks.return_value = []

    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id)
    assert result is False


async def test_enrich_track_handles_empty_labels(session, seed_providers):
    """Empty labels list doesn't crash."""
    from app.services.import_yandex import ImportYandexService

    track = Track(title="Test — Track", duration_ms=300000)
    session.add(track)
    await session.flush()

    mock_ym_track = {
        "id": 999,
        "title": "Track",
        "artists": [{"id": 1, "name": "Test", "various": False}],
        "albums": [{"id": 10, "title": "EP", "genre": "techno", "labels": [], "year": 2024}],
        "durationMs": 300000,
    }

    mock_client = AsyncMock()
    mock_client.search_tracks.return_value = [mock_ym_track]

    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id)
    assert result is True


async def test_enrich_track_skips_already_enriched(session):
    """Returns True immediately if track already has YandexMetadata."""
    from app.services.import_yandex import ImportYandexService

    track = Track(title="Already Enriched", duration_ms=300000)
    session.add(track)
    await session.flush()

    # Pre-create metadata
    from app.core.models.metadata_yandex import YandexMetadata

    meta = YandexMetadata(
        track_id=track.track_id,
        yandex_track_id="existing_123",
    )
    session.add(meta)
    await session.flush()

    mock_client = AsyncMock()
    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id)
    assert result is True
    # search_tracks should NOT have been called
    mock_client.search_tracks.assert_not_called()


async def test_enrich_track_nonexistent_track_id(session):
    """Returns False for a track_id that doesn't exist in DB."""
    from app.services.import_yandex import ImportYandexService

    mock_client = AsyncMock()
    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(999999)
    assert result is False
    mock_client.search_tracks.assert_not_called()


async def test_enrich_batch(session, seed_providers):
    """Batch enrichment returns correct summary."""
    from app.services.import_yandex import ImportYandexService

    t1 = Track(title="Found Track", duration_ms=300000)
    t2 = Track(title="Missing Tune XYZ", duration_ms=300000)
    session.add_all([t1, t2])
    await session.flush()

    mock_ym_track = {
        "id": 111,
        "title": "Found Track",
        "artists": [{"id": 1, "name": "DJ Test", "various": False}],
        "albums": [{"id": 10, "title": "Album", "genre": "techno", "labels": [], "year": 2024}],
        "durationMs": 300000,
    }

    mock_client = AsyncMock()

    async def _search(query):
        if "Found Track" in query:
            return [mock_ym_track]
        return []

    mock_client.search_tracks.side_effect = _search

    svc = ImportYandexService(session=session, ym_client=mock_client)
    summary = await svc.enrich_batch([t1.track_id, t2.track_id])

    assert summary["total"] == 2
    assert summary["enriched"] == 1
    assert summary["not_found"] == 1
    assert summary["errors"] == []
