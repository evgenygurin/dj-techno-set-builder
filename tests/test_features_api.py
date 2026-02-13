from app.schemas.features import AudioFeaturesList, AudioFeaturesRead


async def test_features_read_schema():
    from datetime import datetime

    data = AudioFeaturesRead(
        track_id=1,
        run_id=1,
        bpm=140.0,
        tempo_confidence=0.9,
        bpm_stability=0.95,
        is_variable_tempo=False,
        lufs_i=-8.0,
        rms_dbfs=-10.0,
        energy_mean=0.4,
        energy_max=0.7,
        key_code=18,
        key_confidence=0.85,
        is_atonal=False,
        created_at=datetime(2026, 1, 1),
    )
    assert data.bpm == 140.0


async def test_features_list_schema():
    lst = AudioFeaturesList(items=[], total=0)
    assert lst.total == 0


# -- API tests --


async def test_get_features_for_track_not_found(client):
    resp = await client.get("/api/v1/tracks/99999/features")
    assert resp.status_code == 404


async def test_list_features_for_track_empty(client):
    track_resp = await client.post(
        "/api/v1/tracks",
        json={"title": "Test Track", "duration_ms": 360000},
    )
    track_id = track_resp.json()["track_id"]
    resp = await client.get(f"/api/v1/tracks/{track_id}/features")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
