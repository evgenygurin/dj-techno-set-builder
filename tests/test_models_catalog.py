import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Artist,
    Genre,
    Label,
    Release,
    Track,
    TrackArtist,
    TrackGenre,
    TrackRelease,
)


async def test_create_label(session: AsyncSession) -> None:
    label = Label(name="Drumcode")
    session.add(label)
    await session.flush()
    assert label.label_id is not None


async def test_create_release_with_label(session: AsyncSession) -> None:
    label = Label(name="Drumcode")
    session.add(label)
    await session.flush()
    release = Release(title="A-Sides Vol.12", label_id=label.label_id)
    session.add(release)
    await session.flush()
    assert release.release_id is not None


async def test_release_date_precision_constraint(session: AsyncSession) -> None:
    """release_date_precision must be 'year', 'month', or 'day'."""
    release = Release(title="Bad", release_date_precision="century")
    session.add(release)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_track_artist_role_constraint(session: AsyncSession) -> None:
    """role must be 0, 1, or 2."""
    track = Track(title="T", duration_ms=300000)
    artist = Artist(name="A")
    session.add_all([track, artist])
    await session.flush()
    ta = TrackArtist(track_id=track.track_id, artist_id=artist.artist_id, role=99)
    session.add(ta)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_genre_self_reference(session: AsyncSession) -> None:
    parent = Genre(name="Techno")
    session.add(parent)
    await session.flush()
    child = Genre(name="Hard Techno", parent_genre_id=parent.genre_id)
    session.add(child)
    await session.flush()
    assert child.parent_genre_id == parent.genre_id


async def test_genre_name_unique(session: AsyncSession) -> None:
    session.add(Genre(name="Techno"))
    session.add(Genre(name="Techno"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_track_release_composite_pk(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    release = Release(title="R")
    session.add_all([track, release])
    await session.flush()
    tr = TrackRelease(
        track_id=track.track_id,
        release_id=release.release_id,
        track_number=1,
    )
    session.add(tr)
    await session.flush()
    assert tr.track_id is not None


async def test_track_genre_with_provider(session: AsyncSession) -> None:
    from app.models.providers import Provider

    track = Track(title="T", duration_ms=300000)
    genre = Genre(name="Techno")
    prov = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add_all([track, genre, prov])
    await session.flush()
    tg = TrackGenre(
        track_id=track.track_id,
        genre_id=genre.genre_id,
        source_provider_id=1,
    )
    session.add(tg)
    await session.flush()
    assert tg.track_genre_id is not None
