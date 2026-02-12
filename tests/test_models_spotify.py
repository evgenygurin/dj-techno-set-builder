import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.metadata_spotify import (
    SpotifyAlbumMetadata,
    SpotifyAudioFeatures,
    SpotifyMetadata,
)


async def test_create_spotify_metadata(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    sm = SpotifyMetadata(
        track_id=track.track_id,
        spotify_track_id="6rqhFgbbKwnb9MLmUQDhG6",
    )
    session.add(sm)
    await session.flush()
    assert sm.track_id == track.track_id


async def test_spotify_popularity_constraint(session: AsyncSession) -> None:
    """popularity must be between 0 and 100."""
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    sm = SpotifyMetadata(
        track_id=track.track_id,
        spotify_track_id="abc",
        popularity=200,
    )
    session.add(sm)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_spotify_audio_features_mode_constraint(session: AsyncSession) -> None:
    """mode must be 0 or 1."""
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    saf = SpotifyAudioFeatures(
        track_id=track.track_id,
        danceability=0.8,
        energy=0.9,
        loudness=-5.0,
        speechiness=0.04,
        acousticness=0.01,
        instrumentalness=0.95,
        liveness=0.1,
        valence=0.3,
        tempo=128.0,
        time_signature=4,
        key=5,
        mode=2,
    )
    session.add(saf)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_spotify_album_metadata(session: AsyncSession) -> None:
    album = SpotifyAlbumMetadata(
        spotify_album_id="2noRn2Aes5aoNVsU6iWThc",
        album_type="album",
        name="Test Album",
    )
    session.add(album)
    await session.flush()
    assert album.spotify_album_id == "2noRn2Aes5aoNVsU6iWThc"
