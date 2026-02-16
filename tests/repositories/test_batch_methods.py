"""Tests for batch repository methods used by Rekordbox XML export.

These tests verify the SQL layer returns correct groupings.
Uses in-memory SQLite from conftest.py fixtures.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Genre,
    Label,
    Release,
    Track,
    TrackGenre,
    TrackRelease,
)
from app.models.dj import DjBeatgrid, DjCuePoint, DjSavedLoop
from app.models.runs import FeatureExtractionRun
from app.models.sections import TrackSection
from app.repositories.dj_beatgrid import DjBeatgridRepository
from app.repositories.dj_cue_points import DjCuePointRepository
from app.repositories.dj_saved_loops import DjSavedLoopRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository


@pytest.fixture
async def two_tracks(session: AsyncSession) -> tuple[int, int]:
    """Create two tracks and return their IDs."""
    t1 = Track(track_id=100, title="Track A", duration_ms=300_000)
    t2 = Track(track_id=200, title="Track B", duration_ms=400_000)
    session.add_all([t1, t2])
    await session.flush()
    return t1.track_id, t2.track_id


class TestDjCuePointRepository:
    async def test_get_by_track_ids_empty(self, session: AsyncSession):
        repo = DjCuePointRepository(session)
        result = await repo.get_by_track_ids([])
        assert result == {}

    async def test_get_by_track_ids(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, tid2 = two_tracks
        session.add_all([
            DjCuePoint(track_id=tid1, position_ms=0, cue_kind=0, hotcue_index=0),
            DjCuePoint(track_id=tid1, position_ms=64000, cue_kind=0, hotcue_index=1),
            DjCuePoint(track_id=tid2, position_ms=32000, cue_kind=0),
        ])
        await session.flush()

        repo = DjCuePointRepository(session)
        result = await repo.get_by_track_ids([tid1, tid2])
        assert len(result[tid1]) == 2
        assert len(result[tid2]) == 1

    async def test_missing_tracks_absent(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        session.add(DjCuePoint(track_id=tid1, position_ms=0, cue_kind=0))
        await session.flush()

        repo = DjCuePointRepository(session)
        result = await repo.get_by_track_ids([tid1, 999])
        assert tid1 in result
        assert 999 not in result


class TestDjSavedLoopRepository:
    async def test_get_by_track_ids(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        session.add(DjSavedLoop(
            track_id=tid1, in_ms=96000, out_ms=104000, length_ms=8000,
        ))
        await session.flush()

        repo = DjSavedLoopRepository(session)
        result = await repo.get_by_track_ids([tid1])
        assert len(result[tid1]) == 1
        assert result[tid1][0].in_ms == 96000


class TestDjBeatgridRepository:
    async def test_get_canonical_by_track_ids(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, tid2 = two_tracks
        session.add_all([
            DjBeatgrid(
                track_id=tid1, source_app=1, bpm=136.0,
                first_downbeat_ms=98, is_canonical=True,
            ),
            DjBeatgrid(
                track_id=tid1, source_app=2, bpm=136.0,
                first_downbeat_ms=100, is_canonical=False,
            ),
            DjBeatgrid(
                track_id=tid2, source_app=1, bpm=140.0,
                first_downbeat_ms=50, is_canonical=True,
            ),
        ])
        await session.flush()

        repo = DjBeatgridRepository(session)
        result = await repo.get_canonical_by_track_ids([tid1, tid2])
        assert result[tid1].bpm == 136.0
        assert result[tid1].first_downbeat_ms == 98  # canonical one
        assert result[tid2].bpm == 140.0

    async def test_no_canonical_returns_empty(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        session.add(DjBeatgrid(
            track_id=tid1, source_app=1, bpm=136.0,
            first_downbeat_ms=98, is_canonical=False,
        ))
        await session.flush()

        repo = DjBeatgridRepository(session)
        result = await repo.get_canonical_by_track_ids([tid1])
        assert tid1 not in result


class TestSectionsRepositoryBatch:
    async def test_get_latest_by_track_ids(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        # FeatureExtractionRun has no track_id — it's a standalone entity
        run = FeatureExtractionRun(
            pipeline_name="test", pipeline_version="1",
            status="completed",
        )
        session.add(run)
        await session.flush()

        session.add_all([
            TrackSection(
                track_id=tid1, run_id=run.run_id,
                start_ms=0, end_ms=32000, section_type=0,
                section_duration_ms=32000,
            ),
            TrackSection(
                track_id=tid1, run_id=run.run_id,
                start_ms=32000, end_ms=96000, section_type=2,
                section_duration_ms=64000,
            ),
        ])
        await session.flush()

        repo = SectionsRepository(session)
        result = await repo.get_latest_by_track_ids([tid1])
        assert len(result[tid1]) == 2


class TestTrackRepositoryBatch:
    async def test_get_genres_for_tracks(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        g = Genre(name="Techno")
        session.add(g)
        await session.flush()
        session.add(TrackGenre(track_id=tid1, genre_id=g.genre_id))
        await session.flush()

        repo = TrackRepository(session)
        result = await repo.get_genres_for_tracks([tid1])
        assert result[tid1] == ["Techno"]

    async def test_get_labels_for_tracks(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        label = Label(name="Drumcode")
        session.add(label)
        await session.flush()
        release = Release(title="EP", label_id=label.label_id)
        session.add(release)
        await session.flush()
        session.add(TrackRelease(track_id=tid1, release_id=release.release_id))
        await session.flush()

        repo = TrackRepository(session)
        result = await repo.get_labels_for_tracks([tid1])
        assert result[tid1] == ["Drumcode"]

    async def test_get_albums_for_tracks(
        self,
        session: AsyncSession,
        two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        release = Release(title="Night Sessions")
        session.add(release)
        await session.flush()
        session.add(TrackRelease(track_id=tid1, release_id=release.release_id))
        await session.flush()

        repo = TrackRepository(session)
        result = await repo.get_albums_for_tracks([tid1])
        assert result[tid1] == ["Night Sessions"]


# ---------------------------------------------------------------------------
# Key repository batch
# ---------------------------------------------------------------------------

from app.models.harmony import Key
from app.repositories.keys import KeyRepository


class TestKeyRepositoryBatch:
    async def test_get_key_names(self, session: AsyncSession):
        session.add_all([
            Key(key_code=18, pitch_class=9, mode=0, name="Am", camelot="8A"),
            Key(key_code=0, pitch_class=0, mode=0, name="Cm", camelot="5A"),
        ])
        await session.flush()

        repo = KeyRepository(session)
        result = await repo.get_key_names([18, 0])
        assert result[18] == "Am"
        assert result[0] == "Cm"

    async def test_get_key_names_empty(self, session: AsyncSession):
        repo = KeyRepository(session)
        result = await repo.get_key_names([])
        assert result == {}
