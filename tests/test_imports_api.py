async def test_enrich_endpoint_returns_422_without_body(client):
    resp = await client.post("/api/v1/imports/yandex/enrich")
    assert resp.status_code == 422


async def test_list_playlists_endpoint_exists(client):
    resp = await client.get("/api/v1/imports/yandex/playlists")
    # Route exists (not 404) — may fail with connection error (no real YM token)
    assert resp.status_code != 404
