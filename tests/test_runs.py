from app.schemas.runs import FeatureRunCreate, FeatureRunList, FeatureRunRead


async def test_feature_run_create_schema():
    data = FeatureRunCreate(pipeline_name="essentia-v1", pipeline_version="2.1b6")
    assert data.pipeline_name == "essentia-v1"


async def test_feature_run_create_with_params():
    data = FeatureRunCreate(
        pipeline_name="essentia-v1",
        pipeline_version="2.1b6",
        parameters={"target_sr": 44100},
        code_ref="abc123",
    )
    assert data.parameters == {"target_sr": 44100}


async def test_feature_run_read_schema():
    from datetime import datetime

    data = FeatureRunRead(
        run_id=1,
        pipeline_name="essentia-v1",
        pipeline_version="2.1b6",
        parameters=None,
        code_ref=None,
        status="running",
        started_at=datetime(2026, 1, 1),
        completed_at=None,
        created_at=datetime(2026, 1, 1),
    )
    assert data.run_id == 1
    assert data.status == "running"


async def test_feature_run_list_schema():
    lst = FeatureRunList(items=[], total=0)
    assert lst.total == 0


# -- Repository tests (use session fixture from conftest.py) --


async def test_create_feature_run(session):
    from app.repositories.runs import FeatureRunRepository

    repo = FeatureRunRepository(session)
    run = await repo.create(
        pipeline_name="essentia-v1",
        pipeline_version="2.1b6",
        status="running",
    )
    await session.flush()
    assert run.run_id is not None
    assert run.status == "running"


async def test_complete_feature_run(session):
    from app.repositories.runs import FeatureRunRepository

    repo = FeatureRunRepository(session)
    run = await repo.create(
        pipeline_name="essentia-v1",
        pipeline_version="2.1b6",
        status="running",
    )
    await session.flush()
    updated = await repo.mark_completed(run.run_id)
    assert updated.status == "completed"
    assert updated.completed_at is not None


async def test_fail_feature_run(session):
    from app.repositories.runs import FeatureRunRepository

    repo = FeatureRunRepository(session)
    run = await repo.create(
        pipeline_name="essentia-v1",
        pipeline_version="2.1b6",
        status="running",
    )
    await session.flush()
    updated = await repo.mark_failed(run.run_id)
    assert updated.status == "failed"


# -- API tests (use client fixture from conftest.py) --


async def test_create_feature_run_api(client):
    resp = await client.post(
        "/api/v1/runs/features",
        json={
            "pipeline_name": "essentia-v1",
            "pipeline_version": "2.1b6",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pipeline_name"] == "essentia-v1"
    assert body["status"] == "running"
    assert body["run_id"] is not None


async def test_get_feature_run_api(client):
    create_resp = await client.post(
        "/api/v1/runs/features",
        json={
            "pipeline_name": "essentia-v1",
            "pipeline_version": "2.1b6",
        },
    )
    run_id = create_resp.json()["run_id"]
    resp = await client.get(f"/api/v1/runs/features/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id


async def test_get_feature_run_not_found(client):
    resp = await client.get("/api/v1/runs/features/99999")
    assert resp.status_code == 404


async def test_list_feature_runs_api(client):
    resp = await client.get("/api/v1/runs/features")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


async def test_create_transition_run_api(client):
    resp = await client.post(
        "/api/v1/runs/transitions",
        json={
            "pipeline_name": "scorer-v1",
            "pipeline_version": "1.0.0",
            "weights": {"bpm": 0.4, "key": 0.25},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pipeline_name"] == "scorer-v1"
    assert body["weights"]["bpm"] == 0.4
