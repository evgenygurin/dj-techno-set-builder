"""E2E test: create tracks → enrich from YM (mocked) → verify all metadata populated."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.infrastructure.repositories.yandex_metadata import YandexMetadataRepository


def _make_ym_track(ym_id: int, title: str, artist: str, genre: str, label: str, year: int) -> dict:
    return {
        "id": ym_id,
        "title": title,
        "artists": [{"id": ym_id + 1000, "name": artist, "various": False}],
        "albums": [
            {
                "id": ym_id + 2000,
                "title": f"{artist} EP",
                "type": "single",
                "genre": genre,
                "labels": [label],
                "year": year,
                "releaseDate": f"{year}-06-01T00:00:00+03:00",
            }
        ],
        "durationMs": 300000,
    }


_MOCK_YM_DATA = {
    "jouska": _make_ym_track(
        103119407, "Octopus Neuroplasticity", "Jouska", "techno", "Techgnosis", 2022
    ),
    "klaudia gawlas": _make_ym_track(
        78966611, "Momentum", "Klaudia Gawlas", "techno", "KD RAW", 2021
    ),
    "fantoo": _make_ym_track(85546833, "Anxiety", "Fantoo", "techno", "Phobia", 2023),
}


async def _mock_search(query: str) -> list[dict]:
    """Return mock YM track for known queries by matching artist name."""
    q_lower = query.lower()
    for key, track in _MOCK_YM_DATA.items():
        if key in q_lower:
            return [track]
    return []


async def test_full_enrich_flow(session, seed_providers):
    """Create tracks → enrich → verify metadata chain."""
    from app.core.models import Track
    from app.services.import_yandex import ImportYandexService

    # 1. Create tracks directly via session
    tracks = []
    for title in [
        "Jouska — Octopus Neuroplasticity",
        "Klaudia Gawlas — Momentum",
        "Fantoo — Anxiety",
    ]:
        t = Track(title=title, duration_ms=300000)
        session.add(t)
        tracks.append(t)
    await session.flush()
    track_ids = [t.track_id for t in tracks]

    # 2. Enrich via ImportYandexService (mock YM client)
    mock_client = AsyncMock()
    mock_client.search_tracks = _mock_search

    svc = ImportYandexService(session=session, ym_client=mock_client)
    result = await svc.enrich_batch(track_ids)

    assert result["total"] == 3
    assert result["enriched"] == 3
    assert result["not_found"] == 0

    # 3. Verify YandexMetadata exists for all tracks
    repo = YandexMetadataRepository(session)
    for tid in track_ids:
        meta = await repo.get_by_track_id(tid)
        assert meta is not None, f"No YandexMetadata for track {tid}"
        assert meta.album_genre == "techno"

    # 4. Verify no unenriched tracks remain
    unenriched = await repo.list_unenriched_track_ids()
    for tid in track_ids:
        assert tid not in unenriched


async def test_enrich_api_endpoint(client):
    """POST /imports/yandex/enrich validates request body."""
    # Missing required field
    resp = await client.post("/api/v1/imports/yandex/enrich", json={})
    assert resp.status_code == 422

    # Empty track_ids list
    resp = await client.post("/api/v1/imports/yandex/enrich", json={"track_ids": []})
    assert resp.status_code == 422
