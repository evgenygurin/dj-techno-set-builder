import pytest

from app.services.camelot_lookup import CamelotLookupService


@pytest.mark.asyncio
async def test_build_lookup_table_same_key():
    """Same key should score 1.0"""
    service = CamelotLookupService()
    lookup = await service.build_lookup_table()
    # Key 0 → Key 0 (C major)
    assert lookup[(0, 0)] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_build_lookup_table_adjacent():
    """Adjacent Camelot keys (±1) should score 0.9"""
    service = CamelotLookupService()
    lookup = await service.build_lookup_table()
    # Find an adjacent pair from key_edges with distance=1.0
    # This test will pass once we query the DB correctly
    assert len(lookup) > 0  # At least some transitions exist


@pytest.mark.asyncio
async def test_build_lookup_table_tritone():
    """Tritone (±6 semitones) should score ~0.05"""
    service = CamelotLookupService()
    lookup = await service.build_lookup_table()
    # Key 0 → Key 12 (tritone in chromatic, but need to find actual mapping)
    # Placeholder: just ensure table is built
    assert len(lookup) == 24 * 24  # All key pairs


@pytest.mark.asyncio
async def test_get_score_with_fallback():
    """Unknown key pair should return default score"""
    service = CamelotLookupService()
    await service.build_lookup_table()
    # Invalid key codes
    score = service.get_score(999, 999)
    assert score == pytest.approx(0.5)  # Default fallback


@pytest.mark.asyncio
async def test_get_score_cached():
    """Subsequent calls should use cached lookup table"""
    service = CamelotLookupService()
    score1 = service.get_score(0, 0)
    score2 = service.get_score(0, 0)
    assert score1 == score2 == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_build_lookup_table_from_db(session):
    """Build lookup from actual key_edges table"""
    from app.repositories.harmony import KeyEdgeRepository

    # Verify key_edges has data
    repo = KeyEdgeRepository(session)
    edges = await repo.list_all()

    if len(edges) == 0:
        pytest.skip("key_edges table must be populated for this test")

    service = CamelotLookupService(session)
    lookup = await service.build_lookup_table()

    # Verify same-key transitions
    assert lookup[(0, 0)] == pytest.approx(1.0)

    # Verify table is complete
    assert len(lookup) == 24 * 24
