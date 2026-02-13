async def test_batch_analyze_rejects_empty(client):
    resp = await client.post(
        "/api/v1/tracks/batch-analyze",
        json={"track_ids": [], "audio_dir": "/tmp"},
    )
    assert resp.status_code == 422


async def test_batch_analyze_endpoint_exists(client):
    resp = await client.post(
        "/api/v1/tracks/batch-analyze",
        json={"track_ids": [999], "audio_dir": "/nonexistent"},
    )
    # Route exists (not 404), may be 404 for track or other error
    assert resp.status_code != 404
