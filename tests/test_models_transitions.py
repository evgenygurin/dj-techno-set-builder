import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.runs import FeatureExtractionRun, TransitionRun
from app.models.timeseries import TrackTimeseriesRef
from app.models.transitions import Transition, TransitionCandidate


async def test_create_timeseries_ref(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([track, run])
    await session.flush()
    ref = TrackTimeseriesRef(
        track_id=track.track_id,
        run_id=run.run_id,
        feature_set="onset_env",
        storage_uri="s3://bucket/track_1/onset_env.npz",
        frame_count=18000,
        hop_length=512,
        sample_rate=22050,
    )
    session.add(ref)
    await session.flush()
    assert ref.track_id == track.track_id


async def test_timeseries_frame_count_positive(session: AsyncSession) -> None:
    """frame_count must be > 0."""
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([track, run])
    await session.flush()
    ref = TrackTimeseriesRef(
        track_id=track.track_id,
        run_id=run.run_id,
        feature_set="bad",
        storage_uri="s3://bad",
        frame_count=0,
        hop_length=512,
        sample_rate=22050,
    )
    session.add(ref)
    with pytest.raises(IntegrityError):
        await session.flush()


async def _make_two_tracks(session: AsyncSession) -> tuple:
    t1 = Track(title="T1", duration_ms=300000)
    t2 = Track(title="T2", duration_ms=300000)
    trun = TransitionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([t1, t2, trun])
    await session.flush()
    return t1, t2, trun


async def test_create_transition_candidate(session: AsyncSession) -> None:
    t1, t2, trun = await _make_two_tracks(session)
    tc = TransitionCandidate(
        from_track_id=t1.track_id,
        to_track_id=t2.track_id,
        run_id=trun.run_id,
        bpm_distance=2.0,
        key_distance=1.0,
    )
    session.add(tc)
    await session.flush()
    assert tc.from_track_id == t1.track_id


async def test_candidate_direction_constraint(session: AsyncSession) -> None:
    """from_track_id must not equal to_track_id."""
    t1, _, trun = await _make_two_tracks(session)
    tc = TransitionCandidate(
        from_track_id=t1.track_id,
        to_track_id=t1.track_id,
        run_id=trun.run_id,
        bpm_distance=0.0,
        key_distance=0.0,
    )
    session.add(tc)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_transition(session: AsyncSession) -> None:
    t1, t2, trun = await _make_two_tracks(session)
    tr = Transition(
        run_id=trun.run_id,
        from_track_id=t1.track_id,
        to_track_id=t2.track_id,
        overlap_ms=16000,
        bpm_distance=1.5,
        energy_step=0.1,
        transition_quality=0.85,
    )
    session.add(tr)
    await session.flush()
    assert tr.transition_id is not None


async def test_transition_quality_constraint(session: AsyncSession) -> None:
    """transition_quality must be between 0 and 1."""
    t1, t2, trun = await _make_two_tracks(session)
    tr = Transition(
        run_id=trun.run_id,
        from_track_id=t1.track_id,
        to_track_id=t2.track_id,
        overlap_ms=16000,
        bpm_distance=1.5,
        energy_step=0.1,
        transition_quality=5.0,
    )
    session.add(tr)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_transition_direction_constraint(session: AsyncSession) -> None:
    """from_track_id must not equal to_track_id."""
    t1, _, trun = await _make_two_tracks(session)
    tr = Transition(
        run_id=trun.run_id,
        from_track_id=t1.track_id,
        to_track_id=t1.track_id,
        overlap_ms=0,
        bpm_distance=0.0,
        energy_step=0.0,
        transition_quality=0.5,
    )
    session.add(tr)
    with pytest.raises(IntegrityError):
        await session.flush()
