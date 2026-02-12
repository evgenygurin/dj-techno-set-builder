import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.sets import DjSet, DjSetConstraint, DjSetFeedback, DjSetItem, DjSetVersion


async def test_create_set(session: AsyncSession) -> None:
    s = DjSet(name="Friday Night Techno", target_duration_ms=3600000)
    session.add(s)
    await session.flush()
    assert s.set_id is not None


async def test_set_duration_constraint(session: AsyncSession) -> None:
    """target_duration_ms must be > 0."""
    s = DjSet(name="Bad", target_duration_ms=0)
    session.add(s)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_set_version(session: AsyncSession) -> None:
    s = DjSet(name="Test")
    session.add(s)
    await session.flush()
    v = DjSetVersion(set_id=s.set_id, version_label="v1", score=0.85)
    session.add(v)
    await session.flush()
    assert v.set_version_id is not None


async def test_create_set_constraint(session: AsyncSession) -> None:
    s = DjSet(name="Test")
    session.add(s)
    await session.flush()
    v = DjSetVersion(set_id=s.set_id, version_label="v1")
    session.add(v)
    await session.flush()
    c = DjSetConstraint(
        set_version_id=v.set_version_id,
        constraint_type="max_bpm_jump",
        value={"max": 6},
    )
    session.add(c)
    await session.flush()
    assert c.constraint_id is not None


async def test_create_set_item(session: AsyncSession) -> None:
    s = DjSet(name="Test")
    track = Track(title="T", duration_ms=300000)
    session.add_all([s, track])
    await session.flush()
    v = DjSetVersion(set_id=s.set_id)
    session.add(v)
    await session.flush()
    item = DjSetItem(
        set_version_id=v.set_version_id,
        sort_index=0,
        track_id=track.track_id,
    )
    session.add(item)
    await session.flush()
    assert item.set_item_id is not None


async def test_set_item_sort_unique(session: AsyncSession) -> None:
    """(set_version_id, sort_index) must be unique."""
    s = DjSet(name="Test")
    track = Track(title="T", duration_ms=300000)
    session.add_all([s, track])
    await session.flush()
    v = DjSetVersion(set_id=s.set_id)
    session.add(v)
    await session.flush()
    i1 = DjSetItem(set_version_id=v.set_version_id, sort_index=0, track_id=track.track_id)
    i2 = DjSetItem(set_version_id=v.set_version_id, sort_index=0, track_id=track.track_id)
    session.add_all([i1, i2])
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_set_feedback(session: AsyncSession) -> None:
    s = DjSet(name="Test")
    session.add(s)
    await session.flush()
    v = DjSetVersion(set_id=s.set_id)
    session.add(v)
    await session.flush()
    fb = DjSetFeedback(
        set_version_id=v.set_version_id,
        rating=4,
        feedback_type="manual",
        notes="Great energy arc",
    )
    session.add(fb)
    await session.flush()
    assert fb.feedback_id is not None


async def test_feedback_rating_constraint(session: AsyncSession) -> None:
    """rating must be between -1 and 5."""
    s = DjSet(name="Test")
    session.add(s)
    await session.flush()
    v = DjSetVersion(set_id=s.set_id)
    session.add(v)
    await session.flush()
    fb = DjSetFeedback(set_version_id=v.set_version_id, rating=99)
    session.add(fb)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_feedback_type_constraint(session: AsyncSession) -> None:
    """feedback_type must be 'manual', 'live_crowd', or 'a_b_test'."""
    s = DjSet(name="Test")
    session.add(s)
    await session.flush()
    v = DjSetVersion(set_id=s.set_id)
    session.add(v)
    await session.flush()
    fb = DjSetFeedback(set_version_id=v.set_version_id, rating=3, feedback_type="invalid")
    session.add(fb)
    with pytest.raises(IntegrityError):
        await session.flush()
