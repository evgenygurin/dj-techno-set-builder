import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.assets import AudioAsset
from app.core.models.catalog import Track
from app.core.models.runs import FeatureExtractionRun, TransitionRun


async def test_create_feature_extraction_run(session: AsyncSession) -> None:
    run = FeatureExtractionRun(
        pipeline_name="audio_features_v1",
        pipeline_version="1.0.0",
    )
    session.add(run)
    await session.flush()
    assert run.run_id is not None
    assert run.status == "running"


async def test_run_status_constraint(session: AsyncSession) -> None:
    """status must be 'running', 'completed', or 'failed'."""
    run = FeatureExtractionRun(
        pipeline_name="test",
        pipeline_version="1.0.0",
        status="invalid",
    )
    session.add(run)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_transition_run(session: AsyncSession) -> None:
    run = TransitionRun(
        pipeline_name="transition_scoring_v2",
        pipeline_version="2.0.0",
    )
    session.add(run)
    await session.flush()
    assert run.run_id is not None


async def test_create_audio_asset(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    asset = AudioAsset(
        track_id=track.track_id,
        asset_type=0,
        storage_uri="s3://bucket/track_1/full.flac",
        format="flac",
    )
    session.add(asset)
    await session.flush()
    assert asset.asset_id is not None


async def test_audio_asset_type_constraint(session: AsyncSession) -> None:
    """asset_type must be between 0 and 5."""
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    asset = AudioAsset(
        track_id=track.track_id,
        asset_type=99,
        storage_uri="s3://bucket/bad",
        format="mp3",
    )
    session.add(asset)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_audio_asset_with_run(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="demucs_v4", pipeline_version="4.0.0")
    session.add_all([track, run])
    await session.flush()
    asset = AudioAsset(
        track_id=track.track_id,
        asset_type=1,
        storage_uri="s3://bucket/track_1/drums.flac",
        format="flac",
        source_run_id=run.run_id,
    )
    session.add(asset)
    await session.flush()
    assert asset.source_run_id == run.run_id
