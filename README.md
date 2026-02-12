# DJ Techno Set Builder

Audio analysis, transition matching, and automated set construction for techno DJs.

The system ingests tracks from multiple providers (Spotify, SoundCloud, Beatport), runs DSP/ML audio analysis pipelines, scores transition compatibility between tracks, and generates optimized DJ sets with key-matching, energy-arc shaping, and feedback loops.

## Tech Stack

- **API**: Python 3.12+, FastAPI, Pydantic v2, uvicorn
- **ORM**: SQLAlchemy 2.0+ (async), Alembic migrations
- **Database**: PostgreSQL 16+ (asyncpg, pgvector, btree_gist, pg_trgm) / SQLite (dev)
- **Tooling**: uv, ruff, mypy (strict), pytest + pytest-asyncio

## Quick Start

```bash
# Clone and install
git clone https://github.com/evgenygurin/dj-techno-set-builder.git
cd dj-techno-set-builder
uv sync --all-extras

# Run dev server (SQLite, auto-creates tables)
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest -v

# Lint & type-check
uv run ruff check
uv run mypy app/
```

The dev server uses SQLite by default. To use PostgreSQL, set `DATABASE_URL` in `.env`:

```text
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dj_set_builder
```

## Architecture

```text
Router → Service → Repository → AsyncSession → DB
  ↕         ↕          ↕
Schemas   Errors     Models
```

- **Routers** (`app/routers/v1/`): FastAPI endpoints, mounted at `/api/v1`. Health check at `/health`.
- **Services** (`app/services/`): Business logic, receives repositories via constructor injection.
- **Repositories** (`app/repositories/`): Generic CRUD via `BaseRepository[ModelT]` (PEP 695), domain queries.
- **Models** (`app/models/`): 30+ SQLAlchemy ORM models matching `schema_v6.sql` with inline CHECK constraints.
- **Schemas** (`app/schemas/`): Pydantic v2 request/response models with `from_attributes=True`.
- **Errors** (`app/errors.py`): `AppError` hierarchy (NotFound, Validation, Conflict) with global exception handlers.
- **Middleware** (`app/middleware/`): `RequestIdMiddleware` — injects `X-Request-ID` via contextvars.

## Database

PostgreSQL DDL: [`schema_v6.sql`](data/schema_v6.sql) — 30+ tables organized into layers:

| Layer | Tables | Purpose |
|-------|--------|---------|
| Catalog | tracks, artists, labels, releases, genres + junction tables | Core music metadata |
| Providers | providers, provider_track_ids | Multi-source identity mapping |
| Ingestion | raw_provider_responses | Raw JSON from APIs (partitioned) |
| Metadata | spotify_*, soundcloud_*, beatport_* | Provider-specific enriched data |
| Pipeline | feature_extraction_runs, transition_runs | Versioned analysis runs |
| Assets | audio_assets | Original files + Demucs stems |
| Harmony | keys, key_edges | 24-key compatibility graph |
| Features | track_audio_features_computed | ~35 DSP/ML audio descriptors |
| Sections | track_sections | Structural segmentation (intro, drop, outro...) |
| Timeseries | track_timeseries_refs | Frame-level data pointers (object storage) |
| Transitions | transition_candidates, transitions | Two-stage transition scoring |
| Embeddings | embedding_types, track_embeddings | Vector embeddings (pgvector) |
| DJ Layer | dj_library_items, dj_beatgrid, dj_cue_points, dj_saved_loops, dj_playlists, dj_app_exports | DJ app data (Traktor, Rekordbox, djay) |
| Sets | dj_sets, dj_set_versions, dj_set_items, dj_set_constraints, dj_set_feedback | Generated sets + feedback loop |

See [`docs/database.md`](docs/database.md) for detailed schema documentation.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/tracks` | List tracks (pagination, search) |
| `GET` | `/api/v1/tracks/{id}` | Get track by ID |
| `POST` | `/api/v1/tracks` | Create track |
| `PATCH` | `/api/v1/tracks/{id}` | Update track |
| `DELETE` | `/api/v1/tracks/{id}` | Delete track |

## Project Structure

```bash
app/
  main.py              # create_app() factory with lifespan
  config.py            # Settings(BaseSettings) from .env
  database.py          # Engine, session factory, init/close
  dependencies.py      # DbSession type alias (DI)
  errors.py            # AppError hierarchy + handlers
  models/              # 30+ SQLAlchemy ORM models
  schemas/             # Pydantic v2 request/response models
  repositories/        # BaseRepository[ModelT] + domain repos
  services/            # Business logic layer
  routers/             # FastAPI routers (v1/ prefix)
  middleware/           # RequestIdMiddleware
tests/                 # pytest-asyncio, in-memory SQLite
migrations/            # Alembic (async PostgreSQL)
data/
  schema_v6.sql        # PostgreSQL DDL source of truth
```

## License

Private.
