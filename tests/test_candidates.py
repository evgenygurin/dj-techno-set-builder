from app.schemas.candidates import CandidateList, CandidateRead


async def test_candidate_schema():
    from datetime import datetime

    data = CandidateRead(
        from_track_id=1,
        to_track_id=2,
        run_id=1,
        bpm_distance=2.0,
        key_distance=1.0,
        embedding_similarity=None,
        energy_delta=None,
        is_fully_scored=False,
        created_at=datetime(2026, 1, 1),
    )
    assert data.bpm_distance == 2.0


async def test_candidate_list_schema():
    lst = CandidateList(items=[], total=0)
    assert lst.total == 0
