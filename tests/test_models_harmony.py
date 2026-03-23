import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.harmony import Key, KeyEdge


async def test_create_key(session: AsyncSession) -> None:
    k = Key(key_code=0, pitch_class=0, mode=0, name="Cm", camelot="5A")
    session.add(k)
    await session.flush()
    assert k.key_code == 0


async def test_key_code_constraint(session: AsyncSession) -> None:
    """key_code must be between 0 and 23."""
    k = Key(key_code=99, pitch_class=0, mode=0, name="Bad")
    session.add(k)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_key_mode_constraint(session: AsyncSession) -> None:
    """mode must be 0 or 1."""
    k = Key(key_code=0, pitch_class=0, mode=5, name="Bad")
    session.add(k)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_key_deterministic_constraint(session: AsyncSession) -> None:
    """key_code must equal pitch_class * 2 + mode."""
    k = Key(key_code=0, pitch_class=1, mode=0, name="Bad")
    session.add(k)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_key_edge(session: AsyncSession) -> None:
    k1 = Key(key_code=0, pitch_class=0, mode=0, name="Cm", camelot="5A")
    k2 = Key(key_code=1, pitch_class=0, mode=1, name="C", camelot="8B")
    session.add_all([k1, k2])
    await session.flush()
    edge = KeyEdge(
        from_key_code=0,
        to_key_code=1,
        distance=1.0,
        weight=0.8,
        rule="relative_major_minor",
    )
    session.add(edge)
    await session.flush()
    assert edge.from_key_code == 0


async def test_key_edge_distance_constraint(session: AsyncSession) -> None:
    """distance must be >= 0."""
    k1 = Key(key_code=0, pitch_class=0, mode=0, name="Cm")
    k2 = Key(key_code=1, pitch_class=0, mode=1, name="C")
    session.add_all([k1, k2])
    await session.flush()
    edge = KeyEdge(from_key_code=0, to_key_code=1, distance=-1.0, weight=0.5)
    session.add(edge)
    with pytest.raises(IntegrityError):
        await session.flush()
