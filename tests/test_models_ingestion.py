from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId, RawProviderResponse
from app.models.providers import Provider


async def test_create_provider_track_id(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    prov = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add_all([track, prov])
    await session.flush()

    ptid = ProviderTrackId(
        track_id=track.track_id,
        provider_id=1,
        provider_track_id="6rqhFgbbKwnb9MLmUQDhG6",
        provider_country="US",
    )
    session.add(ptid)
    await session.flush()
    assert ptid.track_id == track.track_id


async def test_create_raw_provider_response(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    prov = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add_all([track, prov])
    await session.flush()

    raw = RawProviderResponse(
        track_id=track.track_id,
        provider_id=1,
        provider_track_id="6rqhFgbbKwnb9MLmUQDhG6",
        endpoint="audio-features",
        payload={"tempo": 128.0},
    )
    session.add(raw)
    await session.flush()
    assert raw.id is not None
