# Audio Analysis Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate the existing `app/utils/audio/` layer into the full application — schemas, repos, services, and REST endpoints for feature extraction runs, audio features, sections, analysis triggering, transition scoring, and transition computation.

**Architecture:** The utils layer (pure functions returning frozen dataclasses) is already built. This plan bridges it to the Router→Service→Repository stack. Runs are versioned containers for features/transitions. Analysis endpoints trigger CPU-bound work via `asyncio.to_thread`. Transition scoring uses a two-stage pipeline: candidates (pre-filter) → full scoring.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, pytest-asyncio, httpx

---

## Task 1: FeatureExtractionRun — Schemas

**Files:**
- Create: `app/schemas/runs.py`
- Test: `tests/test_runs.py`

**Step 1: Write the failing test**

```python
# tests/test_runs.py
from app.schemas.runs import FeatureRunCreate, FeatureRunRead, FeatureRunList

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runs.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# app/schemas/runs.py
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema

class FeatureRunCreate(BaseSchema):
    pipeline_name: str = Field(min_length=1, max_length=200)
    pipeline_version: str = Field(min_length=1, max_length=50)
    parameters: dict[str, Any] | None = None
    code_ref: str | None = Field(default=None, max_length=200)

class FeatureRunRead(BaseSchema):
    run_id: int
    pipeline_name: str
    pipeline_version: str
    parameters: dict[str, Any] | None
    code_ref: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime

class FeatureRunList(BaseSchema):
    items: list[FeatureRunRead]
    total: int

class TransitionRunCreate(BaseSchema):
    pipeline_name: str = Field(min_length=1, max_length=200)
    pipeline_version: str = Field(min_length=1, max_length=50)
    weights: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None

class TransitionRunRead(BaseSchema):
    run_id: int
    pipeline_name: str
    pipeline_version: str
    weights: dict[str, Any] | None
    constraints: dict[str, Any] | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime

class TransitionRunList(BaseSchema):
    items: list[TransitionRunRead]
    total: int
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/schemas/runs.py tests/test_runs.py
git commit -m "feat(schemas): add FeatureRun and TransitionRun schemas"
```

---

## Task 2: FeatureExtractionRun — Repository + Service

**Files:**
- Create: `app/repositories/runs.py`
- Create: `app/services/runs.py`
- Modify: `tests/test_runs.py`

**Step 1: Write the failing test**

Append to `tests/test_runs.py`:

```python
from app.models import Base

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runs.py::test_create_feature_run -v`
Expected: FAIL with ImportError

**Step 3: Write repository**

```python
# app/repositories/runs.py
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.runs import FeatureExtractionRun, TransitionRun
from app.repositories.base import BaseRepository

class FeatureRunRepository(BaseRepository[FeatureExtractionRun]):
    model = FeatureExtractionRun

    async def mark_completed(self, run_id: int) -> FeatureExtractionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"FeatureExtractionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )

    async def mark_failed(self, run_id: int) -> FeatureExtractionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"FeatureExtractionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )

class TransitionRunRepository(BaseRepository[TransitionRun]):
    model = TransitionRun

    async def mark_completed(self, run_id: int) -> TransitionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"TransitionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )

    async def mark_failed(self, run_id: int) -> TransitionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"TransitionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )
```

**Step 4: Write service**

```python
# app/services/runs.py
from app.errors import NotFoundError
from app.repositories.runs import FeatureRunRepository, TransitionRunRepository
from app.schemas.runs import (
    FeatureRunCreate,
    FeatureRunList,
    FeatureRunRead,
    TransitionRunCreate,
    TransitionRunList,
    TransitionRunRead,
)
from app.services.base import BaseService

class FeatureRunService(BaseService):
    def __init__(self, repo: FeatureRunRepository) -> None:
        super().__init__()
        self.repo = repo

    async def create(self, data: FeatureRunCreate) -> FeatureRunRead:
        run = await self.repo.create(**data.model_dump())
        return FeatureRunRead.model_validate(run)

    async def get(self, run_id: int) -> FeatureRunRead:
        run = await self.repo.get_by_id(run_id)
        if not run:
            raise NotFoundError("FeatureExtractionRun", run_id=run_id)
        return FeatureRunRead.model_validate(run)

    async def list(self, *, offset: int = 0, limit: int = 50) -> FeatureRunList:
        items, total = await self.repo.list(offset=offset, limit=limit)
        return FeatureRunList(
            items=[FeatureRunRead.model_validate(r) for r in items],
            total=total,
        )

class TransitionRunService(BaseService):
    def __init__(self, repo: TransitionRunRepository) -> None:
        super().__init__()
        self.repo = repo

    async def create(self, data: TransitionRunCreate) -> TransitionRunRead:
        run = await self.repo.create(**data.model_dump())
        return TransitionRunRead.model_validate(run)

    async def get(self, run_id: int) -> TransitionRunRead:
        run = await self.repo.get_by_id(run_id)
        if not run:
            raise NotFoundError("TransitionRun", run_id=run_id)
        return TransitionRunRead.model_validate(run)

    async def list(self, *, offset: int = 0, limit: int = 50) -> TransitionRunList:
        items, total = await self.repo.list(offset=offset, limit=limit)
        return TransitionRunList(
            items=[TransitionRunRead.model_validate(r) for r in items],
            total=total,
        )
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_runs.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/repositories/runs.py app/services/runs.py tests/test_runs.py
git commit -m "feat(runs): add repos and services for feature/transition runs"
```

---

## Task 3: Runs — Router + API tests

**Files:**
- Create: `app/routers/v1/runs.py`
- Modify: `app/routers/v1/__init__.py` — register router
- Modify: `tests/test_runs.py` — add API tests

**Step 1: Write the failing API tests**

Append to `tests/test_runs.py`:

```python
# -- API tests (use client fixture from conftest.py) --

async def test_create_feature_run_api(client):
    resp = await client.post("/api/v1/runs/features", json={
        "pipeline_name": "essentia-v1",
        "pipeline_version": "2.1b6",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["pipeline_name"] == "essentia-v1"
    assert body["status"] == "running"
    assert body["run_id"] is not None

async def test_get_feature_run_api(client):
    create_resp = await client.post("/api/v1/runs/features", json={
        "pipeline_name": "essentia-v1",
        "pipeline_version": "2.1b6",
    })
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
    resp = await client.post("/api/v1/runs/transitions", json={
        "pipeline_name": "scorer-v1",
        "pipeline_version": "1.0.0",
        "weights": {"bpm": 0.4, "key": 0.25},
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["pipeline_name"] == "scorer-v1"
    assert body["weights"]["bpm"] == 0.4
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runs.py::test_create_feature_run_api -v`
Expected: FAIL with 404 (route not registered)

**Step 3: Write the router**

```python
# app/routers/v1/runs.py
from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.runs import FeatureRunRepository, TransitionRunRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.runs import (
    FeatureRunCreate,
    FeatureRunList,
    FeatureRunRead,
    TransitionRunCreate,
    TransitionRunList,
    TransitionRunRead,
)
from app.services.runs import FeatureRunService, TransitionRunService

router = APIRouter(prefix="/runs", tags=["runs"])

def _feature_svc(db: DbSession) -> FeatureRunService:
    return FeatureRunService(FeatureRunRepository(db))

def _transition_svc(db: DbSession) -> TransitionRunService:
    return TransitionRunService(TransitionRunRepository(db))

# -- Feature extraction runs --

@router.post(
    "/features",
    response_model=FeatureRunRead,
    status_code=201,
    summary="Create feature extraction run",
    description="Start a new feature extraction run to group analysis results.",
    response_description="The created run",
    operation_id="create_feature_run",
)
async def create_feature_run(data: FeatureRunCreate, db: DbSession) -> FeatureRunRead:
    result = await _feature_svc(db).create(data)
    await db.commit()
    return result

@router.get(
    "/features",
    response_model=FeatureRunList,
    summary="List feature extraction runs",
    description="Retrieve a paginated list of feature extraction runs.",
    response_description="Paginated list of runs",
    operation_id="list_feature_runs",
)
async def list_feature_runs(
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> FeatureRunList:
    return await _feature_svc(db).list(offset=offset, limit=limit)

@router.get(
    "/features/{run_id}",
    response_model=FeatureRunRead,
    summary="Get feature extraction run",
    description="Retrieve a single feature extraction run by ID.",
    response_description="The run details",
    responses=RESPONSES_GET,
    operation_id="get_feature_run",
)
async def get_feature_run(run_id: int, db: DbSession) -> FeatureRunRead:
    return await _feature_svc(db).get(run_id)

# -- Transition runs --

@router.post(
    "/transitions",
    response_model=TransitionRunRead,
    status_code=201,
    summary="Create transition run",
    description="Start a new transition scoring run with given weights and constraints.",
    response_description="The created run",
    operation_id="create_transition_run",
)
async def create_transition_run(data: TransitionRunCreate, db: DbSession) -> TransitionRunRead:
    result = await _transition_svc(db).create(data)
    await db.commit()
    return result

@router.get(
    "/transitions",
    response_model=TransitionRunList,
    summary="List transition runs",
    description="Retrieve a paginated list of transition scoring runs.",
    response_description="Paginated list of runs",
    operation_id="list_transition_runs",
)
async def list_transition_runs(
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> TransitionRunList:
    return await _transition_svc(db).list(offset=offset, limit=limit)

@router.get(
    "/transitions/{run_id}",
    response_model=TransitionRunRead,
    summary="Get transition run",
    description="Retrieve a single transition scoring run by ID.",
    response_description="The run details",
    responses=RESPONSES_GET,
    operation_id="get_transition_run",
)
async def get_transition_run(run_id: int, db: DbSession) -> TransitionRunRead:
    return await _transition_svc(db).get(run_id)
```

**Step 4: Register the router**

In `app/routers/v1/__init__.py`, add import and `include_router`:

```python
from app.routers.v1 import (
    ...
    runs,         # add this
    ...
)
v1_router.include_router(runs.router)   # add this
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_runs.py -v`
Expected: PASS

**Step 6: Lint + commit**

```bash
uv run ruff check app/schemas/runs.py app/repositories/runs.py app/services/runs.py app/routers/v1/runs.py --fix
git add app/schemas/runs.py app/repositories/runs.py app/services/runs.py app/routers/v1/runs.py app/routers/v1/__init__.py tests/test_runs.py
git commit -m "feat(api): add /runs/features and /runs/transitions endpoints"
```

---

## Task 4: AudioFeatures — Read Schemas

**Files:**
- Create: `app/schemas/features.py`
- Create: `tests/test_features_api.py`

**Step 1: Write the failing test**

```python
# tests/test_features_api.py
from app.schemas.features import AudioFeaturesRead, AudioFeaturesList

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
        transition_quality=None,
        created_at=datetime(2026, 1, 1),
    )
    assert data.bpm == 140.0

async def test_features_list_schema():
    lst = AudioFeaturesList(items=[], total=0)
    assert lst.total == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features_api.py -v`
Expected: FAIL with ImportError

**Step 3: Write schemas**

```python
# app/schemas/features.py
from datetime import datetime

from app.schemas.base import BaseSchema

class AudioFeaturesRead(BaseSchema):
    track_id: int
    run_id: int
    # Tempo
    bpm: float
    tempo_confidence: float
    bpm_stability: float
    is_variable_tempo: bool
    # Loudness
    lufs_i: float
    lufs_s_mean: float | None = None
    lufs_m_max: float | None = None
    rms_dbfs: float
    true_peak_db: float | None = None
    crest_factor_db: float | None = None
    lra_lu: float | None = None
    # Energy
    energy_mean: float
    energy_max: float
    energy_std: float | None = None
    energy_slope_mean: float | None = None
    # Band energies
    sub_energy: float | None = None
    low_energy: float | None = None
    lowmid_energy: float | None = None
    mid_energy: float | None = None
    highmid_energy: float | None = None
    high_energy: float | None = None
    low_high_ratio: float | None = None
    sub_lowmid_ratio: float | None = None
    # Spectral
    centroid_mean_hz: float | None = None
    rolloff_85_hz: float | None = None
    rolloff_95_hz: float | None = None
    flatness_mean: float | None = None
    flux_mean: float | None = None
    flux_std: float | None = None
    contrast_mean_db: float | None = None
    # Tonal
    key_code: int
    key_confidence: float
    is_atonal: bool
    # Rhythm (optional, Phase 2)
    hp_ratio: float | None = None
    onset_rate_mean: float | None = None
    onset_rate_max: float | None = None
    pulse_clarity: float | None = None
    kick_prominence: float | None = None
    # Meta
    created_at: datetime

class AudioFeaturesList(BaseSchema):
    items: list[AudioFeaturesRead]
    total: int
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_features_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/schemas/features.py tests/test_features_api.py
git commit -m "feat(schemas): add AudioFeaturesRead and AudioFeaturesList"
```

---

## Task 5: AudioFeatures — Repository query + Service + Router

**Files:**
- Modify: `app/repositories/audio_features.py` — add `get_by_track` and `list_by_track`
- Create: `app/services/features.py`
- Create: `app/routers/v1/features.py`
- Modify: `app/routers/v1/__init__.py` — register router
- Modify: `tests/test_features_api.py` — add API tests

**Step 1: Write the failing tests**

Append to `tests/test_features_api.py`:

```python
async def test_get_features_for_track_not_found(client):
    resp = await client.get("/api/v1/tracks/99999/features")
    assert resp.status_code == 404

async def test_list_features_for_track_empty(client):
    # Create a track first
    track_resp = await client.post("/api/v1/tracks", json={
        "title": "Test Track", "duration_ms": 360000,
    })
    track_id = track_resp.json()["track_id"]
    resp = await client.get(f"/api/v1/tracks/{track_id}/features")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features_api.py::test_list_features_for_track_empty -v`
Expected: FAIL with 404 (route not found) or ImportError

**Step 3: Add repository queries**

Append to `app/repositories/audio_features.py`:

```python
async def get_by_track(
    self, track_id: int, run_id: int | None = None,
) -> TrackAudioFeaturesComputed | None:
    """Get features for a track, optionally filtered by run."""
    from sqlalchemy import select
    stmt = select(self.model).where(self.model.track_id == track_id)
    if run_id is not None:
        stmt = stmt.where(self.model.run_id == run_id)
    stmt = stmt.order_by(self.model.created_at.desc()).limit(1)
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none()

async def list_by_track(
    self, track_id: int, *, offset: int = 0, limit: int = 50,
) -> tuple[list[TrackAudioFeaturesComputed], int]:
    from typing import Any
    filters: list[Any] = [self.model.track_id == track_id]
    return await self.list(offset=offset, limit=limit, filters=filters)
```

**Step 4: Write service**

```python
# app/services/features.py
from app.errors import NotFoundError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.schemas.features import AudioFeaturesList, AudioFeaturesRead
from app.services.base import BaseService

class AudioFeaturesService(BaseService):
    def __init__(
        self, features_repo: AudioFeaturesRepository, track_repo: TrackRepository,
    ) -> None:
        super().__init__()
        self.features_repo = features_repo
        self.track_repo = track_repo

    async def get_latest(self, track_id: int) -> AudioFeaturesRead:
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        features = await self.features_repo.get_by_track(track_id)
        if not features:
            raise NotFoundError("AudioFeatures", track_id=track_id)
        return AudioFeaturesRead.model_validate(features)

    async def list_for_track(
        self, track_id: int, *, offset: int = 0, limit: int = 50,
    ) -> AudioFeaturesList:
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        items, total = await self.features_repo.list_by_track(
            track_id, offset=offset, limit=limit,
        )
        return AudioFeaturesList(
            items=[AudioFeaturesRead.model_validate(f) for f in items],
            total=total,
        )
```

**Step 5: Write router (nested under /tracks)**

```python
# app/routers/v1/features.py
from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.features import AudioFeaturesList, AudioFeaturesRead
from app.services.features import AudioFeaturesService

router = APIRouter(prefix="/tracks", tags=["features"])

def _service(db: DbSession) -> AudioFeaturesService:
    return AudioFeaturesService(AudioFeaturesRepository(db), TrackRepository(db))

@router.get(
    "/{track_id}/features",
    response_model=AudioFeaturesList,
    summary="List audio features for track",
    description="Retrieve all computed audio features for a track across all runs.",
    response_description="Paginated list of audio features",
    responses=RESPONSES_GET,
    operation_id="list_track_features",
)
async def list_track_features(
    track_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> AudioFeaturesList:
    return await _service(db).list_for_track(track_id, offset=offset, limit=limit)

@router.get(
    "/{track_id}/features/latest",
    response_model=AudioFeaturesRead,
    summary="Get latest audio features for track",
    description="Retrieve the most recent audio features computed for a track.",
    response_description="The latest audio features",
    responses=RESPONSES_GET,
    operation_id="get_track_features_latest",
)
async def get_track_features_latest(track_id: int, db: DbSession) -> AudioFeaturesRead:
    return await _service(db).get_latest(track_id)
```

**Step 6: Register in `app/routers/v1/__init__.py`**

Add `features` import and `v1_router.include_router(features.router)`.

**Step 7: Run tests**

Run: `uv run pytest tests/test_features_api.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add app/repositories/audio_features.py app/services/features.py app/routers/v1/features.py app/routers/v1/__init__.py tests/test_features_api.py
git commit -m "feat(api): add GET /tracks/{id}/features endpoints"
```

---

## Task 6: Sections — Schemas, Service, Router

**Files:**
- Create: `app/schemas/sections.py`
- Create: `app/services/sections.py`
- Create: `app/routers/v1/sections.py`
- Modify: `app/routers/v1/__init__.py`
- Create: `tests/test_sections_api.py`

**Step 1: Write the failing tests**

```python
# tests/test_sections_api.py

async def test_list_sections_for_track_empty(client):
    track_resp = await client.post("/api/v1/tracks", json={
        "title": "Test Track", "duration_ms": 360000,
    })
    track_id = track_resp.json()["track_id"]
    resp = await client.get(f"/api/v1/tracks/{track_id}/sections")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0

async def test_list_sections_not_found_track(client):
    resp = await client.get("/api/v1/tracks/99999/sections")
    assert resp.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sections_api.py -v`
Expected: FAIL

**Step 3: Write schemas**

```python
# app/schemas/sections.py
from datetime import datetime

from app.schemas.base import BaseSchema

class SectionRead(BaseSchema):
    section_id: int
    track_id: int
    run_id: int
    start_ms: int
    end_ms: int
    section_type: int
    section_duration_ms: int
    section_energy_mean: float | None = None
    section_energy_max: float | None = None
    section_energy_slope: float | None = None
    section_centroid_hz: float | None = None
    section_flux: float | None = None
    section_onset_rate: float | None = None
    section_pulse_clarity: float | None = None
    boundary_confidence: float | None = None
    created_at: datetime

class SectionList(BaseSchema):
    items: list[SectionRead]
    total: int
```

**Step 4: Add `list_by_track` to SectionsRepository**

In `app/repositories/sections.py`:

```python
async def list_by_track(
    self, track_id: int, *, offset: int = 0, limit: int = 50,
) -> tuple[list[TrackSection], int]:
    from typing import Any
    filters: list[Any] = [self.model.track_id == track_id]
    return await self.list(offset=offset, limit=limit, filters=filters)
```

**Step 5: Write service**

```python
# app/services/sections.py
from app.errors import NotFoundError
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.schemas.sections import SectionList, SectionRead
from app.services.base import BaseService

class SectionsService(BaseService):
    def __init__(
        self, sections_repo: SectionsRepository, track_repo: TrackRepository,
    ) -> None:
        super().__init__()
        self.sections_repo = sections_repo
        self.track_repo = track_repo

    async def list_for_track(
        self, track_id: int, *, offset: int = 0, limit: int = 50,
    ) -> SectionList:
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)
        items, total = await self.sections_repo.list_by_track(
            track_id, offset=offset, limit=limit,
        )
        return SectionList(
            items=[SectionRead.model_validate(s) for s in items],
            total=total,
        )
```

**Step 6: Write router (nested under /tracks)**

```python
# app/routers/v1/sections.py
from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.sections import SectionList
from app.services.sections import SectionsService

router = APIRouter(prefix="/tracks", tags=["sections"])

def _service(db: DbSession) -> SectionsService:
    return SectionsService(SectionsRepository(db), TrackRepository(db))

@router.get(
    "/{track_id}/sections",
    response_model=SectionList,
    summary="List sections for track",
    description="Retrieve structural sections detected for a track.",
    response_description="Paginated list of sections",
    responses=RESPONSES_GET,
    operation_id="list_track_sections",
)
async def list_track_sections(
    track_id: int,
    db: DbSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> SectionList:
    return await _service(db).list_for_track(track_id, offset=offset, limit=limit)
```

**Step 7: Register in `app/routers/v1/__init__.py`**

**Step 8: Run tests**

Run: `uv run pytest tests/test_sections_api.py -v`
Expected: PASS

**Step 9: Commit**

```bash
git add app/schemas/sections.py app/repositories/sections.py app/services/sections.py app/routers/v1/sections.py app/routers/v1/__init__.py tests/test_sections_api.py
git commit -m "feat(api): add GET /tracks/{id}/sections endpoint"
```

---

## Task 7: Analysis Trigger — POST /tracks/{id}/analyze

This is the key integration endpoint: creates a run, calls TrackAnalysisService, returns features.

**Files:**
- Create: `app/schemas/analysis.py`
- Create: `app/services/analysis.py`
- Create: `app/routers/v1/analysis.py`
- Modify: `app/routers/v1/__init__.py`
- Create: `tests/test_analysis_api.py`

**Step 1: Write schemas**

```python
# app/schemas/analysis.py
from app.schemas.base import BaseSchema

class AnalysisRequest(BaseSchema):
    audio_path: str
    pipeline_name: str = "essentia-v1"
    pipeline_version: str = "2.1b6"
    full_analysis: bool = False  # True = Phase 2 (beats + sections)

class AnalysisResponse(BaseSchema):
    track_id: int
    run_id: int
    status: str  # "completed" or "failed"
    bpm: float | None = None
    key_code: int | None = None
    sections_count: int = 0
```

**Step 2: Write the failing tests**

```python
# tests/test_analysis_api.py
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.utils.audio import (  # noqa: E402
    BandEnergyResult,
    BpmResult,
    KeyResult,
    LoudnessResult,
    SpectralResult,
    TrackFeatures,
)

def _fake_features() -> TrackFeatures:
    return TrackFeatures(
        bpm=BpmResult(bpm=140.0, confidence=0.9, stability=0.95, is_variable=False),
        key=KeyResult(
            key="A", scale="minor", key_code=18, confidence=0.85,
            is_atonal=False, chroma=np.zeros(12, dtype=np.float32),
        ),
        loudness=LoudnessResult(
            lufs_i=-8.0, lufs_s_mean=-7.5, lufs_m_max=-5.0,
            rms_dbfs=-10.0, true_peak_db=-1.0, crest_factor_db=9.0, lra_lu=6.0,
        ),
        band_energy=BandEnergyResult(
            sub=0.3, low=0.7, low_mid=0.5, mid=0.4,
            high_mid=0.2, high=0.1, low_high_ratio=7.0, sub_lowmid_ratio=0.6,
        ),
        spectral=SpectralResult(
            centroid_mean_hz=1500.0, rolloff_85_hz=5000.0, rolloff_95_hz=8000.0,
            flatness_mean=0.3, flux_mean=0.5, flux_std=0.1, contrast_mean_db=20.0,
        ),
    )

@patch("app.services.track_analysis.extract_all_features")
async def test_analyze_track_endpoint(mock_extract, client):
    mock_extract.return_value = _fake_features()

    # Create a track first
    track_resp = await client.post("/api/v1/tracks", json={
        "title": "Test Track", "duration_ms": 360000,
    })
    track_id = track_resp.json()["track_id"]

    # Trigger analysis
    resp = await client.post(f"/api/v1/tracks/{track_id}/analyze", json={
        "audio_path": "/fake/path.wav",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["track_id"] == track_id
    assert body["status"] == "completed"
    assert body["bpm"] == 140.0
    assert body["key_code"] == 18

@patch("app.services.track_analysis.extract_all_features")
async def test_analyze_track_not_found(mock_extract, client):
    resp = await client.post("/api/v1/tracks/99999/analyze", json={
        "audio_path": "/fake/path.wav",
    })
    assert resp.status_code == 404
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_analysis_api.py -v`
Expected: FAIL

**Step 4: Write the analysis service (orchestrator)**

```python
# app/services/analysis.py
from app.errors import NotFoundError
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.runs import FeatureRunRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.base import BaseService
from app.services.track_analysis import TrackAnalysisService

class AnalysisOrchestrator(BaseService):
    """Orchestrates the full analysis workflow: create run → extract → persist."""

    def __init__(
        self,
        track_repo: TrackRepository,
        features_repo: AudioFeaturesRepository,
        sections_repo: SectionsRepository,
        run_repo: FeatureRunRepository,
    ) -> None:
        super().__init__()
        self.track_repo = track_repo
        self.run_repo = run_repo
        self.analysis_svc = TrackAnalysisService(track_repo, features_repo, sections_repo)

    async def analyze(self, track_id: int, request: AnalysisRequest) -> AnalysisResponse:
        # Validate track exists
        track = await self.track_repo.get_by_id(track_id)
        if not track:
            raise NotFoundError("Track", track_id=track_id)

        # Create a run
        run = await self.run_repo.create(
            pipeline_name=request.pipeline_name,
            pipeline_version=request.pipeline_version,
            status="running",
        )

        try:
            if request.full_analysis:
                features = await self.analysis_svc.analyze_track_full(
                    track_id, request.audio_path, run.run_id,
                )
            else:
                features = await self.analysis_svc.analyze_track(
                    track_id, request.audio_path, run.run_id,
                )
            await self.run_repo.mark_completed(run.run_id)

            return AnalysisResponse(
                track_id=track_id,
                run_id=run.run_id,
                status="completed",
                bpm=features.bpm.bpm,
                key_code=features.key.key_code,
            )
        except Exception:
            self.logger.exception("Analysis failed for track %d", track_id)
            await self.run_repo.mark_failed(run.run_id)
            return AnalysisResponse(
                track_id=track_id,
                run_id=run.run_id,
                status="failed",
            )
```

**Step 5: Write the router**

```python
# app/routers/v1/analysis.py
from fastapi import APIRouter

from app.dependencies import DbSession
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.runs import FeatureRunRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis import AnalysisOrchestrator

router = APIRouter(prefix="/tracks", tags=["analysis"])

def _service(db: DbSession) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        track_repo=TrackRepository(db),
        features_repo=AudioFeaturesRepository(db),
        sections_repo=SectionsRepository(db),
        run_repo=FeatureRunRepository(db),
    )

@router.post(
    "/{track_id}/analyze",
    response_model=AnalysisResponse,
    summary="Analyze track audio",
    description=(
        "Extract audio features from a track's audio file. Creates a feature extraction "
        "run, extracts BPM/key/loudness/spectral/energy features, and persists results. "
        "Set full_analysis=true for Phase 2 features (beats, sections)."
    ),
    response_description="Analysis result with run ID and extracted features summary",
    responses=RESPONSES_GET,
    operation_id="analyze_track",
)
async def analyze_track(
    track_id: int, data: AnalysisRequest, db: DbSession,
) -> AnalysisResponse:
    result = await _service(db).analyze(track_id, data)
    await db.commit()
    return result
```

**Step 6: Register in `app/routers/v1/__init__.py`**

**Step 7: Run tests**

Run: `uv run pytest tests/test_analysis_api.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add app/schemas/analysis.py app/services/analysis.py app/routers/v1/analysis.py app/routers/v1/__init__.py tests/test_analysis_api.py
git commit -m "feat(api): add POST /tracks/{id}/analyze endpoint"
```

---

## Task 8: TransitionCandidate — Repository + Pre-filter

**Files:**
- Create: `app/repositories/candidates.py`
- Create: `app/schemas/candidates.py`
- Create: `tests/test_candidates.py`

**Step 1: Write the failing test**

```python
# tests/test_candidates.py
from app.schemas.candidates import CandidateRead, CandidateList

async def test_candidate_schema():
    from datetime import datetime
    data = CandidateRead(
        from_track_id=1, to_track_id=2, run_id=1,
        bpm_distance=2.0, key_distance=1.0,
        embedding_similarity=None, energy_delta=None,
        is_fully_scored=False, created_at=datetime(2026, 1, 1),
    )
    assert data.bpm_distance == 2.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_candidates.py -v`
Expected: FAIL with ImportError

**Step 3: Write schemas**

```python
# app/schemas/candidates.py
from datetime import datetime

from app.schemas.base import BaseSchema

class CandidateRead(BaseSchema):
    from_track_id: int
    to_track_id: int
    run_id: int
    bpm_distance: float
    key_distance: float
    embedding_similarity: float | None = None
    energy_delta: float | None = None
    is_fully_scored: bool
    created_at: datetime

class CandidateList(BaseSchema):
    items: list[CandidateRead]
    total: int
```

**Step 4: Write repository**

```python
# app/repositories/candidates.py
from typing import Any

from app.models.transitions import TransitionCandidate
from app.repositories.base import BaseRepository

class CandidateRepository(BaseRepository[TransitionCandidate]):
    model = TransitionCandidate

    async def list_unscored(
        self, run_id: int, *, offset: int = 0, limit: int = 50,
    ) -> tuple[list[TransitionCandidate], int]:
        filters: list[Any] = [
            self.model.run_id == run_id,
            self.model.is_fully_scored == False,  # noqa: E712
        ]
        return await self.list(offset=offset, limit=limit, filters=filters)

    async def list_for_track(
        self, track_id: int, *, offset: int = 0, limit: int = 50,
    ) -> tuple[list[TransitionCandidate], int]:
        filters: list[Any] = [
            (self.model.from_track_id == track_id)
            | (self.model.to_track_id == track_id),
        ]
        return await self.list(offset=offset, limit=limit, filters=filters)
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_candidates.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/schemas/candidates.py app/repositories/candidates.py tests/test_candidates.py
git commit -m "feat: add TransitionCandidate schema and repository"
```

---

## Task 9: Transition Scoring Service

This is the core integration: bridges `score_transition()` from utils to the Transition ORM model.

**Files:**
- Create: `app/services/transition_scoring.py`
- Create: `tests/test_transition_scoring.py`

**Step 1: Write the failing tests**

```python
# tests/test_transition_scoring.py
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

from app.models.features import TrackAudioFeaturesComputed  # noqa: E402
from app.services.transition_scoring import TransitionScoringService  # noqa: E402

def _mock_features(track_id: int, bpm: float = 140.0, key_code: int = 18) -> MagicMock:
    """Create a mock TrackAudioFeaturesComputed row."""
    feat = MagicMock(spec=TrackAudioFeaturesComputed)
    feat.track_id = track_id
    feat.bpm = bpm
    feat.tempo_confidence = 0.9
    feat.bpm_stability = 0.95
    feat.is_variable_tempo = False
    feat.key_code = key_code
    feat.key_confidence = 0.85
    feat.is_atonal = False
    feat.sub_energy = 0.3
    feat.low_energy = 0.7
    feat.low_mid_energy = 0.5
    feat.lowmid_energy = 0.5
    feat.mid_energy = 0.4
    feat.highmid_energy = 0.2
    feat.high_energy = 0.1
    feat.low_high_ratio = 7.0
    feat.sub_lowmid_ratio = 0.6
    feat.centroid_mean_hz = 1500.0
    feat.rolloff_85_hz = 5000.0
    feat.rolloff_95_hz = 8000.0
    feat.flatness_mean = 0.3
    feat.flux_mean = 0.5
    feat.flux_std = 0.1
    feat.contrast_mean_db = 20.0
    feat.chroma = "[0,0,0,0,0,0,0,0,0,0,0,0]"
    return feat

class TestTransitionScoringService:
    @pytest.fixture
    def service(self) -> TransitionScoringService:
        features_repo = MagicMock()
        transitions_repo = MagicMock()
        transitions_repo.create = AsyncMock()
        candidates_repo = MagicMock()
        candidates_repo.create = AsyncMock()
        return TransitionScoringService(features_repo, transitions_repo, candidates_repo)

    async def test_score_pair(self, service: TransitionScoringService) -> None:
        feat_a = _mock_features(1, bpm=140.0, key_code=18)
        feat_b = _mock_features(2, bpm=142.0, key_code=18)
        service.features_repo.get_by_track = AsyncMock(side_effect=[feat_a, feat_b])

        result = await service.score_pair(
            from_track_id=1, to_track_id=2, run_id=1,
        )
        assert result.transition_quality > 0
        assert result.bpm_distance == pytest.approx(2.0)
        service.transitions_repo.create.assert_awaited_once()

    async def test_score_pair_missing_features(self, service: TransitionScoringService) -> None:
        service.features_repo.get_by_track = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="No features"):
            await service.score_pair(from_track_id=1, to_track_id=2, run_id=1)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transition_scoring.py -v`
Expected: FAIL with ImportError

**Step 3: Write the service**

```python
# app/services/transition_scoring.py
from __future__ import annotations

from app.models.features import TrackAudioFeaturesComputed
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.candidates import CandidateRepository
from app.repositories.transitions import TransitionRepository
from app.services.base import BaseService
from app.utils.audio._types import (
    BandEnergyResult,
    BpmResult,
    KeyResult,
    SpectralResult,
    TransitionScore,
)
from app.utils.audio.camelot import camelot_distance
from app.utils.audio.transition_score import score_transition

class TransitionScoringService(BaseService):
    """Bridges utils/transition_score → Transition ORM via repositories."""

    def __init__(
        self,
        features_repo: AudioFeaturesRepository,
        transitions_repo: TransitionRepository,
        candidates_repo: CandidateRepository,
    ) -> None:
        super().__init__()
        self.features_repo = features_repo
        self.transitions_repo = transitions_repo
        self.candidates_repo = candidates_repo

    async def score_pair(
        self,
        from_track_id: int,
        to_track_id: int,
        run_id: int,
        *,
        groove_sim: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> TransitionScore:
        """Score a transition between two tracks and persist result."""
        feat_a = await self.features_repo.get_by_track(from_track_id)
        if not feat_a:
            msg = f"No features found for track {from_track_id}"
            raise ValueError(msg)

        feat_b = await self.features_repo.get_by_track(to_track_id)
        if not feat_b:
            msg = f"No features found for track {to_track_id}"
            raise ValueError(msg)

        # Map ORM → utils types
        bpm_a, bpm_b = self._to_bpm(feat_a), self._to_bpm(feat_b)
        key_a, key_b = self._to_key(feat_a), self._to_key(feat_b)
        energy_a, energy_b = self._to_energy(feat_a), self._to_energy(feat_b)
        spec_a, spec_b = self._to_spectral(feat_a), self._to_spectral(feat_b)

        # Score via utils
        result = score_transition(
            bpm_a=bpm_a, bpm_b=bpm_b,
            key_a=key_a, key_b=key_b,
            energy_a=energy_a, energy_b=energy_b,
            spectral_a=spec_a, spectral_b=spec_b,
            groove_sim=groove_sim,
            weights=weights,
        )

        # Persist
        centroid_gap = abs(
            (feat_a.centroid_mean_hz or 0) - (feat_b.centroid_mean_hz or 0)
        )
        await self.transitions_repo.create(
            run_id=run_id,
            from_track_id=from_track_id,
            to_track_id=to_track_id,
            overlap_ms=0,
            bpm_distance=result.bpm_distance,
            energy_step=result.energy_step,
            centroid_gap_hz=centroid_gap,
            low_conflict_score=result.low_conflict_score,
            overlap_score=result.overlap_score,
            groove_similarity=result.groove_similarity,
            key_distance_weighted=result.key_distance_weighted,
            transition_quality=result.transition_quality,
        )

        return result

    async def create_candidate(
        self,
        from_track_id: int,
        to_track_id: int,
        run_id: int,
    ) -> None:
        """Pre-filter stage 1: create lightweight candidate from features."""
        feat_a = await self.features_repo.get_by_track(from_track_id)
        feat_b = await self.features_repo.get_by_track(to_track_id)
        if not feat_a or not feat_b:
            return  # Skip pairs without features

        bpm_dist = abs(feat_a.bpm - feat_b.bpm)
        key_dist = float(camelot_distance(feat_a.key_code, feat_b.key_code))
        energy_delta = (feat_b.energy_mean or 0) - (feat_a.energy_mean or 0)

        await self.candidates_repo.create(
            from_track_id=from_track_id,
            to_track_id=to_track_id,
            run_id=run_id,
            bpm_distance=bpm_dist,
            key_distance=key_dist,
            energy_delta=energy_delta,
            is_fully_scored=False,
        )

    @staticmethod
    def _to_bpm(feat: TrackAudioFeaturesComputed) -> BpmResult:
        import numpy as np
        return BpmResult(
            bpm=feat.bpm,
            confidence=feat.tempo_confidence,
            stability=feat.bpm_stability,
            is_variable=feat.is_variable_tempo,
        )

    @staticmethod
    def _to_key(feat: TrackAudioFeaturesComputed) -> KeyResult:
        import json
        import numpy as np
        chroma = np.zeros(12, dtype=np.float32)
        if feat.chroma:
            try:
                chroma = np.array(json.loads(feat.chroma), dtype=np.float32)
            except (json.JSONDecodeError, ValueError):
                pass
        # Derive key name from key_code (pitch_class * 2 + mode)
        pitch_class = feat.key_code // 2
        mode = feat.key_code % 2
        pitch_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return KeyResult(
            key=pitch_names[pitch_class],
            scale="major" if mode == 1 else "minor",
            key_code=feat.key_code,
            confidence=feat.key_confidence,
            is_atonal=feat.is_atonal,
            chroma=chroma,
        )

    @staticmethod
    def _to_energy(feat: TrackAudioFeaturesComputed) -> BandEnergyResult:
        return BandEnergyResult(
            sub=feat.sub_energy or 0.0,
            low=feat.low_energy or 0.0,
            low_mid=feat.lowmid_energy or 0.0,
            mid=feat.mid_energy or 0.0,
            high_mid=feat.highmid_energy or 0.0,
            high=feat.high_energy or 0.0,
            low_high_ratio=feat.low_high_ratio or 0.0,
            sub_lowmid_ratio=feat.sub_lowmid_ratio or 0.0,
        )

    @staticmethod
    def _to_spectral(feat: TrackAudioFeaturesComputed) -> SpectralResult:
        return SpectralResult(
            centroid_mean_hz=feat.centroid_mean_hz or 0.0,
            rolloff_85_hz=feat.rolloff_85_hz or 0.0,
            rolloff_95_hz=feat.rolloff_95_hz or 0.0,
            flatness_mean=feat.flatness_mean or 0.0,
            flux_mean=feat.flux_mean or 0.0,
            flux_std=feat.flux_std or 0.0,
            contrast_mean_db=feat.contrast_mean_db or 0.0,
        )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_transition_scoring.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/transition_scoring.py tests/test_transition_scoring.py
git commit -m "feat: add TransitionScoringService bridging utils to repos"
```

---

## Task 10: Transition Compute Endpoints

**Files:**
- Modify: `app/routers/v1/transitions.py` — add compute endpoints
- Modify: `app/services/transitions.py` — integrate scoring
- Modify: `tests/test_transitions_api.py` (if exists, or create)

**Step 1: Write the failing tests**

```python
# tests/test_transitions_compute.py
from unittest.mock import patch

import numpy as np
import pytest

essentia = pytest.importorskip("essentia")

async def test_compute_transition_missing_features(client):
    """Computing transition without features should return 422 or appropriate error."""
    track1 = await client.post("/api/v1/tracks", json={"title": "A", "duration_ms": 300000})
    track2 = await client.post("/api/v1/tracks", json={"title": "B", "duration_ms": 300000})

    # Create a transition run
    run = await client.post("/api/v1/runs/transitions", json={
        "pipeline_name": "scorer-v1", "pipeline_version": "1.0.0",
    })
    run_id = run.json()["run_id"]

    resp = await client.post("/api/v1/transitions/compute", json={
        "from_track_id": track1.json()["track_id"],
        "to_track_id": track2.json()["track_id"],
        "run_id": run_id,
    })
    # Should fail gracefully — no features to score
    assert resp.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transitions_compute.py -v`
Expected: FAIL (route doesn't exist)

**Step 3: Add compute schema**

Add to `app/schemas/transitions.py`:

```python
class TransitionComputeRequest(BaseSchema):
    from_track_id: int
    to_track_id: int
    run_id: int
    groove_sim: float = 0.5
    weights: dict[str, float] | None = None

class TransitionComputeResponse(BaseSchema):
    transition_quality: float
    bpm_distance: float
    key_distance_weighted: float
    energy_step: float
    low_conflict_score: float
    overlap_score: float
    groove_similarity: float
```

**Step 4: Add compute endpoint to transitions router**

Add to `app/routers/v1/transitions.py`:

```python
from app.repositories.audio_features import AudioFeaturesRepository
from app.repositories.candidates import CandidateRepository
from app.schemas.transitions import TransitionComputeRequest, TransitionComputeResponse
from app.services.transition_scoring import TransitionScoringService

def _scoring_service(db: DbSession) -> TransitionScoringService:
    return TransitionScoringService(
        AudioFeaturesRepository(db),
        TransitionRepository(db),
        CandidateRepository(db),
    )

@router.post(
    "/compute",
    response_model=TransitionComputeResponse,
    summary="Compute transition score",
    description="Score a transition between two tracks using their audio features.",
    response_description="Computed transition score and components",
    operation_id="compute_transition",
)
async def compute_transition(
    data: TransitionComputeRequest, db: DbSession,
) -> TransitionComputeResponse:
    svc = _scoring_service(db)
    result = await svc.score_pair(
        from_track_id=data.from_track_id,
        to_track_id=data.to_track_id,
        run_id=data.run_id,
        groove_sim=data.groove_sim,
        weights=data.weights,
    )
    await db.commit()
    return TransitionComputeResponse(
        transition_quality=result.transition_quality,
        bpm_distance=result.bpm_distance,
        key_distance_weighted=result.key_distance_weighted,
        energy_step=result.energy_step,
        low_conflict_score=result.low_conflict_score,
        overlap_score=result.overlap_score,
        groove_similarity=result.groove_similarity,
    )
```

**Note:** The `ValueError` raised by `score_pair` when features are missing needs to be handled. Add to `app/errors.py` or catch in the router and return 422. The convention is to handle via the existing `ValidationError(422)` from `app/errors.py`.

**Step 5: Run tests**

Run: `uv run pytest tests/test_transitions_compute.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/schemas/transitions.py app/routers/v1/transitions.py tests/test_transitions_compute.py
git commit -m "feat(api): add POST /transitions/compute endpoint"
```

---

## Task 11: Full lint + type check + all tests

**Step 1: Run ruff**

```bash
uv run ruff check app/ tests/ --fix
uv run ruff format app/ tests/
```

**Step 2: Run mypy**

```bash
uv run mypy app/
```

Fix any type errors.

**Step 3: Run all tests**

```bash
uv run pytest -v
```

**Step 4: Commit any fixes**

```bash
git add -u
git commit -m "chore: fix lint and type errors from integration"
```

---

## Summary of new files

| Layer | File | Purpose |
|-------|------|---------|
| Schema | `app/schemas/runs.py` | FeatureRun + TransitionRun CRUD schemas |
| Schema | `app/schemas/features.py` | AudioFeaturesRead (read-only) |
| Schema | `app/schemas/sections.py` | SectionRead (read-only) |
| Schema | `app/schemas/analysis.py` | AnalysisRequest + AnalysisResponse |
| Schema | `app/schemas/candidates.py` | CandidateRead (read-only) |
| Repo | `app/repositories/runs.py` | FeatureRunRepository + TransitionRunRepository |
| Repo | `app/repositories/candidates.py` | CandidateRepository |
| Service | `app/services/runs.py` | FeatureRunService + TransitionRunService |
| Service | `app/services/features.py` | AudioFeaturesService |
| Service | `app/services/sections.py` | SectionsService |
| Service | `app/services/analysis.py` | AnalysisOrchestrator |
| Service | `app/services/transition_scoring.py` | TransitionScoringService |
| Router | `app/routers/v1/runs.py` | /runs/features + /runs/transitions |
| Router | `app/routers/v1/features.py` | /tracks/{id}/features |
| Router | `app/routers/v1/sections.py` | /tracks/{id}/sections |
| Router | `app/routers/v1/analysis.py` | /tracks/{id}/analyze |
| Test | `tests/test_runs.py` | Runs schema + repo + API tests |
| Test | `tests/test_features_api.py` | Features API tests |
| Test | `tests/test_sections_api.py` | Sections API tests |
| Test | `tests/test_analysis_api.py` | Analysis trigger tests |
| Test | `tests/test_candidates.py` | Candidate schema + repo tests |
| Test | `tests/test_transition_scoring.py` | Scoring service unit tests |
| Test | `tests/test_transitions_compute.py` | Compute endpoint API tests |

## Modified files

| File | Change |
|------|--------|
| `app/routers/v1/__init__.py` | Register 4 new routers |
| `app/repositories/audio_features.py` | Add `get_by_track`, `list_by_track` |
| `app/repositories/sections.py` | Add `list_by_track` |
| `app/schemas/transitions.py` | Add `TransitionComputeRequest/Response` |
| `app/routers/v1/transitions.py` | Add `POST /compute` endpoint |

## New API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/runs/features` | Create feature extraction run |
| GET | `/api/v1/runs/features` | List feature extraction runs |
| GET | `/api/v1/runs/features/{run_id}` | Get feature extraction run |
| POST | `/api/v1/runs/transitions` | Create transition run |
| GET | `/api/v1/runs/transitions` | List transition runs |
| GET | `/api/v1/runs/transitions/{run_id}` | Get transition run |
| GET | `/api/v1/tracks/{id}/features` | List audio features for track |
| GET | `/api/v1/tracks/{id}/features/latest` | Get latest features for track |
| GET | `/api/v1/tracks/{id}/sections` | List sections for track |
| POST | `/api/v1/tracks/{id}/analyze` | Trigger audio analysis |
| POST | `/api/v1/transitions/compute` | Compute transition score |
