import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.dj import (
    DjAppExport,
    DjBeatgrid,
    DjBeatgridChangePoint,
    DjCuePoint,
    DjLibraryItem,
    DjPlaylist,
    DjPlaylistItem,
    DjSavedLoop,
)


async def _make_track(session: AsyncSession) -> Track:
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    return track


async def test_create_library_item(session: AsyncSession) -> None:
    track = await _make_track(session)
    item = DjLibraryItem(
        track_id=track.track_id,
        file_path="/music/track.flac",
        source_app=1,
    )
    session.add(item)
    await session.flush()
    assert item.library_item_id is not None


async def test_library_item_source_app_constraint(session: AsyncSession) -> None:
    """source_app must be between 1 and 5."""
    track = await _make_track(session)
    item = DjLibraryItem(
        track_id=track.track_id,
        source_app=99,
    )
    session.add(item)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_beatgrid(session: AsyncSession) -> None:
    track = await _make_track(session)
    bg = DjBeatgrid(
        track_id=track.track_id,
        source_app=1,
        bpm=128.0,
        first_downbeat_ms=500,
    )
    session.add(bg)
    await session.flush()
    assert bg.beatgrid_id is not None


async def test_beatgrid_bpm_constraint(session: AsyncSession) -> None:
    """bpm must be between 20 and 300."""
    track = await _make_track(session)
    bg = DjBeatgrid(
        track_id=track.track_id,
        source_app=1,
        bpm=999.0,
        first_downbeat_ms=0,
    )
    session.add(bg)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_beatgrid_track_source_unique(session: AsyncSession) -> None:
    """(track_id, source_app) must be unique."""
    track = await _make_track(session)
    bg1 = DjBeatgrid(track_id=track.track_id, source_app=1, bpm=128.0, first_downbeat_ms=0)
    bg2 = DjBeatgrid(track_id=track.track_id, source_app=1, bpm=130.0, first_downbeat_ms=0)
    session.add_all([bg1, bg2])
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_change_point(session: AsyncSession) -> None:
    track = await _make_track(session)
    bg = DjBeatgrid(track_id=track.track_id, source_app=1, bpm=128.0, first_downbeat_ms=0)
    session.add(bg)
    await session.flush()
    cp = DjBeatgridChangePoint(beatgrid_id=bg.beatgrid_id, position_ms=60000, bpm=130.0)
    session.add(cp)
    await session.flush()
    assert cp.point_id is not None


async def test_create_cue_point(session: AsyncSession) -> None:
    track = await _make_track(session)
    cue = DjCuePoint(
        track_id=track.track_id,
        position_ms=0,
        cue_kind=0,
        hotcue_index=0,
        label="Load",
        color_rgb=0xFF0000,
    )
    session.add(cue)
    await session.flush()
    assert cue.cue_id is not None


async def test_cue_kind_constraint(session: AsyncSession) -> None:
    """cue_kind must be between 0 and 7."""
    track = await _make_track(session)
    cue = DjCuePoint(track_id=track.track_id, position_ms=0, cue_kind=99)
    session.add(cue)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_saved_loop(session: AsyncSession) -> None:
    track = await _make_track(session)
    loop = DjSavedLoop(
        track_id=track.track_id,
        in_ms=16000,
        out_ms=32000,
        length_ms=16000,
    )
    session.add(loop)
    await session.flush()
    assert loop.loop_id is not None


async def test_saved_loop_range_check(session: AsyncSession) -> None:
    """out_ms must > in_ms and length_ms = out_ms - in_ms."""
    track = await _make_track(session)
    loop = DjSavedLoop(
        track_id=track.track_id,
        in_ms=32000,
        out_ms=16000,
        length_ms=16000,
    )
    session.add(loop)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_playlist_with_items(session: AsyncSession) -> None:
    track = await _make_track(session)
    pl = DjPlaylist(name="My Techno", source_app=1)
    session.add(pl)
    await session.flush()
    item = DjPlaylistItem(
        playlist_id=pl.playlist_id,
        track_id=track.track_id,
        sort_index=0,
    )
    session.add(item)
    await session.flush()
    assert item.playlist_item_id is not None


async def test_playlist_sort_index_unique(session: AsyncSession) -> None:
    """(playlist_id, sort_index) must be unique."""
    track = await _make_track(session)
    pl = DjPlaylist(name="Test", source_app=1)
    session.add(pl)
    await session.flush()
    i1 = DjPlaylistItem(playlist_id=pl.playlist_id, track_id=track.track_id, sort_index=0)
    i2 = DjPlaylistItem(playlist_id=pl.playlist_id, track_id=track.track_id, sort_index=0)
    session.add_all([i1, i2])
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_app_export(session: AsyncSession) -> None:
    export = DjAppExport(
        target_app=1,
        export_format="nml",
        storage_uri="s3://exports/export_1.nml",
    )
    session.add(export)
    await session.flush()
    assert export.export_id is not None


async def test_app_export_target_app_constraint(session: AsyncSession) -> None:
    """target_app must be between 1 and 3."""
    export = DjAppExport(target_app=99, export_format="nml")
    session.add(export)
    with pytest.raises(IntegrityError):
        await session.flush()
