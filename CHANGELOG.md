# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Section-based mix points**: `_get_mix_points()` helper populates `mix_in_ms`/`mix_out_ms` from `track_sections` intro/outro data as fallback when not set on items
- **Batch section loading**: `SectionsRepository.get_latest_by_track_ids()` used in `score_consecutive_transitions()` — single IN-query instead of N+1
- **Crossfader FX legend** in cheat sheet footer: 8 FX type descriptions for quick DJ reference

### Changed

- **TransitionType enum**: expanded from 7 generic to 16 real djay Pro AI Crossfader FX types (9 Classic + 7 Neural Mix) in `app/utils/audio/_types.py`
- **Transition recommender**: rewritten as 13-rule priority-based algorithm with mood-aware + position-aware logic for all 16 FX types (`app/services/transition_type.py`)
- **`recommend_transition()` signature**: `camelot_compatible: bool` → `camelot_dist: int`, added `set_position`, `energy_direction`, `mood` params
- **`score_consecutive_transitions()`**: derives `set_position`, `energy_direction` per pair; populates `djay_bars`, `djay_bpm_mode`, `mix_out_ms`, `mix_in_ms`
- **Cheat sheet djay block**: expanded from single line to multi-line box with FX name, bars, BPM mode, mix points, alt type, reason (tree-character formatting)

## [0.3.0] - 2026-03-22

### Added

- **Iron Laws**: все 5 скиллов дополнены Iron Law + Rationalization Table + Red Flags по паттерну obra/superpowers
- **Agent `emergency-protocols`**: диагностика MCP/DB/iCloud/CI проблем с triage-таблицей
- **Agent `pr-reviewer`**: двухстадийный review PR от Codegen агентов (spec compliance → code quality)
- **Command `/setup-check`**: верификация окружения (DB, MCP, env vars, deps, iCloud)
- **Command `/delegate` улучшен**: 5 примеров типичных задач для делегирования
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

- **Skills дисциплина**: каждый скилл теперь содержит жёсткое ограничение (Iron Law) и таблицу типичных отговорок
- **Memory `superpowers-patterns.md`**: обновлён с полным анализом v5.0.5 — Iron Laws, CSO, Two-Stage Review, Skill Chaining
- **Cleanup**: removed completed TODOs, added script data files to .gitignore
- **Mood classifier**: expanded from 6 to 15 subgenres with weighted fuzzy scoring; narrowed driving/hypnotic Gaussians (sigma=0.15) to prevent catch-all dominance
- **audio.md**: added "Mood classifier (15 subgenres)" section with discriminators table, anti-catch-all penalties, subgenre playlists info
- **CLAUDE.md**: секция Workflow skills обновлена; добавлены `db-schema.md`, `make db-schema`; таблицы ссылок на docs.anthropic.com и docs.codegen.com; mypy status updated (12 errors → 0)
- **database.md**: добавлена секция "Schema reference" с правилами регенерации `db-schema.md`
- **Episodic Memory**: добавлено обязательное правило использования `episodic-memory:search-conversations` при старте сессии
- **Documentation meta-rules**: добавлена секция Official Documentation Requirement
- **MCP rules**: добавлена ссылка на официальную MCP документацию
- **`.env.example`**: добавлен `DJ_DB_PATH` для sqlite-db MCP сервера
- **Documentation sync**: tool counts verified via runtime (52 DJ + 28 YM + 4 transforms = 84 total); db-schema.md regenerated; audio modules 21→22 (greedy_chain); Pydantic types 36→37 (DistributeResult)
- **CHANGELOG format**: standardized to Keep a Changelog (removed non-standard "Previously Added", merged duplicate "Changed")
- **macOS compatibility rules**: added to documentation.md (lsof not fuser, stat -f not stat -c)

### Fixed

- **`ctx: Context` defaults**: fixed 7 MCP tools with `ctx: Context | None = None` → `ctx: Context` (download.py, sync.py ×6)
- **Broad exceptions narrowed**: 4 `except Exception` in curation_discovery.py → `except (httpx.HTTPError, TimeoutError, ValueError)`
- **Hardcoded `provider_id=4`**: replaced with `_YM_PROVIDER_ID` constant in 9 locations (curation_discovery.py, playlist.py, sync.py, complete_workflow.py)
- **Stale tool names**: fixed `ym_search_tracks` → `ym_search_yandex_music` in prompts (runtime bug); `dj_get_track_details` → `dj_get_track`, `dj_get_playlist_status` → `dj_get_playlist` in docs
- **`make mcp-list` crash**: removed `--skip-env` from mcp-list/mcp-call targets (YM client init fails without .env)
- **CI PYTHONPATH**: removed hardcoded `python3.13` path (no longer needed with `_compat.py` TypeForm patch)
- **Missing configs**: added `DJ_LIBRARY_PATH` to `.env.example`; added `DATABASE_URL` + `DJ_LIBRARY_PATH` to `fastmcp.json` deployment env
- **`.gitignore`**: added `CLAUDE.local.md`
- **`find_similar_tracks`**: marked DEPRECATED (always returns 0 candidates — real pipeline in `discover_candidates`/`expand_playlist_full`)
- **mypy status**: updated from "12 pre-existing errors" to "0 errors" across 5 documentation files

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
- **Docs sync with code** (Issue #64, P1-1): fixed 6 incorrect tool names in skills/agents (`dj_get_track_details` → `dj_get_track`, `dj_search_by_criteria` → `dj_filter_tracks`, `dj_compute_audio_features` → `dj_analyze_track`); updated tool counts 41→44 across CLAUDE.md, mcp.md, agents; fixed "6 mood categories" → "15" in dj-workflow agent
- **Skills token budget** (Issue #64): reduced 3 oversized skills to CSO-compliant sizes — audio-analysis (922→362 words), mcp-tool-dev (938→318), delegated-development (1055→351). Eliminated duplication with `.claude/rules/` files

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
