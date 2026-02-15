# DJ Techno Set Builder

Audio analysis, transition matching, and automated set construction for techno DJs. Combines a REST API, MCP server for AI-assisted workflows, and DSP/ML audio analysis pipelines.

## Tech Stack

- **API**: Python 3.12+, FastAPI, Pydantic v2, uvicorn
- **ORM**: SQLAlchemy 2.0+ (async), Alembic migrations
- **Database**: PostgreSQL 16+ (asyncpg, pgvector, btree_gist, pg_trgm) / SQLite (dev)
- **MCP**: FastMCP 3.0 (StreamableHTTP transport, composition, structured output)
- **Audio**: essentia, soundfile, scipy, numpy (optional `audio` extra)
- **ML**: demucs, torch (optional `ml` extra for stem separation)
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

For MCP server with Yandex Music integration, also set:

```text
YANDEX_MUSIC_TOKEN=your_oauth_token
YANDEX_MUSIC_BASE_URL=https://api.music.yandex.net
```

## CI

GitHub Actions:

- `.github/workflows/ci.yml` runs lint (`ruff`), type-check (`mypy`), and tests (`pytest` with coverage).
- `.github/workflows/pr-title.yml` enforces PR title format: `TEAM-123: Short summary` for Linear linking.

Linear linking rules and magic words are documented in `docs/linear.md`.

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                      FastAPI App                         │
│                                                          │
│  REST API (/api/v1)          MCP Server (/mcp/mcp)       │
│  ┌──────────────────┐        ┌────────────────────────┐  │
│  │ Routers (v1/)    │        │ Gateway (FastMCP 3.0)  │  │
│  │  tracks, artists │        │  ├── YM (namespace ym) │  │
│  │  playlists, sets │        │  └── DJ (namespace dj) │  │
│  │  features, etc.  │        │     ├── analysis       │  │
│  └────────┬─────────┘        │     ├── discovery      │  │
│           │                  │     ├── setbuilder      │  │
│           ▼                  │     ├── import          │  │
│  ┌──────────────────┐        │     └── export          │  │
│  │ Services         │◄───────┤                         │  │
│  └────────┬─────────┘        └────────────────────────┘  │
│           ▼                                              │
│  ┌──────────────────┐        ┌────────────────────────┐  │
│  │ Repositories     │        │ Audio Utils            │  │
│  │ (BaseRepository) │        │ (pure functions, 16    │  │
│  └────────┬─────────┘        │  DSP/ML modules)       │  │
│           ▼                  └────────────────────────┘  │
│  ┌──────────────────┐                                    │
│  │ SQLAlchemy Async  │                                   │
│  │ (30+ ORM models)  │                                   │
│  └────────┬──────────┘                                   │
│           ▼                                              │
│  SQLite (dev) / PostgreSQL 16+ (prod)                    │
└──────────────────────────────────────────────────────────┘
```

- **Routers** (`app/routers/v1/`): FastAPI endpoints, mounted at `/api/v1`. Health check at `/health`.
- **Services** (`app/services/`): Business logic, receives repositories via constructor injection.
- **Repositories** (`app/repositories/`): Generic CRUD via `BaseRepository[ModelT]` (PEP 695), domain queries.
- **Models** (`app/models/`): 30+ SQLAlchemy ORM models matching `schema_v6.sql` with inline CHECK constraints.
- **Schemas** (`app/schemas/`): Pydantic v2 request/response models with `from_attributes=True`.
- **Errors** (`app/errors.py`): `AppError` hierarchy (NotFound, Validation, Conflict) with global exception handlers.
- **Middleware** (`app/middleware/`): `RequestIdMiddleware` — injects `X-Request-ID` via contextvars.
- **Audio Utils** (`app/utils/audio/`): Pure-function DSP/ML analysis layer (no DB dependencies).
- **MCP Server** (`app/mcp/`): FastMCP 3.0 gateway combining Yandex Music and DJ workflow tools.

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

## Audio Analysis Pipeline

`app/utils/audio/` — 16 pure-function modules for DSP/ML audio analysis:

| Module | Function | Output | Description |
|--------|----------|--------|-------------|
| `loader` | `load_audio()` | `AudioData` | Load audio file, resample to mono 44.1kHz |
| `bpm` | `detect_bpm()` | `BpmResult` | BPM detection with confidence score |
| `key_detect` | `detect_key()` | `KeyResult` | Musical key detection (24 keys) |
| `loudness` | `measure_loudness()` | `LoudnessResult` | Integrated LUFS, loudness range, peak |
| `energy` | `compute_energy()` | `EnergyResult` | RMS energy, low/mid/high band ratios |
| `spectral` | `compute_spectral()` | `SpectralResult` | Centroid, bandwidth, rolloff, flatness |
| `beats` | `detect_beats()` | `BeatsResult` | Beat positions and onset rate |
| `groove` | `compute_groove()` | `GrooveResult` | Rhythmic complexity and swing |
| `structure` | `segment_structure()` | `StructureResult` | Section boundaries (intro, drop, outro) |
| `stems` | `separate_stems()` | `StemsResult` | Source separation via Demucs (ML) |
| `camelot` | `key_code_to_camelot()` | `str` | Convert key code to Camelot notation |
| `transition_score` | `score_transition()` | `TransitionResult` | Compatibility score between two tracks |
| `set_generator` | `generate_set()` | `SetResult` | Genetic algorithm for optimal track ordering |
| `pipeline` | `extract_all_features()` | `AllFeatures` | Orchestrator — runs all analyses |

**Pattern**: Each module exports one pure function returning a frozen `@dataclass(frozen=True, slots=True)`. The `pipeline` orchestrator wraps unexpected errors in `AudioAnalysisError`.

### Transition Scoring (5-component formula)

`TransitionScoringService` scores adjacent track transitions:

| Component | Weight | Description |
|-----------|--------|-------------|
| BPM compatibility | 0.30 | Exponential decay on BPM difference |
| Harmonic compatibility | 0.25 | Camelot wheel distance + harmonic density bonus |
| Energy flow | 0.20 | Sigmoid on LUFS difference (smooth energy changes) |
| Spectral similarity | 0.15 | Centroid + frequency band ratio comparison |
| Groove continuity | 0.10 | Onset rate difference |

### Set Generation (Genetic Algorithm)

`SetGenerationService` optimizes track ordering using GA with 2-opt local search:
- Population-based optimization
- Fitness = sum of transition scores + energy arc adherence
- Energy arcs: `classic`, `progressive`, `roller`, `wave`

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| | **Tracks** | |
| `GET` | `/api/v1/tracks` | List tracks (pagination, search) |
| `GET` | `/api/v1/tracks/{id}` | Get track by ID |
| `POST` | `/api/v1/tracks` | Create track |
| `PATCH` | `/api/v1/tracks/{id}` | Update track |
| `DELETE` | `/api/v1/tracks/{id}` | Delete track |
| `POST` | `/api/v1/tracks/{id}/analyze` | Run audio analysis on track |
| `POST` | `/api/v1/tracks/batch-analyze` | Batch audio analysis |
| `POST` | `/api/v1/tracks/{id}/enrich/yandex-music` | Enrich track with YM metadata |
| `GET` | `/api/v1/tracks/{id}/features` | List all feature versions |
| `GET` | `/api/v1/tracks/{id}/features/latest` | Latest audio features |
| `GET` | `/api/v1/tracks/{id}/sections` | Track sections (intro, drop, outro) |
| | **Artists** | |
| `GET/POST` | `/api/v1/artists` | List / Create artists |
| `GET/PATCH/DELETE` | `/api/v1/artists/{id}` | Get / Update / Delete artist |
| | **Labels** | |
| `GET/POST` | `/api/v1/labels` | List / Create labels |
| `GET/PATCH/DELETE` | `/api/v1/labels/{id}` | Get / Update / Delete label |
| | **Releases** | |
| `GET/POST` | `/api/v1/releases` | List / Create releases |
| `GET/PATCH/DELETE` | `/api/v1/releases/{id}` | Get / Update / Delete release |
| | **Genres** | |
| `GET/POST` | `/api/v1/genres` | List / Create genres |
| `GET/PATCH/DELETE` | `/api/v1/genres/{id}` | Get / Update / Delete genre |
| | **Keys** | |
| `GET` | `/api/v1/keys` | List all 24 musical keys |
| `GET` | `/api/v1/keys/{code}` | Get key by code |
| | **Playlists** | |
| `GET/POST` | `/api/v1/playlists` | List / Create playlists |
| `GET/PATCH/DELETE` | `/api/v1/playlists/{id}` | Get / Update / Delete playlist |
| `GET/POST` | `/api/v1/playlists/{id}/items` | List / Add playlist items |
| `DELETE` | `/api/v1/playlists/{id}/items/{item_id}` | Remove playlist item |
| | **DJ Sets** | |
| `GET/POST` | `/api/v1/sets` | List / Create DJ sets |
| `GET/PATCH/DELETE` | `/api/v1/sets/{id}` | Get / Update / Delete set |
| `GET/POST` | `/api/v1/sets/{id}/versions` | List / Create set versions |
| `GET/POST` | `/api/v1/sets/{id}/versions/{ver}/items` | List / Add version items |
| `POST` | `/api/v1/sets/{id}/generate` | Generate optimal track ordering (GA) |
| | **Transitions** | |
| `GET` | `/api/v1/transitions` | List transitions |
| `GET/DELETE` | `/api/v1/transitions/{id}` | Get / Delete transition |
| `POST` | `/api/v1/transitions/compute` | Compute transition score |
| | **Pipeline Runs** | |
| `GET/POST` | `/api/v1/runs/features` | List / Create feature extraction runs |
| `GET` | `/api/v1/runs/features/{id}` | Get feature run |
| `GET/POST` | `/api/v1/runs/transitions` | List / Create transition runs |
| `GET` | `/api/v1/runs/transitions/{id}` | Get transition run |
| | **Yandex Music** | |
| `POST` | `/api/v1/yandex-music/search` | Search Yandex Music |
| `POST` | `/api/v1/yandex-music/enrich/batch` | Batch enrich tracks from YM |
| `GET` | `/api/v1/imports/yandex/playlists` | List YM playlists |
| `POST` | `/api/v1/imports/yandex/enrich` | Enrich from YM import |

Interactive API docs at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## MCP Server

The MCP server exposes DJ workflow tools for AI-assisted set building. It uses [FastMCP 3.0](https://gofastmcp.com) with composition, structured output, and visibility control.

### Gateway Architecture

```text
DJ Set Builder (Gateway)
├── Yandex Music (namespace "ym") — ~30 tools from OpenAPI spec
├── DJ Workflows (namespace "dj") — 12 hand-written tools
│   ├── analysis:    get_playlist_status, get_track_details
│   ├── import:      import_playlist, import_tracks
│   ├── discovery:   find_similar_tracks, search_by_criteria
│   ├── setbuilder:  build_set, score_transitions, adjust_set
│   ├── export:      export_set_m3u, export_set_json
│   └── admin:       activate_heavy_mode
├── Prompts:  expand_playlist, build_set_from_scratch, improve_set
└── Resources: playlist://{id}/status, catalog://stats, set://{id}/summary
```

Transforms (`PromptsAsTools`, `ResourcesAsTools`) expose prompts and resources as tools for clients that only support the tool protocol.

### DJ Workflow Tools

| Tool | Description |
|------|-------------|
| `dj_get_playlist_status` | Playlist stats: tracks, BPM range, keys, energy, duration |
| `dj_get_track_details` | Track metadata + audio features (BPM, key, energy) |
| `dj_import_playlist` | Import from external source (stub — manual steps needed) |
| `dj_import_tracks` | Import tracks by Yandex Music IDs (stub) |
| `dj_find_similar_tracks` | LLM-assisted similar track search via `ctx.sample()` |
| `dj_search_by_criteria` | Filter local tracks by BPM/key/energy ranges |
| `dj_build_set` | Create DJ set + GA optimization |
| `dj_score_transitions` | Score all transitions in a set version (5-component formula) |
| `dj_adjust_set` | LLM-assisted set adjustment via `ctx.sample()` |
| `dj_export_set_m3u` | Export set as M3U playlist with titles and durations |
| `dj_export_set_json` | Export set as JSON with full audio features and energy curve |
| `dj_activate_heavy_mode` | Enable heavy analysis tools (hidden by default) |

### Workflow Recipes (Prompts)

Multi-step recipes that guide an AI through complete DJ workflows:

- **`expand_playlist`** — Analyze playlist profile → Find similar tracks → Build optimized set
- **`build_set_from_scratch`** — Search Yandex Music → Import tracks → Find similar → Build set
- **`improve_set`** — Score transitions → Adjust with LLM → Re-score and compare

### Running the MCP Server

Central config: [`fastmcp.json`](fastmcp.json) — auto-detected by `fastmcp run`.

```bash
# Dev: HTTP with hot-reload (edit app/mcp/ → auto-restart, clients reconnect)
make mcp-dev                    # http://127.0.0.1:9100/mcp

# Visual debugger in browser
make mcp-inspect                # http://localhost:6274

# List all registered tools (46)
make mcp-list

# Call a specific tool
make mcp-call TOOL=dj_get_track_details ARGS='{"track_id": 45}'

# Embedded in FastAPI (REST + MCP together)
make run                        # REST at /api/v1, MCP at /mcp/mcp
```

### Client Configuration

**Claude Code** — auto-connects via [`.mcp.json`](.mcp.json) when `make mcp-dev` is running:

```json
{
  "mcpServers": {
    "dj-techno": {
      "type": "url",
      "url": "http://localhost:9100/mcp"
    }
  }
}
```

**Claude Desktop** — one-command install (stdio transport):

```bash
make mcp-install-desktop
```

This writes to `~/Library/Application Support/Claude/claude_desktop_config.json` automatically.

## Project Structure

```text
app/
  main.py              # create_app() factory with lifespan + MCP mount
  config.py            # Settings(BaseSettings) from .env
  database.py          # Engine, session factory, init/close
  dependencies.py      # DbSession type alias (DI)
  errors.py            # AppError hierarchy + handlers
  models/              # 30+ SQLAlchemy ORM models
  schemas/             # Pydantic v2 request/response models
  repositories/        # BaseRepository[ModelT] + domain repos
  services/            # Business logic layer
    transition_scoring.py  # 5-component transition scoring
    set_generation.py      # Genetic algorithm for set ordering
    track_analysis.py      # Audio analysis orchestrator
  routers/             # FastAPI routers (v1/ prefix)
  middleware/           # RequestIdMiddleware
  clients/             # External API clients (Yandex Music)
  utils/
    audio/             # 16 DSP/ML analysis modules (pure functions)
  mcp/
    gateway.py         # MCP gateway (compose YM + DJ Workflows)
    types.py           # Structured output models
    dependencies.py    # FastMCP DI providers
    workflows/         # DJ workflow tools (5 modules)
    prompts/           # Workflow recipe prompts
    resources/         # Status/stats MCP resources
    yandex_music/      # OpenAPI-generated YM tools
tests/                 # pytest-asyncio, in-memory SQLite
  mcp/                 # MCP tool registration tests
  utils/               # Audio analysis tests (synthetic audio)
migrations/            # Alembic (async PostgreSQL)
data/
  schema_v6.sql        # PostgreSQL DDL source of truth
  yandex-music.yaml    # Yandex Music OpenAPI spec
docs/
  plans/               # Design docs and implementation plans
  linear.md            # Linear ↔ Git workflow (PR titles, magic words)
```

## License

Private.
