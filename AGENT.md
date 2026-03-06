# AGENT.md

Guidelines for coding agents working in this repository.

## Project Snapshot

- Stack: Python 3.12+, FastAPI, SQLAlchemy asyncio, Pydantic v2, Alembic.
- Package/deps: managed with `uv` (`pyproject.toml`, `uv.lock`).
- Default dev DB: SQLite (`sqlite+aiosqlite:///./dev.db`).
- Source-of-truth DB design: `schema_v6.sql` (PostgreSQL 16+).

## Fast Commands

```bash
# Install / sync deps
uv sync --all-extras

# Run app (dev)
uv run uvicorn app.main:app --reload

# Tests
uv run pytest -v
uv run pytest tests/test_tracks.py -v

# Lint + type-check
uv run ruff check
uv run mypy app/

# Alembic
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

## Linear / PR Naming (required)

This repo links work to Linear issues via the issue identifier (e.g. `BPM-123`).

- **Branch name**: start with the issue ID, e.g. `BPM-123-orm-schema-audit`
- **PR title**: start with the issue ID, e.g. `BPM-123: Fix ORM default consistency`
- **PR description**: include a magic-word link line, e.g. `Fixes BPM-123` (or `Related to BPM-123`)

Details: `docs/linear.md`

## Architecture Rules

- Keep the layered flow: Router -> Service -> Repository -> DB session.
- Routers live in `app/routers/v1/` (except health in `app/routers/health.py`).
- Services hold business logic and raise domain errors (`app/errors.py`).
- Repositories handle persistence; shared CRUD in `app/repositories/base.py`.
- DI pattern: use `DbSession` from `app/dependencies.py`.
- For mutating endpoints, commit in router after service call (current pattern).

## App Lifecycle / DB

- App factory is `create_app()` in `app/main.py`.
- Lifespan calls `init_db()`/`close_db()` from `app/database.py`.
- SQLite path auto-creates tables in `init_db()` for local dev/tests.
- Always ensure models are imported before `Base.metadata.create_all()`:
  - Use `from app.models import Base` in tests/fixtures.

## Models and Schema Conventions

- Every ORM model must stay aligned with `schema_v6.sql`.
- Prefer explicit `CheckConstraint` in model columns (matching DDL intent/names).
- Base classes:
  - `Base` in `app/models/base.py`
  - `TimestampMixin` for mutable rows (`created_at`, `updated_at`)
  - `CreatedAtMixin` for append-only rows
- Enums in `app/models/enums.py` are app-level helpers; DB stores raw `smallint`/`text`.
- Keep `app/models/__init__.py` exports and `__all__` sorted.

## SQLite/PostgreSQL Compatibility

Project tests run on SQLite, production targets PostgreSQL. Keep models portable:

- Use SQLAlchemy-generic types instead of PG-only where possible.
- Use `server_default=func.now()` (not literal `"now()"`).
- For pgvector fields, keep SQLite placeholder as `String` (see embeddings/features/transitions).
- For PG `int4range` semantics, use `start_ms`/`end_ms` columns in ORM (`TrackSection`).

## API and Schema Patterns

- API root for versioned endpoints: `/api/v1`.
- Current domain example: tracks (`app/routers/v1/tracks.py` + service/repo/schemas).
- Pydantic schemas should inherit `BaseSchema` (`from_attributes=True`, `extra="forbid"`).
- Error responses should go through `AppError` subclasses and global handlers.

## Testing Expectations

- Test framework: `pytest` + `pytest-asyncio` (`asyncio_mode=auto`).
- Core fixtures in `tests/conftest.py`: `engine`, `session`, `client`.
- For model changes:
  - Add/adjust constraint tests (expect `IntegrityError` where relevant).
  - Cover both happy path and invalid data path.
- For API changes:
  - Cover CRUD behavior, pagination/search, and error responses.

## Change Checklist

When implementing non-trivial changes, verify all relevant items:

1. Updated ORM model(s), schema(s), repository/service/router layers as needed.
2. Added or adjusted tests in `tests/`.
3. `uv run ruff check` passes.
4. `uv run mypy app/` passes.
5. `uv run pytest -v` passes (or at least touched subset, then full suite when possible).
6. If DB shape changed: update Alembic migration and keep `schema_v6.sql`/docs in sync when requested.

## Branch Setup (ALWAYS first step)

Before reading or writing any file, verify you are on the correct branch:

```bash
git checkout <target-branch>          # switch to the PR branch
git pull origin <target-branch>       # get latest remote state
git log --oneline -5                  # confirm expected commits are present
```

If a file the task references is not found after checkout:
- Do NOT assume it doesn't exist
- Run `git log --all -- path/to/file` to check if it exists on another branch
- Do NOT create a replacement file — report the blocker explicitly

## Delegated Execution Guardrail (required)

When an agent is delegated a Linear/dev task, it must execute implementation work with available repo tools and may not stop with a generic "tool unavailable" response.

- Do not block on non-essential messaging APIs/tools (for example `send_message`-like helpers).
- If a specific helper tool is missing, continue with shell/file/repo tools and complete the coding scope as far as possible.
- Only mark work complete after concrete artifacts exist:
  - changed files,
  - test command(s) run and outcome,
  - commit/PR reference,
  - short list of residual risks.
- If truly blocked, report an explicit blocker:
  - exact missing capability/tool,
  - exact command or action that failed,
  - what was already implemented before blocking.
