# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Energy arc adherence**: `SetCurationService.compute_energy_arc_adherence()` — compares actual set LUFS curve against template energy arc via linear interpolation, returns [0,1] adherence score. `review_set` MCP tool now computes real energy_arc_adherence (was hardcoded 0.0). Added optional `template` parameter to `review_set`. 15 unit tests.

### Fixed

- **DB data cleanup**: removed 5 orphan features, 3 duplicate provider_track_ids, 3 duplicate tracks from dev.db
- **Hookify rule**: `warn-sql-check-schema` — reminds to verify column names against `db-schema.md` before SQL queries

- **DB schema dump**: `scripts/dump_db_schema.py` + `make db-schema` — auto-generates `.claude/rules/db-schema.md` with all tables, columns, types, PKs, FKs, row counts from live SQLite DB. Path-scoped to `app/models/**`, `app/repositories/**`, `app/mcp/tools/**`, `migrations/**`.
- Документация: добавлен раздел про MCP/OpenAI контекст и рекомендованный базовый набор MCP-серверов (безопасность/принципы доступа) в `docs/data-inventory.md`.
- **Claude Code project config**: `.claude/settings.json` with codegen-bridge marketplace (`github:evgenygurin/codegen-bridge`) + plugin auto-install for team
- **SQLite MCP server**: `sqlite-db` in `.mcp.json` — direct SQL access to dev.db via `${DJ_DB_PATH}` env var (set in `.claude/settings.local.json`)
- **In-Memoria MCP server**: added to `.mcp.json` as project-level stdio server with `SURREAL_SYNC_DATA=true`
- **Documentation rule**: mandatory CHANGELOG + docs update after every change (`.claude/rules/documentation.md`)
- **Git workflow rules**: глобальные (`~/.claude/rules/git.md`) + project-specific (`.claude/rules/git.md`) — conventional commits, HEREDOC fix, Linear integration, domain scopes, safety guardrails

### Changed

- **CLAUDE.md**: добавлен `db-schema.md` в список rules, `make db-schema` в Makefile shortcuts, заметка про 12 pre-existing mypy errors
- **database.md**: добавлена секция "Schema reference" с правилами регенерации `db-schema.md`
- **Episodic Memory**: добавлено обязательное правило использования `episodic-memory:search-conversations` при старте сессии (`.claude/rules/in-memoria.md`)
- **Official Documentation**: добавлены таблицы ссылок на docs.anthropic.com (Claude Code, 12 ссылок) и docs.codegen.com (Codegen AI, 13 ссылок) в `CLAUDE.md` с требованием изучения перед работой
- **Documentation meta-rules**: добавлена секция Official Documentation Requirement в `.claude/rules/documentation.md` со ссылками на Memory, Skills, Hooks, Settings, Plugins
- **MCP rules**: добавлена ссылка на официальную MCP документацию в `.claude/rules/mcp.md`
- **`.env.example`**: добавлен `DJ_DB_PATH` для sqlite-db MCP сервера

### Fixed

- **sqlite-db MCP server (VSCode)**: `${VAR}` в `env` блоке `.mcp.json` не раскрывается в VSCode extension (known bug). Заменено на sourcing `.env` из `sh -c` команды: `. .env && npx ...`. Удалён мусорный файл `${DJ_DB_PATH}`.
- **sqlite-db MCP server**: `${DJ_DB_PATH}` in `args` array was not expanded by npx (no shell). Wrapped in `sh -c` with explicit `env` block, matching the `in-memoria` pattern. Removed spurious empty `${DJ_DB_PATH}` file created by the literal path.
- **ORM Schema Consistency** (BPM-1): Fixed 5 critical default value mismatches between SQLAlchemy models and SQL DDL
  - Added `server_default` for boolean fields: `dj_beatgrid.is_variable_tempo`, `is_canonical`
  - Added `server_default` for status fields: `tracks.status`, `feature_extraction_runs.status`, `transition_runs.status`
  - Added `server_default` for `track_audio_features_computed` fields: `is_atonal`, `is_variable_tempo`, `computed_from_asset_type`
  - Improved schema consistency from 79.5% to 90.9% coverage (40/44 tables perfect matches)

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
