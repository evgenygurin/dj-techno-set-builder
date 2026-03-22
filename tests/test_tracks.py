from httpx import AsyncClient


async def test_create_track(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/tracks", json={"title": "Acid Rain", "duration_ms": 420000})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Acid Rain"
    assert data["duration_ms"] == 420000
    assert data["track_id"] is not None


async def test_get_track(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/tracks", json={"title": "Warehouse", "duration_ms": 360000}
    )
    track_id = create.json()["track_id"]

    resp = await client.get(f"/api/v1/tracks/{track_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Warehouse"


async def test_get_track_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/tracks/9999")
    assert resp.status_code == 404


async def test_list_tracks(client: AsyncClient) -> None:
    # Count existing tracks before adding new ones (session-scoped engine may have data)
    before = await client.get("/api/v1/tracks")
    existing = before.json()["total"]

    await client.post("/api/v1/tracks", json={"title": "Track A", "duration_ms": 300000})
    await client.post("/api/v1/tracks", json={"title": "Track B", "duration_ms": 310000})

    resp = await client.get("/api/v1/tracks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == existing + 2
    assert len(data["items"]) >= 2


async def test_list_tracks_search(client: AsyncClient) -> None:
    # Use a unique prefix to avoid matching pre-existing tracks
    await client.post("/api/v1/tracks", json={"title": "ZZUniq Dark Acid", "duration_ms": 300000})
    await client.post("/api/v1/tracks", json={"title": "ZZUniq Deep Bass", "duration_ms": 310000})

    resp = await client.get("/api/v1/tracks", params={"search": "ZZUniq Dark"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "ZZUniq Dark Acid"


async def test_update_track(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/tracks", json={"title": "Old Title", "duration_ms": 300000}
    )
    track_id = create.json()["track_id"]

    resp = await client.patch(f"/api/v1/tracks/{track_id}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"
    assert resp.json()["duration_ms"] == 300000  # unchanged


async def test_delete_track(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/tracks", json={"title": "To Delete", "duration_ms": 300000}
    )
    track_id = create.json()["track_id"]

    resp = await client.delete(f"/api/v1/tracks/{track_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/tracks/{track_id}")
    assert resp.status_code == 404
