"""Tests for AudioFeaturesRepository.filter_by_criteria — SQL-level filtering.

Uses in-memory SQLite (via ``engine`` fixture) to verify deduplication
and filtering logic end-to-end.  Each test creates a function-scoped
engine to avoid cross-test contamination.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.models import Base
from app.core.models.catalog import Track
from app.core.models.features import TrackAudioFeaturesComputed
from app.core.models.runs import FeatureExtractionRun
from app.infrastructure.repositories.audio.features import AudioFeaturesRepository


@pytest.fixture
async def fresh_engine():
    """Function-scoped in-memory SQLite engine — isolated per test."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


async def _seed(fresh_engine) -> None:
    """Seed two tracks with two extraction runs each (v1 and v2)."""
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        t1 = Track(title="Track A", duration_ms=300_000)
        t2 = Track(title="Track B", duration_ms=400_000)
        session.add_all([t1, t2])
        await session.flush()

        run1 = FeatureExtractionRun(
            pipeline_name="v1.0", pipeline_version="1.0", status="completed"
        )
        run2 = FeatureExtractionRun(
            pipeline_name="v2.1b6", pipeline_version="2.1b6", status="completed"
        )
        session.add_all([run1, run2])
        await session.flush()

        # Track A: run1 bpm=130, run2 bpm=132 (latest)
        f1_old = TrackAudioFeaturesComputed(
            track_id=t1.track_id,
            run_id=run1.run_id,
            bpm=130.0,
            tempo_confidence=0.9,
            bpm_stability=0.8,
            lufs_i=-10.0,
            rms_dbfs=-11.0,
            energy_mean=0.4,
            energy_max=0.8,
            energy_std=0.1,
            key_code=8,
            key_confidence=0.7,
        )
        f1_new = TrackAudioFeaturesComputed(
            track_id=t1.track_id,
            run_id=run2.run_id,
            bpm=132.0,
            tempo_confidence=0.95,
            bpm_stability=0.85,
            lufs_i=-9.0,
            rms_dbfs=-10.0,
            energy_mean=0.5,
            energy_max=0.9,
            energy_std=0.12,
            key_code=8,
            key_confidence=0.8,
        )
        # Track B: run1 bpm=140, run2 bpm=142 (latest)
        f2_old = TrackAudioFeaturesComputed(
            track_id=t2.track_id,
            run_id=run1.run_id,
            bpm=140.0,
            tempo_confidence=0.85,
            bpm_stability=0.7,
            lufs_i=-8.0,
            rms_dbfs=-9.0,
            energy_mean=0.6,
            energy_max=1.0,
            energy_std=0.15,
            key_code=10,
            key_confidence=0.9,
        )
        f2_new = TrackAudioFeaturesComputed(
            track_id=t2.track_id,
            run_id=run2.run_id,
            bpm=142.0,
            tempo_confidence=0.9,
            bpm_stability=0.75,
            lufs_i=-7.0,
            rms_dbfs=-8.0,
            energy_mean=0.65,
            energy_max=1.0,
            energy_std=0.14,
            key_code=10,
            key_confidence=0.92,
        )
        session.add_all([f1_old, f1_new, f2_old, f2_new])
        await session.commit()


async def test_filter_no_duplicates(fresh_engine):
    """filter_by_criteria returns one row per track (latest run only)."""
    await _seed(fresh_engine)
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        repo = AudioFeaturesRepository(session)
        results, total = await repo.filter_by_criteria(offset=0, limit=50)

    assert total == 2
    assert len(results) == 2
    track_ids = [r.track_id for r in results]
    assert len(set(track_ids)) == 2, "Each track should appear exactly once"


async def test_filter_returns_latest_run(fresh_engine):
    """filter_by_criteria returns features from the latest extraction run."""
    await _seed(fresh_engine)
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        repo = AudioFeaturesRepository(session)
        results, _ = await repo.filter_by_criteria(offset=0, limit=50)

    by_track = {r.track_id: r for r in results}
    for feat in by_track.values():
        assert feat.bpm in (132.0, 142.0), f"Expected latest BPM, got {feat.bpm}"


async def test_filter_bpm_range(fresh_engine):
    """BPM range filter works correctly with deduplication."""
    await _seed(fresh_engine)
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        repo = AudioFeaturesRepository(session)
        results, total = await repo.filter_by_criteria(
            bpm_min=140.0, bpm_max=150.0, offset=0, limit=50
        )

    assert total == 1
    assert len(results) == 1
    assert results[0].bpm == 142.0


async def test_filter_energy_range(fresh_engine):
    """Energy filter works correctly."""
    await _seed(fresh_engine)
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        repo = AudioFeaturesRepository(session)
        results, total = await repo.filter_by_criteria(energy_min=0.6, offset=0, limit=50)

    assert total == 1
    assert results[0].energy_mean == 0.65


async def test_filter_key_codes(fresh_engine):
    """key_codes filter works correctly."""
    await _seed(fresh_engine)
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        repo = AudioFeaturesRepository(session)
        results, total = await repo.filter_by_criteria(key_codes=[8], offset=0, limit=50)

    assert total == 1
    assert results[0].key_code == 8


async def test_filter_combined_criteria(fresh_engine):
    """Multiple filters combine correctly."""
    await _seed(fresh_engine)
    factory = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with factory() as session:
        repo = AudioFeaturesRepository(session)
        results, total = await repo.filter_by_criteria(
            bpm_min=130.0, bpm_max=145.0, key_codes=[10], offset=0, limit=50
        )

    assert total == 1
    assert results[0].bpm == 142.0
    assert results[0].key_code == 10
