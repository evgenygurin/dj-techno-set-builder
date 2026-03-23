import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.catalog import Track
from app.core.models.runs import FeatureExtractionRun
from app.core.models.sections import TrackSection


async def test_create_section(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([track, run])
    await session.flush()
    sec = TrackSection(
        track_id=track.track_id,
        run_id=run.run_id,
        section_type=0,
        section_duration_ms=16000,
        start_ms=0,
        end_ms=16000,
    )
    session.add(sec)
    await session.flush()
    assert sec.section_id is not None


async def test_section_type_constraint(session: AsyncSession) -> None:
    """section_type must be between 0 and 11."""
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([track, run])
    await session.flush()
    sec = TrackSection(
        track_id=track.track_id,
        run_id=run.run_id,
        section_type=99,
        section_duration_ms=16000,
        start_ms=0,
        end_ms=16000,
    )
    session.add(sec)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_section_duration_positive(session: AsyncSession) -> None:
    """section_duration_ms must be > 0."""
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([track, run])
    await session.flush()
    sec = TrackSection(
        track_id=track.track_id,
        run_id=run.run_id,
        section_type=0,
        section_duration_ms=0,
        start_ms=0,
        end_ms=0,
    )
    session.add(sec)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_section_energy_constraint(session: AsyncSession) -> None:
    """section_energy_mean must be between 0 and 1."""
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([track, run])
    await session.flush()
    sec = TrackSection(
        track_id=track.track_id,
        run_id=run.run_id,
        section_type=2,
        section_duration_ms=16000,
        start_ms=0,
        end_ms=16000,
        section_energy_mean=5.0,
    )
    session.add(sec)
    with pytest.raises(IntegrityError):
        await session.flush()
