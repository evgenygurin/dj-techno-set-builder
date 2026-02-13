async def test_list_sections_for_track_empty(client):
    track_resp = await client.post(
        "/api/v1/tracks",
        json={"title": "Test Track", "duration_ms": 360000},
    )
    track_id = track_resp.json()["track_id"]
    resp = await client.get(f"/api/v1/tracks/{track_id}/sections")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_sections_not_found_track(client):
    resp = await client.get("/api/v1/tracks/99999/sections")
    assert resp.status_code == 404
