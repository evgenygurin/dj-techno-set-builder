"""Tests for DjPlaylistService CRUD and item operations."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, Field

from app.core.errors import NotFoundError
from app.core.models.catalog import Track
from app.core.models.dj import DjPlaylist
from app.infrastructure.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.services.playlists import DjPlaylistService


class DjPlaylistCreate(BaseModel):
    """Minimal stand-in for the deleted REST schema."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=500)
    parent_playlist_id: int | None = None
    source_app: int | None = None
    source_of_truth: str = "local"
    platform_ids: dict[str, str] | None = None


class DjPlaylistUpdate(BaseModel):
    """Minimal stand-in for the deleted REST schema."""

    model_config = {"extra": "forbid"}

    name: str | None = None
    parent_playlist_id: int | None = None
    source_app: int | None = None
    source_of_truth: str | None = None
    platform_ids: dict[str, str] | None = None


class DjPlaylistItemCreate(BaseModel):
    """Minimal stand-in for the deleted REST schema."""

    model_config = {"extra": "forbid"}

    track_id: int
    sort_index: int = Field(ge=0)

# Unique prefix to avoid collisions with other tests
_PREFIX = "plsvc_"


def _make_service(session: AsyncSession) -> DjPlaylistService:
    return DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )


async def _seed_playlist(session: AsyncSession, *, name: str = "Seed Playlist") -> DjPlaylist:
    pl = DjPlaylist(name=name)
    session.add(pl)
    await session.flush()
    return pl


async def _seed_track(
    session: AsyncSession, *, title: str = "Seed Track", duration_ms: int = 300_000
) -> Track:
    track = Track(title=title, duration_ms=duration_ms, status=0)
    session.add(track)
    await session.flush()
    return track


# -- get --


async def test_get_found(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}get_found")
    await session.commit()

    svc = _make_service(session)
    result = await svc.get(pl.playlist_id)

    assert result.playlist_id == pl.playlist_id
    assert result.name == f"{_PREFIX}get_found"
    assert result.source_of_truth == "local"


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
        await _seed_playlist(session, name=f"{_PREFIX}list_{i}")
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
    await _seed_playlist(session, name=unique)
    await session.commit()

    svc = _make_service(session)
    result = await svc.list(search=unique)
    assert result.total >= 1
    assert any(item.name == unique for item in result.items)


# -- create --


async def test_create_playlist(session: AsyncSession) -> None:
    svc = _make_service(session)
    data = DjPlaylistCreate(name=f"{_PREFIX}created")
    result = await svc.create(data)
    await session.commit()

    assert result.playlist_id is not None
    assert result.name == f"{_PREFIX}created"
    assert result.source_of_truth == "local"
    assert result.parent_playlist_id is None
    assert result.platform_ids is None


async def test_create_playlist_with_source_app(session: AsyncSession) -> None:
    svc = _make_service(session)
    data = DjPlaylistCreate(name=f"{_PREFIX}with_app", source_app=3)
    result = await svc.create(data)
    await session.commit()

    assert result.source_app == 3


async def test_create_playlist_with_platform_ids(session: AsyncSession) -> None:
    svc = _make_service(session)
    data = DjPlaylistCreate(
        name=f"{_PREFIX}with_pids",
        source_of_truth="ym",
        platform_ids={"ym": "1234"},
    )
    result = await svc.create(data)
    await session.commit()

    assert result.source_of_truth == "ym"
    assert result.platform_ids == {"ym": "1234"}


# -- update --


async def test_update_name(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}before_update")
    await session.commit()

    svc = _make_service(session)
    data = DjPlaylistUpdate(name=f"{_PREFIX}after_update")
    result = await svc.update(pl.playlist_id, data)
    await session.commit()

    assert result.name == f"{_PREFIX}after_update"
    assert result.playlist_id == pl.playlist_id


async def test_update_source_of_truth(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}sot_update")
    await session.commit()

    svc = _make_service(session)
    data = DjPlaylistUpdate(source_of_truth="ym")
    result = await svc.update(pl.playlist_id, data)
    await session.commit()

    assert result.source_of_truth == "ym"


async def test_update_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.update(99_998, DjPlaylistUpdate(name="nope"))


# -- delete --


async def test_delete_playlist(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}to_delete")
    await session.commit()
    pid = pl.playlist_id

    svc = _make_service(session)
    await svc.delete(pid)
    await session.commit()

    with pytest.raises(NotFoundError):
        await svc.get(pid)


async def test_delete_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.delete(99_997)


# -- list_items --


async def test_list_items_empty(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}items_empty")
    await session.commit()

    svc = _make_service(session)
    result = await svc.list_items(pl.playlist_id)
    assert result.items == []
    assert result.total == 0


async def test_list_items_with_tracks(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}items_filled")
    t1 = await _seed_track(session, title=f"{_PREFIX}item_t1")
    t2 = await _seed_track(session, title=f"{_PREFIX}item_t2")
    await session.commit()

    svc = _make_service(session)
    await svc.add_item(pl.playlist_id, DjPlaylistItemCreate(track_id=t1.track_id, sort_index=0))
    await svc.add_item(pl.playlist_id, DjPlaylistItemCreate(track_id=t2.track_id, sort_index=1))
    await session.commit()

    result = await svc.list_items(pl.playlist_id)
    assert result.total == 2
    assert len(result.items) == 2
    track_ids = {item.track_id for item in result.items}
    assert t1.track_id in track_ids
    assert t2.track_id in track_ids


async def test_list_items_playlist_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.list_items(99_996)


async def test_list_items_paginated(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}items_paged")
    tracks = []
    for i in range(3):
        t = await _seed_track(session, title=f"{_PREFIX}page_t{i}")
        tracks.append(t)
    await session.commit()

    svc = _make_service(session)
    for i, t in enumerate(tracks):
        await svc.add_item(pl.playlist_id, DjPlaylistItemCreate(track_id=t.track_id, sort_index=i))
    await session.commit()

    result = await svc.list_items(pl.playlist_id, offset=0, limit=2)
    assert len(result.items) == 2
    assert result.total == 3


# -- add_item --


async def test_add_item(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}add_item")
    track = await _seed_track(session, title=f"{_PREFIX}add_item_t")
    await session.commit()

    svc = _make_service(session)
    data = DjPlaylistItemCreate(track_id=track.track_id, sort_index=0)
    result = await svc.add_item(pl.playlist_id, data)
    await session.commit()

    assert result.playlist_item_id is not None
    assert result.playlist_id == pl.playlist_id
    assert result.track_id == track.track_id
    assert result.sort_index == 0


async def test_add_item_playlist_not_found(session: AsyncSession) -> None:
    track = await _seed_track(session, title=f"{_PREFIX}orphan_item")
    await session.commit()

    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.add_item(99_995, DjPlaylistItemCreate(track_id=track.track_id, sort_index=0))


# -- remove_item --


async def test_remove_item(session: AsyncSession) -> None:
    pl = await _seed_playlist(session, name=f"{_PREFIX}rm_item")
    track = await _seed_track(session, title=f"{_PREFIX}rm_item_t")
    await session.commit()

    svc = _make_service(session)
    item = await svc.add_item(
        pl.playlist_id, DjPlaylistItemCreate(track_id=track.track_id, sort_index=0)
    )
    await session.commit()

    await svc.remove_item(item.playlist_item_id)
    await session.commit()

    result = await svc.list_items(pl.playlist_id)
    assert result.total == 0


async def test_remove_item_not_found(session: AsyncSession) -> None:
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        await svc.remove_item(99_994)
