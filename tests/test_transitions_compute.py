import pytest

essentia = pytest.importorskip("essentia")


async def test_compute_transition_missing_features(client):
    """Computing transition without features should return 422."""
    track1 = await client.post("/api/v1/tracks", json={"title": "A", "duration_ms": 300000})
    track2 = await client.post("/api/v1/tracks", json={"title": "B", "duration_ms": 300000})

    # Create a transition run
    run = await client.post(
        "/api/v1/runs/transitions",
        json={"pipeline_name": "scorer-v1", "pipeline_version": "1.0.0"},
    )
    run_id = run.json()["run_id"]

    resp = await client.post(
        "/api/v1/transitions/compute",
        json={
            "from_track_id": track1.json()["track_id"],
            "to_track_id": track2.json()["track_id"],
            "run_id": run_id,
        },
    )
    # Should fail — no features to score
    assert resp.status_code == 422
