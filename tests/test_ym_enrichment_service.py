from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.providers import Provider
from app.services.yandex_music_enrichment import YandexMusicEnrichmentService


async def test_enrich_track_creates_genre_and_artist(
    session: AsyncSession,
) -> None:
    """Enrichment creates Genre, Artist, Label, Release, and links them."""
    track = Track(title="Jouska — Octopus Neuroplasticity", duration_ms=347150)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    ym_track_data = {
        "id": 103119407,
        "title": "Octopus Neuroplasticity",
        "artists": [
            {"id": 3976138, "name": "Jouska", "various": False},
        ],
        "albums": [
            {
                "id": 36081872,
                "title": "Techgnosis, Vol. 6",
                "genre": "techno",
                "labels": ["Techgnosis"],
                "releaseDate": "2022-03-21T00:00:00+03:00",
                "year": 2022,
                "trackPosition": {"volume": 1, "index": 4},
            }
        ],
    }

    mock_client = AsyncMock()
    mock_client.fetch_tracks.return_value = {"103119407": ym_track_data}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id, yandex_track_id="103119407")

    assert result.genre == "techno"
    assert result.artists == ["Jouska"]
    assert result.label == "Techgnosis"
    assert result.release_title == "Techgnosis, Vol. 6"
    assert not result.already_linked


async def test_enrich_track_empty_labels(session: AsyncSession) -> None:
    """Enrichment handles albums with empty labels array (problem #4)."""
    track = Track(title="Test Track", duration_ms=300000)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    ym_track_data = {
        "id": 999,
        "title": "Test",
        "artists": [{"id": 1, "name": "Artist", "various": False}],
        "albums": [
            {
                "id": 1,
                "title": "Album",
                "genre": "techno",
                "labels": [],
                "year": 2024,
            }
        ],
    }

    mock_client = AsyncMock()
    mock_client.fetch_tracks.return_value = {"999": ym_track_data}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id, yandex_track_id="999")
    assert result.label is None


async def test_enrich_track_idempotent(session: AsyncSession) -> None:
    """Second enrichment of same track returns already_linked=True."""
    track = Track(title="Test", duration_ms=300000)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    ym_data = {
        "id": 123,
        "title": "Test",
        "artists": [],
        "albums": [
            {
                "id": 1,
                "title": "A",
                "genre": "techno",
                "labels": [],
                "year": 2024,
            }
        ],
    }
    mock_client = AsyncMock()
    mock_client.fetch_tracks.return_value = {"123": ym_data}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    r1 = await svc.enrich_track(track.track_id, yandex_track_id="123")
    assert not r1.already_linked

    r2 = await svc.enrich_track(track.track_id, yandex_track_id="123")
    assert r2.already_linked


async def test_enrich_batch_auto_search(session: AsyncSession) -> None:
    """Batch enrichment auto-searches YM by parsing track title."""
    track = Track(title="Jouska — Octopus Neuroplasticity", duration_ms=347150)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    mock_client = AsyncMock()
    mock_client.search_tracks.return_value = [
        {
            "id": 103119407,
            "title": "Octopus Neuroplasticity",
            "artists": [{"name": "Jouska", "various": False}],
            "albums": [
                {
                    "title": "Techgnosis",
                    "genre": "techno",
                    "labels": ["Techgnosis"],
                    "year": 2022,
                }
            ],
        }
    ]
    mock_client.fetch_tracks.return_value = {
        "103119407": {
            "id": 103119407,
            "title": "Octopus Neuroplasticity",
            "artists": [{"id": 1, "name": "Jouska", "various": False}],
            "albums": [
                {
                    "id": 1,
                    "title": "Techgnosis",
                    "genre": "techno",
                    "labels": ["Techgnosis"],
                    "year": 2022,
                }
            ],
        }
    }

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    results = await svc.enrich_batch([track.track_id])

    assert len(results) == 1
    assert results[0].genre == "techno"
