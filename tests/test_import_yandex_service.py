from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.errors import NotFoundError
from app.models import Track


async def test_import_creates_metadata(session, seed_providers):
    """Importing a track creates YandexMetadata + links Artist/Genre/Label/Release."""
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
    result = await svc.import_by_search(track.track_id)
    assert result is True

    from app.repositories.yandex_metadata import YandexMetadataRepository

    meta = await YandexMetadataRepository(session).get_by_track_id(track.track_id)
    assert meta is not None
    assert meta.album_genre == "techno"

    r = await session.execute(
        text("SELECT count(*) FROM track_artists WHERE track_id = :tid"),
        {"tid": track.track_id},
    )
    assert r.scalar() >= 1

    r = await session.execute(
        text("SELECT count(*) FROM track_genres WHERE track_id = :tid"),
        {"tid": track.track_id},
    )
    assert r.scalar() >= 1


async def test_import_not_found_on_ym(session, seed_providers):
    """Returns False if track not found on Yandex Music."""
    from app.services.import_yandex import ImportYandexService

    track = Track(title="Nonexistent — Track", duration_ms=300000)
    session.add(track)
    await session.flush()

    mock_client = AsyncMock()
    mock_client.search_tracks.return_value = []

    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.import_by_search(track.track_id)
    assert result is False


async def test_import_handles_empty_labels(session, seed_providers):
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
    result = await svc.import_by_search(track.track_id)
    assert result is True


async def test_import_skips_already_linked(session, seed_providers):
    """Returns True immediately if track already linked to YM."""
    from app.models.ingestion import ProviderTrackId
    from app.services.import_yandex import ImportYandexService

    track = Track(title="Already Linked", duration_ms=300000)
    session.add(track)
    await session.flush()

    session.add(
        ProviderTrackId(
            track_id=track.track_id,
            provider_id=4,
            provider_track_id="existing_123",
        )
    )
    await session.flush()

    mock_client = AsyncMock()
    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.import_by_search(track.track_id)
    assert result is True
    mock_client.search_tracks.assert_not_called()


async def test_import_nonexistent_track_raises(session, seed_providers):
    """Raises NotFoundError for a track_id that doesn't exist."""
    from app.services.import_yandex import ImportYandexService

    mock_client = AsyncMock()
    svc = ImportYandexService(session=session, ym_client=mock_client)
    with pytest.raises(NotFoundError):
        await svc.import_by_search(999999)


async def test_import_batch(session, seed_providers):
    """Batch import returns correct summary."""
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

    async def _search(query, **kwargs):
        if "Found Track" in query:
            return [mock_ym_track]
        return []

    mock_client.search_tracks.side_effect = _search

    svc = ImportYandexService(session=session, ym_client=mock_client)
    summary = await svc.import_batch([t1.track_id, t2.track_id])

    assert summary["total"] == 2
    assert summary["imported"] == 1
    assert summary["not_found"] == 1
    assert summary["errors"] == []
