import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.catalog import Track
from app.core.models.features import TrackAudioFeaturesComputed
from app.core.models.harmony import Key
from app.core.models.runs import FeatureExtractionRun


def _make_features(**overrides: object) -> dict:
    """Return minimal valid feature kwargs, with overrides."""
    defaults = {
        "bpm": 128.0,
        "tempo_confidence": 0.95,
        "bpm_stability": 0.98,
        "lufs_i": -8.0,
        "rms_dbfs": -12.0,
        "energy_mean": 0.7,
        "energy_max": 0.95,
        "energy_std": 0.05,
        "key_code": 0,
        "key_confidence": 0.85,
    }
    defaults.update(overrides)
    return defaults


async def _setup(session: AsyncSession) -> tuple:
    """Create common prerequisites."""
    key = Key(key_code=0, pitch_class=0, mode=0, name="Cm")
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([key, track, run])
    await session.flush()
    return track, run


async def test_create_features(session: AsyncSession) -> None:
    track, run = await _setup(session)
    f = TrackAudioFeaturesComputed(
        track_id=track.track_id,
        run_id=run.run_id,
        **_make_features(),
    )
    session.add(f)
    await session.flush()
    assert f.track_id == track.track_id


async def test_bpm_constraint(session: AsyncSession) -> None:
    """bpm must be between 20 and 300."""
    track, run = await _setup(session)
    f = TrackAudioFeaturesComputed(
        track_id=track.track_id,
        run_id=run.run_id,
        **_make_features(bpm=999.0),
    )
    session.add(f)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_energy_mean_constraint(session: AsyncSession) -> None:
    """energy_mean must be between 0 and 1."""
    track, run = await _setup(session)
    f = TrackAudioFeaturesComputed(
        track_id=track.track_id,
        run_id=run.run_id,
        **_make_features(energy_mean=5.0),
    )
    session.add(f)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_key_code_constraint(session: AsyncSession) -> None:
    """key_code must be between 0 and 23."""
    track, run = await _setup(session)
    f = TrackAudioFeaturesComputed(
        track_id=track.track_id,
        run_id=run.run_id,
        **_make_features(key_code=99),
    )
    session.add(f)
    with pytest.raises(IntegrityError):
        await session.flush()
