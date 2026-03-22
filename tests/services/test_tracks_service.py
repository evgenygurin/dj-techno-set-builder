"""Tests for TrackService CRUD operations."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.catalog import Track
from app.repositories.tracks import TrackRepository
from app.schemas.tracks import TrackCreate, TrackUpdate
from app.services.tracks import TrackService

# Unique prefix to avoid collisions with other tests
_PREFIX = "tsvc_"


def _make_service(session: AsyncSession) -> TrackService:
    return TrackService(TrackRepository(session))


async def _seed_track(
    session: AsyncSession, *, title: str = "Seed Track", duration_ms: int = 300_000
) -> Track:
    track = Track(title=title, duration_ms=duration_ms, status=0)
    session.add(track)
    await session.flush()
    return track


# -- get --


async def test_get_found(session: AsyncSession) -> None:
    track = await _seed_track(session, title=f"{_PREFIX}get_found")
    await session.commit()

    svc = _make_service(session)
    result = await svc.get(track.track_id)

    assert result.track_id == track.track_id
    assert result.title == f"{_PREFIX}get_found"
    assert result.status == 0


async def test_get_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.get(99_999)


# -- list --


async def test_list_returns_paginated(session: AsyncSession) -> None:
    svc = _make_service(session)
    before = await svc.list(offset=0, limit=1000)
    existing = before.total

    for i in range(3):
        await _seed_track(session, title=f"{_PREFIX}list_{i}", duration_ms=200_000 + i)
    await session.commit()

    result = await svc.list(offset=0, limit=2)
    assert len(result.items) <= 2
    assert result.total == existing + 3


async def test_list_empty_when_offset_beyond(session: AsyncSession) -> None:
    svc = _make_service(session)
    result = await svc.list(offset=999_999, limit=50)
    assert result.items == []
    assert result.total >= 0


async def test_list_search_filters(session: AsyncSession) -> None:
    unique = f"{_PREFIX}xyzuniq"
    await _seed_track(session, title=unique)
    await session.commit()

    svc = _make_service(session)
    result = await svc.list(search=unique)
    assert result.total >= 1
    assert any(item.title == unique for item in result.items)


# -- create --


async def test_create_track(session: AsyncSession) -> None:
    svc = _make_service(session)
    data = TrackCreate(title=f"{_PREFIX}created", duration_ms=180_000)
    result = await svc.create(data)
    await session.commit()

    assert result.track_id is not None
    assert result.title == f"{_PREFIX}created"
    assert result.duration_ms == 180_000
    assert result.status == 0
    assert result.title_sort is None


async def test_create_track_with_title_sort(session: AsyncSession) -> None:
    svc = _make_service(session)
    data = TrackCreate(title=f"{_PREFIX}Sorted", title_sort="sorted", duration_ms=120_000)
    result = await svc.create(data)
    await session.commit()

    assert result.title_sort == "sorted"


# -- update --


async def test_update_title(session: AsyncSession) -> None:
    track = await _seed_track(session, title=f"{_PREFIX}before_update")
    await session.commit()

    svc = _make_service(session)
    data = TrackUpdate(title=f"{_PREFIX}after_update")
    result = await svc.update(track.track_id, data)
    await session.commit()

    assert result.title == f"{_PREFIX}after_update"
    assert result.track_id == track.track_id


async def test_update_duration(session: AsyncSession) -> None:
    track = await _seed_track(session, title=f"{_PREFIX}dur_update", duration_ms=100_000)
    await session.commit()

    svc = _make_service(session)
    data = TrackUpdate(duration_ms=250_000)
    result = await svc.update(track.track_id, data)
    await session.commit()

    assert result.duration_ms == 250_000


async def test_update_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.update(99_998, TrackUpdate(title="nope"))


# -- delete --


async def test_delete_track(session: AsyncSession) -> None:
    track = await _seed_track(session, title=f"{_PREFIX}to_delete")
    await session.commit()
    tid = track.track_id

    svc = _make_service(session)
    await svc.delete(tid)
    await session.commit()

    with pytest.raises(NotFoundError):
        await svc.get(tid)


async def test_delete_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.delete(99_997)
