# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install / sync dependencies
uv sync --all-extras

# Run all tests
uv run pytest -v

# Run a single test file
uv run pytest tests/test_tracks.py -v

# Run a single test function
uv run pytest tests/test_tracks.py::test_create_track -v

# Lint
uv run ruff check
uv run ruff format --check

# Type-check
uv run mypy app/

# Dev server
uv run uvicorn app.main:app --reload

# Alembic migrations (uses DATABASE_URL from .env or defaults to SQLite)
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## Architecture

```text
Router → Service → Repository → AsyncSession → DB
  ↕         ↕          ↕
Schemas   Errors     Models
```

**Request flow**: FastAPI router receives request → instantiates Service with Repository → Repository uses async SQLAlchemy session → Service returns Pydantic schema.

**DI pattern**: Session injection via `DbSession = Annotated[AsyncSession, Depends(get_session)]` in `app/dependencies.py`. Routers create service instances inline (no global singletons).

**App factory**: `create_app()` in `app/main.py` with `asynccontextmanager` lifespan that calls `init_db()`/`close_db()`.

### Versioned API routes

- Health: `GET /health` (unversioned, `app/routers/health.py`)
- All domain routes: `/api/v1/...` via `app/routers/v1/` — each domain gets its own router file

### Adding a new domain (e.g., artists)

1. `app/schemas/artists.py` — Pydantic schemas (`ArtistCreate`, `ArtistRead`, etc.) extending `BaseSchema`
2. `app/repositories/artists.py` — `ArtistRepository(BaseRepository[Artist])` with `model = Artist`
3. `app/services/artists.py` — `ArtistService(BaseService)` with business logic
4. `app/routers/v1/artists.py` — APIRouter, wire service via `_service(db)` pattern
5. Register router in `app/routers/v1/__init__.py`

### Key abstractions

- **`BaseRepository[ModelT: Base]`** (`app/repositories/base.py`): Generic CRUD using PEP 695 type params. Provides `get_by_id`, `list` (with filters + count), `create`, `update`, `delete`. Subclasses set `model = SomeModel` and add domain-specific queries.
- **`BaseSchema`** (`app/schemas/base.py`): Pydantic `BaseModel` with `from_attributes=True` and `extra="forbid"`.
- **`BaseService`** (`app/services/base.py`): Sets up `self.logger`.
- **`AppError` hierarchy** (`app/errors.py`): `NotFoundError(404)`, `ValidationError(422)`, `ConflictError(409)`. Registered as global exception handlers returning `{code, message, details}` JSON.

## Models & Database

- **DDL source of truth**: `data/schema_v6.sql` (PostgreSQL DDL with pgvector, btree_gist, pg_trgm)
- **Dev DB**: SQLite via aiosqlite (auto-created by `init_db()` when URL starts with `sqlite`)
- **Prod DB**: PostgreSQL 16+ with asyncpg
- **30+ ORM models** in `app/models/` — all re-exported through `app/models/__init__.py`

### Model conventions

- All models inherit from `Base` (DeclarativeBase) in `app/models/base.py`
- Updatable tables use `TimestampMixin` (created_at + updated_at)
- Append-only tables use `CreatedAtMixin` (created_at only)
- **CHECK constraints inline** in `mapped_column()` matching the DDL exactly
- Domain enums in `app/models/enums.py` are Python `IntEnum`/`StrEnum` — DB stores raw smallint/text, not the enum type
- `__all__` lists in `__init__.py` must be alphabetically sorted (ruff RUF022)

### SQLite compatibility (tests)

Models must work on both SQLite (tests) and PostgreSQL (prod):
- Use `JSON` (not `JSONB` from `sqlalchemy.dialects.postgresql`)
- Use `server_default=func.now()` (not string `"now()"`)
- pgvector `vector(N)` columns use `String` as placeholder
- `int4range` columns use `start_ms`/`end_ms` integer pairs instead

### Test fixtures

`tests/conftest.py` provides three async fixtures:
- `engine` — in-memory SQLite with `create_all`/`drop_all`
- `session` — async session for direct model tests
- `client` — httpx `AsyncClient` with `dependency_overrides[get_session]` for API tests

**Critical**: `from app.models import Base` (not `from app.models.base`) — this import triggers all model registrations so `create_all` sees every table.

## Lint & Type Rules

- **ruff**: Python 3.12 target, line-length 88, selected rules: E/F/W/I/N/UP/B/A/SIM/PLW/RUF. `A003` ignored (allow shadowing builtins on class attributes).
- **mypy**: strict mode with `pydantic.mypy` plugin. `fastmcp` and `alembic` have `ignore_missing_imports`.
- **pytest-asyncio**: `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed on async test functions.
