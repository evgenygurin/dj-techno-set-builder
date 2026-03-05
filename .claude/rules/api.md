---
paths:
  - "app/routers/**"
  - "app/schemas/**"
  - "app/services/**"
  - "app/errors.py"
  - "app/dependencies.py"
  - "app/clients/**"
---

# API Layer: Routers, Services, Schemas

## Adding a new domain (step-by-step)

1. **Schema** — `app/schemas/domain.py`:
   - `DomainCreate(BaseSchema)` — POST body (required fields with `Field()` validators)
   - `DomainRead(BaseSchema)` — GET response (includes `domain_id`, timestamps)
   - `DomainUpdate(BaseSchema)` — PATCH body (all fields `Optional`)
   - `DomainList(BaseSchema)` — `items: list[DomainRead]` + `total: int`

2. **Repository** — `app/repositories/domain.py`:
   - `DomainRepository(BaseRepository[DomainModel])` with `model = DomainModel`
   - Add custom queries if needed (search, filters)

3. **Service** — `app/services/domain.py`:
   - `DomainService(BaseService)` — takes repo in constructor
   - Methods: `get()`, `list()`, `create()`, `update()`, `delete()`

4. **Router** — `app/routers/v1/domain.py`:
   - `router = APIRouter(prefix="/domain", tags=["domain"])`
   - `def _service(db: DbSession) -> DomainService:` — factory function
   - Import shared responses from `_openapi.py`
   - Always include `summary`, `description`, `response_description`, `operation_id`

5. **Register** in `app/routers/v1/__init__.py`:
   ```python
   v1_router.include_router(domain.router)
   ```

## Router pattern

Every router follows the same structure:

```python
router = APIRouter(prefix="/tracks", tags=["tracks"])

def _service(db: DbSession) -> TrackService:
    return TrackService(TrackRepository(db))

@router.get("", response_model=TrackList, responses=RESPONSES_GET,
            summary="List tracks", operation_id="listTracks")
async def list_tracks(db: DbSession, offset: int = 0, limit: int = 50) -> TrackList:
    return await _service(db).list(offset=offset, limit=limit)

@router.post("", response_model=TrackRead, status_code=201,
             responses=RESPONSES_CREATE, summary="Create track")
async def create_track(data: TrackCreate, db: DbSession) -> TrackRead:
    result = await _service(db).create(data)
    await db.commit()  # Commit in router, not service!
    return result
```

13 domain routers using this pattern + health router.

## Transactional boundary

**Critical pattern**: `commit()` is called in the **router** (HTTP layer), NOT in services or repositories:
- Repositories call `flush()` — makes data visible within the session
- Services delegate to repositories — no explicit flush/commit
- Routers call `await db.commit()` after successful service calls

This ensures that if any step fails, the whole transaction rolls back.

## DI pattern

`app/dependencies.py`:
```python
DbSession = Annotated[AsyncSession, Depends(get_session)]
```

Usage: `async def endpoint(db: DbSession):` — every handler gets a fresh session.

## OpenAPI error responses

`app/routers/v1/_openapi.py` — shared response schemas:

| Constant | Status codes | Use in |
|----------|-------------|--------|
| `RESPONSES_GET` | 404 | GET by ID |
| `RESPONSES_CREATE` | 409 | POST |
| `RESPONSES_UPDATE` | 404, 409 | PATCH |
| `RESPONSES_DELETE` | 404 | DELETE |

Usage: `@router.get(..., responses=RESPONSES_GET)`

## Error handling

`AppError` hierarchy (`app/errors.py`):
- `NotFoundError(resource, **details)` — 404, `{"code": "NOT_FOUND", "message": "Track not found", "details": {"track_id": 123}}`
- `ValidationError(message, **details)` — 422
- `ConflictError(resource, **details)` — 409

Registered as global exception handlers in `create_app()` via `register_error_handlers(app)`.

## Schema conventions

`BaseSchema` (`app/schemas/base.py`):
- `from_attributes=True` — for `model_validate(orm_obj)` from SQLAlchemy models
- `extra="forbid"` — rejects unknown fields in request body

Ternary pattern: `Create` (POST fields) -> `Read` (response with IDs + timestamps) -> `Update` (all Optional)

Common validators: `Field(min_length=1, max_length=500)`, `Field(gt=0)`, `Field(ge=0, le=1)`

## Key abstractions

- **`BaseRepository[ModelT: Base]`** (`app/repositories/base.py`): Generic CRUD with PEP 695 type params. Methods: `get_by_id`, `list`, `create`, `update`, `delete`. Subclasses set `model = SomeModel`.
- **`BaseSchema`** (`app/schemas/base.py`): Pydantic `BaseModel` with `from_attributes=True`, `extra="forbid"`.
- **`BaseService`** (`app/services/base.py`): Sets up `self.logger = logging.getLogger(self.__class__.__qualname__)`.
- **`AppError`** (`app/errors.py`): Base for NotFoundError(404), ValidationError(422), ConflictError(409).

## Multi-repo service pattern

For cross-cutting operations that span multiple repositories:

```python
class AnalysisOrchestrator(BaseService):
    def __init__(self, track_repo, features_repo, sections_repo, run_repo):
        super().__init__()
        self.track_repo = track_repo
        self.analysis_svc = TrackAnalysisService(track_repo, features_repo, sections_repo)
```

Examples: `AnalysisOrchestrator` (4 repos), `SetGenerationService` (4 repos), `ImportYandexService` (6 repos + YM client).

## Yandex Music client

`app/clients/yandex_music.py` — `YandexMusicClient`:
- Lazy httpx.AsyncClient initialization
- Auth: OAuth token from `settings.yandex_music_token`
- Configured via env vars: `YANDEX_MUSIC_TOKEN`, `YANDEX_MUSIC_BASE_URL`, `YANDEX_MUSIC_USER_ID`

| Method | Args | Returns | Notes |
|--------|------|---------|-------|
| `search_tracks(query)` | str | list[dict] | Search YM catalog |
| `fetch_tracks(track_ids)` | list[int] | list[dict] | Batch fetch by ID |
| `create_playlist(user_id, title, visibility)` | int, str, str | int | Returns `kind` (playlist ID) |
| `add_tracks_to_playlist(user_id, kind, tracks, revision)` | int, int, list[dict], int | None | `tracks` = `[{"id": "...", "albumId": "..."}]` |
| `close()` | — | None | Close HTTP client |

**YM diff format** — `add_tracks_to_playlist` sends JSON array (NOT object):
```python
diff = [{"op": "insert", "at": 0, "tracks": [{"id": "123", "albumId": "456"}]}]
await _post_form(f"/users/{uid}/playlists/{kind}/change", {"diff": json.dumps(diff), "revision": "1"})
```

## Configuration

`app/config.py` — `Settings(BaseSettings)` with `.env`:

| Env var | Default | Purpose |
|---------|---------|---------|
| `APP_NAME` | "DJ Techno Set Builder" | FastAPI title |
| `DEBUG` | False | Debug mode |
| `LOG_LEVEL` | "INFO" | Logging level |
| `DATABASE_URL` | "sqlite+aiosqlite:///./dev.db" | DB connection |
| `YANDEX_MUSIC_TOKEN` | "" | YM OAuth token |
| `YANDEX_MUSIC_USER_ID` | "" | YM user ID |
| `YANDEX_MUSIC_BASE_URL` | "https://api.music.yandex.net:443" | YM API |
| `DJ_LIBRARY_PATH` | — | Path to iCloud library root (for deliver_set output) |

Settings use `SettingsConfigDict(extra="ignore")` — unknown env vars are silently ignored.
