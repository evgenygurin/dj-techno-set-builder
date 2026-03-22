# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Data refresh scripts**: `scripts/refresh_data.py` (audio features + sections), `scripts/refresh_ym_metadata.py` (YM metadata), `scripts/rescore_sets.py` (transition scores)
- **Makefile refresh targets**: `make refresh-features`, `make refresh-sections`, `make refresh-scores`, `make refresh-ym`, `make refresh-all`, `make refresh-dry`
- **Skills restructured**: 4 project skills переведены в официальный формат `.claude/skills/<name>/SKILL.md` с YAML frontmatter (`name`, `description`) — теперь model-invoked автоматически по контексту
- **`/delegate` slash command**: `.claude/commands/delegate.md` — запуск Codegen cloud агента из чата
- **Sub-agents**: `.claude/agents/` — 3 специализированных субагента: `db-analyst`, `code-investigator`, `dj-workflow`
- **PostToolUse hooks**: авто-форматирование Python через `ruff format` после Write/Edit + регенерация `db-schema.md` при изменении моделей
- **Energy arc adherence**: `SetCurationService.compute_energy_arc_adherence()` — energy arc scoring for DJ sets
- **Delegated Development skill v2**: vertical AI agent management with Codegen Bridge
- **Codegen Orchestration GHA**: `@codegen-sh` dispatch from PR comments
- **GHA Security scanning**: Bandit + Safety in CI, non-blocking
- **DB schema dump**: `scripts/dump_db_schema.py` + `make db-schema` — auto-generates `.claude/rules/db-schema.md`
- **Claude Code project config**: `.claude/settings.json` with codegen-bridge marketplace
- **SQLite MCP server**: `sqlite-db` in `.mcp.json` — direct SQL access to dev.db
- **In-Memoria MCP server**: added to `.mcp.json` as project-level stdio server
- **Documentation rule**: mandatory CHANGELOG + docs update after every change (`.claude/rules/documentation.md`)
- **Git workflow rules**: project-specific (`.claude/rules/git.md`) — Linear integration, domain scopes, branching model

### Changed

- **Cleanup**: removed completed TODOs, added script data files to .gitignore
- **Mood classifier**: expanded from 6 to 15 subgenres with weighted fuzzy scoring; narrowed driving/hypnotic Gaussians (sigma=0.15) to prevent catch-all dominance
- **audio.md**: added "Mood classifier (15 subgenres)" section with discriminators table, anti-catch-all penalties, subgenre playlists info
- **CLAUDE.md**: секция Workflow skills обновлена; добавлены `db-schema.md`, `make db-schema`, заметка про 12 pre-existing mypy errors; таблицы ссылок на docs.anthropic.com и docs.codegen.com
- **database.md**: добавлена секция "Schema reference" с правилами регенерации `db-schema.md`
- **Episodic Memory**: добавлено обязательное правило использования `episodic-memory:search-conversations` при старте сессии
- **Documentation meta-rules**: добавлена секция Official Documentation Requirement
- **MCP rules**: добавлена ссылка на официальную MCP документацию
- **`.env.example`**: добавлен `DJ_DB_PATH` для sqlite-db MCP сервера

### Fixed

- **mypy config**: added `librosa.*` to `ignore_missing_imports` to fix CI lint failures
- **API duplicate queries**: removed duplicate `features_repo.list_all()` call in `SetGenerationService`
- **hardcoded provider ID**: replaced magic number `_PROVIDER_ID = 4` with dynamic lookup from DB
- **CI workflows**: Fixed YAML syntax by quoting 'on' keyword in GitHub Actions workflows
- **test_filter_tracks_by_energy**: fixed test to use correct energy_mean values (0.0-1.0 scale) instead of LUFS range
- **NULL beat features**: deleted 98 v1.0 pipeline rows with NULL beat features; re-analyzed via `refresh_data.py` with v2.1b6 pipeline
- **Hooks**: убран `NotebookEdit` из matcher, убран `2>/dev/null` для видимости ошибок
- **Skills discovery**: старые плоские `.md` файлы перенесены в `SKILL.md` в директориях
- **Rules loading**: создан `.claude/CLAUDE.md` с `@`-импортами для всех `.claude/rules/*.md`
- **Ruff lint fix**: 122→0 violations in scripts/ and migrations/
- **DB data cleanup**: removed orphan features, duplicate tracks from dev.db
- **Router count**: CLAUDE.md + api.md updated 13→15 (actual count)
- **sqlite-db MCP server**: fixed `${VAR}` expansion — wrapped in `sh -c` with explicit `env` block
- **ORM Schema Consistency** (BPM-1): Fixed 5 critical default value mismatches between SQLAlchemy models and SQL DDL; improved consistency from 79.5% to 90.9%
- **numpy compatibility**: pinned `numpy<2.4` in pyproject.toml — numba (via librosa) incompatible with NumPy 2.4
- **Test pollution (23 failures → 0)**: replaced `insert()` with `merge()` in 7 test files to handle pre-existing rows from session-scoped engine; used `index`-based feature values instead of `track_id` to avoid CHECK constraint violations; made count assertions relative
- **typing_extensions_patch.py**: fixed 14 ruff violations (whitespace, imports, PEP 695, SIM102)
- **SQL injection in delivery.py** (Issue #64, P0-1): replaced f-string SQL with ORM `select().where(.in_())` query
- **DI bypass in delivery.py** (Issue #64, P0-2): `_sync_to_ym()` now receives session via DI instead of importing `session_factory` directly
- **BaseRepository.update() field validation** (Issue #64, P0-3): validates field names against model columns, rejects unknown fields with `ValueError`
- **Secrets in repr** (Issue #64, P0-5): added `repr=False` to `yandex_music_token`, `anthropic_api_key`, `sentry_dsn` in Settings
- **Broad except narrowing** (Issue #64, P0-4): narrowed 9 `except Exception` to specific types in services, MCP tools, routers
- **GA artist variety** (Issue #64, P1-7): wired `artist_id` from `track_artists` into GA fitness — variety scoring now functional
- **YM rate limit lock** (Issue #64, P1-10): added `asyncio.Lock` to `_rate_limit()` preventing concurrent bypass
- **BaseRepository.get_by_ids()** (Issue #64, P1-8): batch-fetch by PK with `pk.in_()` — prevents N+1 queries
- **TypeForm consolidation** (Issue #64, P2-13): single source in `_compat.py`, called from `app/__init__.py`; removed `typing_extensions_patch.py`
- **SetGenerationService logging** (Issue #64, P3-22): added entry/result logging to `generate()`
- **Outdated TODO** (Issue #64, P3-24): updated `_build_transition_matrix` docstring — no longer marked as TODO

## [0.2.0] - 2026-02-15

### Added

- **MCP Gateway** (FastMCP 3.0): composite server mounting Yandex Music (`ym_`) and DJ Workflows (`dj_`) sub-servers with ~46 tools total
- **Yandex Music MCP sub-server**: ~30 tools auto-generated from OpenAPI spec via `FastMCP.from_openapi()` with RouteMap filtering, snake_case naming, and circular `$ref` patching
- **12 DJ Workflow tools** across 5 modules:
  - Analysis: `get_playlist_status`, `get_track_details`
  - Import: `import_playlist`, `import_tracks` (stubs with manual-step guidance)
  - Discovery: `find_similar_tracks` (LLM-assisted via `ctx.sample()`), `search_by_criteria` (BPM/key/energy filter)
  - Set builder: `build_set` (GA optimization), `score_transitions` (5-component scoring), `adjust_set` (LLM-assisted)
  - Export: `export_set_m3u`, `export_set_json` with full audio feature data
- **MCP DI system**: 9 dependency providers using FastMCP `Depends()` — session, services, repositories wired automatically
- **MCP prompts**: 3 workflow recipe prompts (`expand_playlist`, `build_set_from_scratch`, `improve_set`)
- **MCP resources**: playlist status, catalog stats, and set summary with DI-based service injection
- **Visibility control**: `activate_heavy_mode` tool + `disable(tags={"heavy"})` for resource-intensive tools
- **Transforms**: `PromptsAsTools` + `ResourcesAsTools` on gateway for tool-only MCP clients
- **FastMCP dev workflow**: `fastmcp.json` config, `.mcp.json` for Claude Code, 6 Makefile targets (`mcp-dev`, `mcp-inspect`, `mcp-list`, `mcp-call`, `mcp-install-desktop`, `mcp-install-code`), HTTP hot-reload on port 9100
- **MCP test infrastructure**: shared fixtures (`conftest.py`), 12 in-memory `Client(server)` integration tests, two-layer testing (metadata + invocation)
- **10 Pydantic structured output types** in `app/mcp/types.py`
- **Modular CLAUDE.md rules**: split into 6 path-specific `.claude/rules/*.md` files (api, database, audio, testing, mcp, documentation)

### Changed

- **MCP mounting in FastAPI**: `create_dj_mcp()` gateway mounted at `/mcp/mcp` via ASGI lifespan composition
- **Refactored MCP tests**: all 10 test files use shared conftest fixtures instead of inline imports
- **`AudioFeaturesService.list_all()`**: added to avoid direct repo access in `search_by_criteria`
- **Export enrichment**: M3U and JSON exports now include real track titles and durations via `TrackService`

### Fixed

- **`Context` parameter**: made non-optional in all tools (was `= None # type: ignore`)
- **`PlaylistStatus.duration_minutes`**: now calculated from track metadata instead of hardcoded
- **OpenAPI circular `$ref`**: Genre→Genre, Artist→Track→Artist, Album→Track→Album cycles resolved in `_patch_spec()`
- **`validate_output=False`**: added to YM MCP server to prevent response schema validation failures

## [0.1.0] - 2026-02-12

### Added

- **Project scaffold**: FastAPI app factory with asynccontextmanager lifespan, pydantic-settings, uv
- **Layered architecture**: Router -> Service -> Repository -> AsyncSession flow with FastAPI DI
- **Versioned API routes**: `/api/v1/tracks` CRUD endpoints (list, get, create, update, delete)
- **Generic repository**: `BaseRepository[ModelT]` with PEP 695 type params — get_by_id, list, create, update, delete
- **Error handling**: `AppError` hierarchy (NotFoundError, ValidationError, ConflictError) with global JSON handlers
- **Middleware**: RequestIdMiddleware — contextvars-based `X-Request-ID` injection
- **30+ ORM models** matching `schema_v6.sql` PostgreSQL DDL:
  - Catalog: Track, Artist, Label, Release, Genre + junction tables (TrackArtist, TrackRelease, TrackGenre)
  - Providers: Provider, ProviderTrackId, RawProviderResponse
  - Metadata: SpotifyMetadata, SpotifyAudioFeatures, SpotifyAlbumMetadata, SpotifyArtistMetadata, SpotifyPlaylistMetadata, SoundCloudMetadata, BeatportMetadata
  - Pipeline: FeatureExtractionRun, TransitionRun, AudioAsset
  - Harmony: Key (24 keys, deterministic constraint), KeyEdge (compatibility graph)
  - Features: TrackAudioFeaturesComputed (~35 DSP/ML columns with CHECK constraints)
  - Sections: TrackSection (structural segmentation)
  - Timeseries: TrackTimeseriesRef (frame-level data pointers)
  - Transitions: TransitionCandidate (pre-filter), Transition (full scoring)
  - Embeddings: EmbeddingType (registry), TrackEmbedding (pgvector)
  - DJ layer: DjLibraryItem, DjBeatgrid, DjBeatgridChangePoint, DjCuePoint, DjSavedLoop, DjPlaylist, DjPlaylistItem, DjAppExport
  - Sets: DjSet, DjSetVersion, DjSetConstraint, DjSetItem, DjSetFeedback
- **8 domain enums**: ArtistRole, SectionType, CueKind, SourceApp, TargetApp, AssetType, RunStatus, FeedbackType
- **Mixins**: TimestampMixin (created_at + updated_at), CreatedAtMixin (append-only tables)
- **Pydantic schemas**: BaseSchema (from_attributes + extra=forbid), TrackCreate/Read/Update/List
- **Test infrastructure**: pytest-asyncio with in-memory SQLite, 88 tests covering all models + constraints + API
- **Tooling**: ruff (E/F/W/I/N/UP/B/A/SIM/PLW/RUF), mypy strict with pydantic plugin, Alembic async migrations
- **DB DDL**: `schema_v6.sql` — full PostgreSQL schema with pgvector, btree_gist, pg_trgm, triggers, functions, views
