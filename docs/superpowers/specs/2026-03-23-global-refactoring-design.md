# Global Refactoring: Layered Architecture Design

> **Status**: Draft
> **Date**: 2026-03-23
> **Scope**: Full restructuring of `app/` — 211 Python files, ~24k LOC
> **Entry points preserved**: REST API, MCP Gateway, CLI, Scripts

---

## 1. Problem Statement

The current codebase has grown organically into a flat-layered structure where:

- **29 service files** and **21 repository files** sit in flat directories with no domain grouping
- **MCP tools contain 1500+ lines of business logic** (raw SQL, model imports, TrackData construction) that cannot be reused from CLI or scripts
- **Two `TrackFeatures` classes** with the same name and different structure coexist (`_types.py:161` DSP-oriented vs `transition_scoring.py:32` scoring-oriented)
- **Two YM clients** (`clients/yandex_music.py` thin + `services/yandex_music_client.py` with rate limiting) — code has a `TODO: Consolidate both`
- **Two scoring modules** (`utils/audio/transition_score.py` v1 + `services/transition_scoring.py` v2)
- **Two M3U generators** (`services/set_export.py:export_m3u()` full + `mcp/tools/delivery.py:_write_m3u8()` simplified)
- **God Object** `set_generator.py` at 912 lines (GA engine + fitness + crossover + mutation + config + energy arcs)
- **Leaky abstractions** — `set_generation.py._load_artist_map()` bypasses repo via `self.features_repo.session.execute()`
- **13 direct repository imports** in MCP tools, bypassing service/DI layer
- **6 files with raw SQL** (`select()`) in MCP tools layer
- **Triple-duplicated pattern** — "load ORM features → classify mood → build TrackData" in `set_generation.py`, `mcp/tools/setbuilder.py`, `mcp/tools/curation.py`
- **Two DI systems** — `app/dependencies.py` (FastAPI) + `app/mcp/dependencies.py` (FastMCP) build identical services
- **Inconsistent transaction management** — REST commits in router, MCP commits in `get_session()` context manager

---

## 2. Design Principles

| Principle | Application |
|-----------|-------------|
| **KISS** | Minimal nesting depth (max 4 levels). No abstract interfaces for single implementations. No `domain/ports/` — Python protocols + duck typing suffice. |
| **DRY** | Merge all 6 identified duplication pairs. Centralized converters + factories. |
| **SRP** | Each module has one reason to change. MCP tools = thin adapters. Services = orchestration. Domain = pure logic. |
| **OCP** | Strategy pattern for optimizer selection (GA/greedy). Plugin-style platform adapters. |
| **LSP** | Single `TrackFeatures` type with optional fields replaces two incompatible classes. |
| **ISP** | Services receive specific repos, not fat "unit of work" objects. SetGenerationService gets only what it needs. |
| **DIP** | Adapters depend on services, never reverse. Domain depends on nothing. Factories centralize construction. |

### GoF Patterns Applied

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Factory Method** | `services/_factories.py` | Centralized service construction — both FastAPI and FastMCP DI call the same factories |
| **Strategy** | `domain/setbuilder/` | GA vs Greedy optimizer. Different energy arc shapes. Pluggable fitness components. |
| **Facade** | `services/audio/scoring.py` | `UnifiedTransitionScoringService` hides Camelot lookup + feature loading + domain scorer |
| **Template Method** | `core/base/repository.py` | `BaseRepository` defines CRUD skeleton, subclasses set `model` class attribute |
| **Adapter** | `api/`, `mcp/`, `cli/` | Each adapter translates between external protocol and application services |
| **Composite** | `mcp/gateway.py` | Gateway composes YM + DJ sub-servers via FastMCP mount |
| **Builder** | `domain/setbuilder/genetic/engine.py` | GA builds population → selects → crosses → mutates → evaluates step by step |

---

## 3. Layer Architecture

```bash
┌──────────────────────────────────────────────────────┐
│  LAYER 5: ADAPTERS                                   │
│  api/  •  mcp/  •  cli/                              │
│  Thin wrappers: input mapping → service call →       │
│  output formatting. Progress, elicitation, errors.   │
├──────────────────────────────────────────────────────┤
│  LAYER 4: APPLICATION                                │
│  services/  •  schemas/                              │
│  Orchestration: coordinate domain + persistence.     │
│  Transaction boundaries. External API clients.       │
│  Factory methods for DI unification.                 │
├──────────────────────────────────────────────────────┤
│  LAYER 3: PERSISTENCE                                │
│  models/  •  repositories/                           │
│  ORM definitions. SQL queries. Data access.          │
│  Converters: ORM ↔ Domain types.                     │
├──────────────────────────────────────────────────────┤
│  LAYER 2: DOMAIN                                     │
│  domain/                                             │
│  Pure business logic, algorithms, value objects.     │
│  ZERO framework imports. Unit-testable in isolation. │
├──────────────────────────────────────────────────────┤
│  LAYER 1: CORE                                       │
│  core/                                               │
│  Config, errors, base abstractions, middleware.      │
└──────────────────────────────────────────────────────┘

Dependencies: STRICTLY DOWNWARD. Layer N → Layer N-1, ..., 1. Never upward.
```

### Strict Import Rules

| Layer | CAN import | CANNOT import |
|-------|-----------|---------------|
| **L1 core/** | stdlib, pydantic, sqlalchemy.orm (Base only) | anything from `app/` except itself |
| **L2 domain/** | stdlib, numpy, L1 (errors only) | sqlalchemy, fastapi, fastmcp, L3, L4, L5 |
| **L3 models/** | L1 (base model), L2 (enums only) | L4, L5 |
| **L3 repositories/** | L1 (base repo), L3 models/ | L4, L5 |
| **L4 services/** | L1, L2, L3 | L5 |
| **L4 schemas/** | L1 (base schema) | L3 models, L5 |
| **L5 api/** | L1–L4 | mcp/, cli/ |
| **L5 mcp/** | L1–L4 | api/, cli/ |
| **L5 cli/** | L1–L4 | api/, mcp/ |

### Enforcement via import-linter

```toml
# pyproject.toml
[tool.importlinter]
root_package = "app"

[[tool.importlinter.contracts]]
name = "Domain has zero framework dependencies"
type = "forbidden"
source_modules = ["app.domain"]
forbidden_modules = [
    "sqlalchemy", "fastapi", "fastmcp", "httpx",
    "app.models", "app.repositories", "app.services",
    "app.schemas", "app.api", "app.mcp", "app.cli",
]

[[tool.importlinter.contracts]]
name = "Persistence cannot import application or adapters"
type = "forbidden"
source_modules = ["app.models", "app.repositories"]
forbidden_modules = ["app.services", "app.schemas", "app.api", "app.mcp", "app.cli"]

[[tool.importlinter.contracts]]
name = "Application cannot import adapters"
type = "forbidden"
source_modules = ["app.services", "app.schemas"]
forbidden_modules = ["app.api", "app.mcp", "app.cli"]

[[tool.importlinter.contracts]]
name = "Adapters are independent"
type = "independence"
modules = ["app.api", "app.mcp", "app.cli"]
```

---

## 4. Target Directory Structure

```bash
app/
├── __init__.py                    # TypeForm compat patch
├── main.py                        # FastAPI app factory
│
├── core/                          # ══ LAYER 1: Foundation ══
│   ├── __init__.py
│   ├── config.py                  # Settings(BaseSettings) — unchanged
│   ├── database.py                # engine, session_factory, init_db(), get_session()
│   ├── errors.py                  # AppError → NotFoundError, ValidationError, ConflictError
│   ├── _compat.py                 # TypeForm patch
│   ├── base/
│   │   ├── __init__.py            # re-exports: Base, BaseRepository, BaseService, BaseSchema
│   │   ├── model.py               # Base(DeclarativeBase), TimestampMixin, CreatedAtMixin
│   │   ├── repository.py          # BaseRepository[ModelT] — Template Method pattern
│   │   ├── service.py             # BaseService (self.logger)
│   │   └── schema.py              # BaseSchema(from_attributes=True, extra="forbid")
│   └── middleware/
│       ├── __init__.py            # apply_middleware()
│       └── request_id.py
│
├── domain/                        # ══ LAYER 2: Pure Business Logic ══
│   ├── __init__.py                #    ZERO: sqlalchemy, fastapi, fastmcp, httpx
│   │
│   ├── audio/                     # Audio analysis & scoring
│   │   ├── __init__.py
│   │   ├── types.py               # ★ ЕДИНЫЙ TrackFeatures (слияние двух),
│   │   │                          #   AudioData, BpmResult, KeyResult, LoudnessResult,
│   │   │                          #   EnergyResult, SpectralResult, BeatsResult, GrooveResult,
│   │   │                          #   MfccResult, StemsResult, SectionResult, TransitionScore,
│   │   │                          #   TransitionRecommendation, TransitionType, HardConstraints
│   │   ├── errors.py              # AudioError, AudioValidationError, AudioAnalysisError
│   │   ├── camelot.py             # camelot_distance(), key_code_to_camelot(), is_compatible()
│   │   ├── dsp/                   # Pure DSP functions (1 module = 1 function)
│   │   │   ├── __init__.py        # re-exports: detect_bpm, detect_key, etc.
│   │   │   ├── bpm.py             # detect_bpm() → BpmResult
│   │   │   ├── key_detect.py      # detect_key() → KeyResult
│   │   │   ├── loudness.py        # measure_loudness() → LoudnessResult
│   │   │   ├── energy.py          # compute_energy() → EnergyResult
│   │   │   ├── spectral.py        # compute_spectral() → SpectralResult
│   │   │   ├── beats.py           # detect_beats() → BeatsResult
│   │   │   ├── groove.py          # compute_groove() → GrooveResult
│   │   │   ├── structure.py       # segment_structure() → StructureResult
│   │   │   ├── stems.py           # separate_stems() → StemsResult
│   │   │   ├── mfcc.py            # extract_mfcc() → MfccResult
│   │   │   ├── loader.py          # load_audio(), validate_audio()
│   │   │   └── pipeline.py        # extract_all_features() — orchestrator
│   │   ├── scoring/               # Transition scoring (pure math)
│   │   │   ├── __init__.py        # re-exports: TransitionScoringService
│   │   │   ├── service.py         # TransitionScoringService (6 components, Phase 2)
│   │   │   │                      #   ★ MERGE of utils/transition_score.py (v1)
│   │   │   │                      #     + services/transition_scoring.py (v2)
│   │   │   ├── matrix.py          # build_matrix_two_tier() — NxN scoring
│   │   │   └── transition_type.py # recommend_transition() → TransitionRecommendation
│   │   └── classifier/            # Mood classification
│   │       ├── __init__.py        # re-exports: classify_track, TrackMood
│   │       ├── moods.py           # TrackMood(StrEnum), 15 subgenres, intensity map
│   │       └── classifier.py      # classify_track() → MoodClassification
│   │
│   ├── setbuilder/                # DJ set generation
│   │   ├── __init__.py
│   │   ├── types.py               # TrackData, GAConfig, GAConstraints, GAResult,
│   │   │                          #   EnergyArcType, GreedyChainResult, CandidateTrack
│   │   ├── genetic/               # ★ SPLIT of set_generator.py (912→4×~200)
│   │   │   ├── __init__.py        # re-exports: GeneticSetGenerator
│   │   │   ├── engine.py          # GeneticSetGenerator class (run, population, selection)
│   │   │   ├── fitness.py         # Fitness functions + variety_score + template_slot_fit
│   │   │   ├── operators.py       # _order_crossover, _mutate, _mutate_replace
│   │   │   └── local_search.py    # _two_opt, _relocate_worst
│   │   ├── greedy.py              # build_greedy_chain() → GreedyChainResult
│   │   ├── energy_arcs.py         # Breakpoints + target_energy_curve() + lufs_to_energy()
│   │   ├── templates.py           # SetTemplate, SetSlot, TemplateName, get_template()
│   │   ├── curation.py            # SetCurationService (classify + select — pure, no DB)
│   │   └── export/                # ★ MERGE of set_export.py + delivery._write_m3u8
│   │       ├── __init__.py        # re-exports: export_m3u, export_json, export_rekordbox
│   │       ├── m3u.py             # export_m3u() — ЕДИНСТВЕННЫЙ генератор M3U
│   │       ├── json_guide.py      # export_json_guide()
│   │       ├── cheat_sheet.py     # generate_cheat_sheet()
│   │       ├── rekordbox.py       # export_rekordbox_xml()
│   │       └── types.py           # RekordboxTrackData
│   │
│   └── platform/                  # Platform-agnostic types & parsing
│       ├── __init__.py
│       ├── types.py               # ParsedYmTrack
│       ├── parser.py              # parse_ym_track() — defensive dict→dataclass
│       ├── filters.py             # _is_techno(), _has_bad_version(), _MIN_DURATION_MS
│       └── protocol.py            # PlatformCapability(Enum), MusicPlatform(Protocol)
│
├── models/                        # ══ LAYER 3a: ORM Models ══
│   ├── __init__.py                # Re-imports all models for Base.metadata.create_all
│   ├── enums.py                   # ArtistRole, SectionType, CueKind, SourceApp,
│   │                              #   TargetApp, AssetType, RunStatus, FeedbackType
│   ├── catalog.py                 # Track, Artist, Genre, Label, Release, TrackArtist,
│   │                              #   TrackGenre, TrackRelease (unchanged)
│   ├── audio.py                   # ★ MERGE of features.py + sections.py + harmony.py +
│   │                              #   transitions.py + runs.py + embeddings.py + timeseries.py
│   ├── dj.py                      # DjSet*, DjPlaylist*, DjLibraryItem, DjBeatgrid*,
│   │                              #   DjCuePoint, DjSavedLoop, DjAppExport, AudioAsset
│   │                              #   (merge of current sets.py + dj.py + assets.py)
│   └── platform.py                # ★ MERGE of providers.py + ingestion.py +
│                                  #   metadata_yandex.py + metadata_spotify.py +
│                                  #   metadata_soundcloud.py + metadata_beatport.py
│
├── repositories/                  # ══ LAYER 3b: Data Access ══
│   ├── __init__.py
│   ├── base.py                    # re-export core/base/repository.py
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── tracks.py              # TrackRepository + get_artists_for_tracks
│   │   │                          #   + ★ NEW get_primary_artist_ids(track_ids)
│   │   │                          #     (moved from set_generation._load_artist_map)
│   │   ├── artists.py
│   │   ├── genres.py
│   │   ├── labels.py
│   │   └── releases.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── features.py            # AudioFeaturesRepository
│   │   ├── sections.py            # SectionsRepository
│   │   ├── runs.py                # FeatureRunRepository, TransitionRunRepository
│   │   ├── harmony.py             # KeyEdgeRepository
│   │   ├── transitions.py         # TransitionRepository
│   │   └── candidates.py          # CandidateRepository
│   ├── dj/
│   │   ├── __init__.py
│   │   ├── sets.py                # DjSetRepository, DjSetVersionRepository, DjSetItemRepository
│   │   ├── playlists.py           # DjPlaylistRepository, DjPlaylistItemRepository
│   │   ├── library_items.py       # DjLibraryItemRepository
│   │   ├── beatgrid.py
│   │   ├── cue_points.py
│   │   └── loops.py
│   └── platform/
│       ├── __init__.py
│       ├── providers.py           # ProviderRepository
│       └── yandex.py              # YandexMetadataRepository
│
├── services/                      # ══ LAYER 4a: Application Services ══
│   ├── __init__.py
│   ├── _factories.py              # ★ ЕДИНЫЙ DI: create_track_service(session), etc.
│   │                              #   Both FastAPI and FastMCP DI call these factories.
│   ├── _converters.py             # ★ ORM → Domain type conversions (single source of truth)
│   │                              #   orm_to_track_features(feat, sections?) → domain.TrackFeatures
│   │                              #   orm_to_track_data(feat, mood?, artist?) → domain.TrackData
│   │                              #   (eliminates 3 duplicate patterns)
│   │
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── tracks.py              # TrackService
│   │   ├── artists.py             # ArtistService
│   │   ├── genres.py              # GenreService
│   │   ├── labels.py              # LabelService
│   │   ├── releases.py            # ReleaseService
│   │   └── keys.py                # KeyService
│   │
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── features.py            # AudioFeaturesService
│   │   ├── analysis.py            # TrackAnalysisService (DSP pipeline → DB persist)
│   │   ├── scoring.py             # UnifiedTransitionScoringService (Facade)
│   │   │                          #   + CamelotLookupService
│   │   ├── persistence.py         # TransitionPersistenceService
│   │   ├── transitions.py         # TransitionService (CRUD)
│   │   └── mix_points.py          # MixPointsService
│   │
│   ├── dj/
│   │   ├── __init__.py
│   │   ├── sets.py                # DjSetService (CRUD)
│   │   ├── playlists.py           # DjPlaylistService (CRUD + items)
│   │   ├── generation.py          # SetGenerationService (orchestrate GA + scoring + DB)
│   │   ├── delivery.py            # ★ NEW: SetDeliveryService
│   │   │                          #   (extracted from mcp/tools/delivery.py — 518 lines → service)
│   │   │                          #   score → copy files → M3U/JSON/cheat_sheet → optional YM sync
│   │   ├── curation.py            # Curation orchestrator (DB → domain.curation → results)
│   │   └── export.py              # Export orchestrator (load items → domain.export → output)
│   │
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── yandex/
│   │   │   ├── __init__.py
│   │   │   ├── client.py          # ★ ЕДИНЫЙ YandexMusicClient (rate limiting + download
│   │   │   │                      #   + search + playlist ops). MERGE of 2 clients.
│   │   │   ├── importer.py        # ImportYandexService
│   │   │   ├── enrichment.py      # YandexMusicEnrichmentService
│   │   │   └── discovery.py       # ★ NEW: CandidateDiscoveryService
│   │   │                          #   (extracted from mcp/tools/curation_discovery.py — 563 lines)
│   │   │                          #   discover_candidates(), expand_playlist(), expand_full()
│   │   └── sync/
│   │       ├── __init__.py
│   │       ├── engine.py          # SyncEngine
│   │       ├── diff.py            # Diff algorithm
│   │       └── track_mapper.py    # DbTrackMapper
│   │
│   └── library/
│       ├── __init__.py
│       └── download.py            # DownloadService
│
├── schemas/                       # ══ LAYER 4b: API Contracts ══
│   ├── __init__.py
│   ├── base.py                    # re-export core/base/schema.py
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── tracks.py              # TrackCreate, TrackRead, TrackUpdate, TrackList
│   │   ├── artists.py
│   │   ├── genres.py
│   │   ├── labels.py
│   │   └── releases.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── features.py            # AudioFeaturesRead, AudioFeaturesList
│   │   ├── analysis.py
│   │   ├── sections.py
│   │   ├── runs.py
│   │   ├── keys.py
│   │   ├── transitions.py
│   │   └── candidates.py
│   ├── dj/
│   │   ├── __init__.py
│   │   ├── sets.py                # DjSet/Version/Item schemas
│   │   ├── playlists.py
│   │   ├── generation.py          # SetGenerationRequest, SetGenerationResponse
│   │   └── curation.py
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── imports.py
│   │   └── yandex.py
│   └── errors.py                  # ErrorResponse schema
│
├── api/                           # ══ LAYER 5a: REST Adapter ══
│   ├── __init__.py                # register_routers(app)
│   ├── dependencies.py            # FastAPI DI → calls services/_factories.py
│   ├── openapi.py                 # RESPONSES_GET, RESPONSES_CREATE, etc.
│   ├── health.py
│   └── v1/
│       ├── __init__.py            # v1_router
│       ├── tracks.py
│       ├── artists.py
│       ├── genres.py
│       ├── labels.py
│       ├── releases.py
│       ├── features.py
│       ├── sections.py
│       ├── keys.py
│       ├── transitions.py
│       ├── runs.py
│       ├── sets.py
│       ├── playlists.py
│       ├── analysis.py
│       ├── imports.py
│       └── yandex_music.py
│
├── mcp/                           # ══ LAYER 5b: MCP Adapter ══
│   ├── __init__.py                # create_dj_mcp()
│   ├── gateway.py                 # Composite pattern: mount YM + DJ sub-servers
│   ├── dependencies.py            # FastMCP DI → calls services/_factories.py
│   ├── tools/                     # THIN handlers (each ≤ 80 lines)
│   │   ├── __init__.py            # create_workflow_mcp(), register all
│   │   ├── catalog.py             # track + search CRUD tools
│   │   ├── audio.py               # features, analysis, scoring tools
│   │   ├── sets.py                # set CRUD + build + rebuild + cheat_sheet
│   │   ├── playlists.py           # playlist CRUD + populate
│   │   ├── delivery.py            # deliver_set (progress + elicitation + svc call)
│   │   ├── curation.py            # classify, review, gaps, distribute, discover, expand
│   │   ├── sync.py                # sync tools
│   │   └── admin.py               # activate_heavy, activate_ym_raw, list_platforms
│   ├── types/                     # MCP-specific response Pydantic models
│   │   ├── __init__.py
│   │   ├── entities.py            # TrackSummary, PlaylistSummary, SetSummary, etc.
│   │   ├── responses.py           # PaginationInfo, SearchResponse, EntityListResponse, etc.
│   │   ├── workflows.py           # SetBuildResult, TransitionScoreResult, DeliveryResult, etc.
│   │   └── curation.py            # ClassifyResult, SetReviewResult, LibraryGapResult, etc.
│   ├── helpers/                   # MCP-specific utilities
│   │   ├── __init__.py
│   │   ├── refs.py                # ParsedRef, parse_ref(), RefType
│   │   ├── resolve.py             # resolve_local_id()
│   │   ├── pagination.py          # encode_cursor, decode_cursor
│   │   ├── response.py            # wrap_list, wrap_detail, wrap_action
│   │   ├── converters.py          # track_to_summary, set_to_summary (ORM → MCP types)
│   │   ├── entity_finder.py       # TrackFinder, SetFinder, PlaylistFinder, ArtistFinder
│   │   ├── scoring.py             # score_consecutive_transitions
│   │   ├── library_stats.py       # get_library_stats()
│   │   ├── session_state.py       # save_build_result, save_export_config
│   │   └── elicitation.py         # resolve_conflict, confirm_action
│   ├── prompts/
│   │   └── workflows.py           # 4 recipe prompts
│   ├── resources/
│   │   └── status.py              # 3 resources (playlist, catalog, set)
│   ├── yandex_music/              # OpenAPI-generated YM tools (unchanged)
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── config.py
│   │   └── response_filters.py
│   ├── platforms/                  # Platform registry (MCP-specific)
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── factory.py
│   │   └── yandex.py
│   ├── skills/                    # MCP skills (YAML + markdown, unchanged)
│   ├── lifespan.py
│   └── observability.py
│
├── cli/                           # ══ LAYER 5c: CLI Adapter ══
│   ├── __init__.py
│   ├── main.py                    # Typer app + sub-apps
│   ├── _context.py                # console, run_async, open_session
│   ├── _formatting.py             # Rich tables, panels
│   └── commands/
│       ├── __init__.py
│       ├── tracks.py
│       ├── playlists.py
│       ├── sets.py
│       ├── build.py
│       ├── delivery.py
│       └── analysis.py
│
└── scripts/                       # Standalone scripts → use services/ layer
```

---

## 5. File Migration Map

### Deleted (merged or removed)

| Old file | Reason |
|----------|--------|
| `app/clients/yandex_music.py` | Merged into `services/platform/yandex/client.py` |
| `app/clients/__init__.py` | Directory removed |
| `app/dependencies.py` | Replaced by `services/_factories.py` + `api/dependencies.py` |
| `app/utils/audio/transition_score.py` | v1 scoring — merged into `domain/audio/scoring/service.py` |
| `app/utils/audio/_types.py` | Merged into `domain/audio/types.py` |
| `app/utils/audio/_errors.py` | Moved to `domain/audio/errors.py` |
| `app/utils/audio/__init__.py` | Replaced by `domain/audio/__init__.py` |
| `app/utils/` | Directory removed entirely |
| `app/services/rekordbox_types.py` | Moved to `domain/setbuilder/export/types.py` |
| `app/services/transition_type.py` | Moved to `domain/audio/scoring/transition_type.py` |
| `app/mcp/tools/curation_discovery.py` | Business logic → `services/platform/yandex/discovery.py` |
| `app/mcp/tools/export.py` + `unified_export.py` | Merged into `mcp/tools/delivery.py` (thin) |
| `app/mcp/tools/_scoring_helpers.py` | Moved to `mcp/helpers/scoring.py` |
| `app/routers/` | Renamed to `api/` |
| `app/models/base.py` | Moved to `core/base/model.py` |
| `app/schemas/base.py` | Moved to `core/base/schema.py` |
| `app/repositories/base.py` | Moved to `core/base/repository.py` |
| `app/services/base.py` | Moved to `core/base/service.py` |

### Split (God Objects → multiple files)

| Old file (LOC) | New files |
|----------------|-----------|
| `utils/audio/set_generator.py` (912) | `domain/setbuilder/types.py` (~70), `domain/setbuilder/energy_arcs.py` (~100), `domain/setbuilder/genetic/engine.py` (~250), `domain/setbuilder/genetic/fitness.py` (~150), `domain/setbuilder/genetic/operators.py` (~100), `domain/setbuilder/genetic/local_search.py` (~100) |
| `mcp/tools/delivery.py` (518) | `services/dj/delivery.py` (~300, business logic) + `mcp/tools/delivery.py` (~80, thin adapter) |
| `mcp/tools/curation_discovery.py` (563) | `services/platform/yandex/discovery.py` (~350, business logic) + `mcp/tools/curation.py` (~80, thin adapter) |

### Merged (DRY consolidation)

| Duplicate pair | Merged into |
|---------------|-------------|
| `_types.py:TrackFeatures` + `transition_scoring.py:TrackFeatures` | `domain/audio/types.py:TrackFeatures` |
| `clients/yandex_music.py` + `services/yandex_music_client.py` | `services/platform/yandex/client.py` |
| `utils/transition_score.py` (v1) + `services/transition_scoring.py` (v2) | `domain/audio/scoring/service.py` |
| `set_export.py:export_m3u()` + `delivery.py:_write_m3u8()` | `domain/setbuilder/export/m3u.py` |
| `app/dependencies.py` + `mcp/dependencies.py` (DI factories) | `services/_factories.py` |
| 3× "ORM → TrackData" patterns | `services/_converters.py:orm_to_track_data()` |

---

## 6. Key Design Decisions

### 6.1 Unified TrackFeatures

Two classes with the same name serve different purposes:
- `_types.py:TrackFeatures` — wraps DSP result objects (`BpmResult`, `KeyResult`, etc.)
- `transition_scoring.py:TrackFeatures` — flat numeric fields for scoring

**Decision**: Keep the scoring-oriented version as the unified `TrackFeatures` (flat, frozen, 15 fields). Rename the DSP wrapper to `AllFeatures` (it's the output of `extract_all_features()`). This way `TrackFeatures` is used everywhere for scoring, and `AllFeatures` is only used in the DSP pipeline → DB persistence path.

### 6.2 DI Unification via Factories

```python
# services/_factories.py (Layer 4)
def create_track_service(session: AsyncSession) -> TrackService:
    return TrackService(TrackRepository(session))

def create_generation_service(session: AsyncSession) -> SetGenerationService:
    return SetGenerationService(
        DjSetRepository(session), DjSetVersionRepository(session),
        DjSetItemRepository(session), AudioFeaturesRepository(session),
        SectionsRepository(session), DjPlaylistItemRepository(session),
    )

# api/dependencies.py (Layer 5a)
def get_track_service(db: DbSession) -> TrackService:
    return create_track_service(db)

# mcp/dependencies.py (Layer 5b)
def get_track_service(session: AsyncSession = Depends(get_session)) -> TrackService:
    return create_track_service(session)
```

### 6.3 Transaction Boundaries

**Current**: REST commits in router (`await db.commit()`), MCP commits in `get_session()` context manager.

**Target**: Both adapters use the same pattern — `get_session()` as async context manager that commits on success, rolls back on exception. REST router removes explicit `await db.commit()` calls. Services use `flush()` only, never `commit()`.

### 6.4 MCP Tool Thickness Rule

Every MCP tool function must be ≤ 80 lines. It can ONLY:
1. Parse input (resolve refs, validate params)
2. Report progress (`ctx.info()`, `ctx.report_progress()`)
3. Handle elicitation (`ctx.elicit()`)
4. Call a service method
5. Map result to MCP response type

If a tool needs business logic — that logic belongs in `services/`.

### 6.5 Models Consolidation

Current 19 model files → 4 domain-grouped files:
- `catalog.py` — Track, Artist, Genre, Label, Release + join tables (unchanged)
- `audio.py` — Features, Section, Run, Key, KeyEdge, Transition, TransitionCandidate, TransitionRun, Embedding, Timeseries
- `dj.py` — Set, Version, Item, Constraint, Feedback, Playlist, PlaylistItem, LibraryItem, Beatgrid, CuePoint, Loop, Asset, Export
- `platform.py` — Provider, ProviderTrackId, RawProviderResponse, YandexMetadata, SpotifyMetadata (all 5 metadata tables)

Each file stays under ~200 lines. All re-exported from `models/__init__.py` for `create_all()`.

---

## 7. Test Structure

```javascript
tests/
├── conftest.py                  # engine, session, client fixtures
│
├── domain/                      # ★ Pure unit tests (no DB, no mocks)
│   ├── audio/
│   │   ├── test_types.py        # TrackFeatures validation
│   │   ├── test_scoring.py      # TransitionScoringService
│   │   ├── test_classifier.py   # mood classification
│   │   └── test_dsp/            # DSP function tests (synthetic audio)
│   │       └── conftest.py      # WAV fixtures
│   ├── setbuilder/
│   │   ├── test_genetic.py      # GA engine, fitness, operators
│   │   ├── test_greedy.py
│   │   ├── test_templates.py
│   │   ├── test_curation.py
│   │   └── test_export/         # M3U, JSON, cheat_sheet
│   └── platform/
│       └── test_parser.py       # parse_ym_track
│
├── repositories/                # DB-dependent tests (in-memory SQLite)
│   ├── catalog/
│   ├── audio/
│   ├── dj/
│   └── platform/
│
├── services/                    # Integration tests (services + repos)
│   ├── catalog/
│   ├── audio/
│   ├── dj/
│   │   ├── test_generation.py
│   │   ├── test_delivery.py
│   │   └── test_curation.py
│   ├── platform/
│   │   └── test_yandex/
│   └── library/
│
├── api/                         # REST integration tests (httpx + ASGI)
│   └── v1/
│
├── mcp/                         # MCP integration tests
│   ├── conftest.py              # workflow_mcp, gateway_mcp, ym_mcp fixtures
│   ├── test_tools/
│   ├── test_types.py
│   ├── test_prompts.py
│   ├── test_resources.py
│   └── platforms/
│
├── cli/                         # CLI tests
│
└── scripts/                     # Script tests
```

**Key principle**: `tests/domain/` runs in <1 second, no DB, no network. `tests/services/` and below need in-memory SQLite.

---

## 8. Migration Strategy

### Phase 1: Foundation (non-breaking)
1. Create `core/` — move base classes, config, errors, middleware
2. Create `domain/` — move pure logic (DSP, scoring, classifier, setbuilder algorithms, export)
3. Update imports project-wide
4. Run `make check` — must pass

### Phase 2: Persistence (move files)
1. Consolidate `models/` from 19 → 4+1 files
2. Create `repositories/` subdirectories, move repos
3. Update imports
4. Run `make check`

### Phase 3: Application (restructure services)
1. Create `services/` subdirectories, move services
2. Create `services/_factories.py` and `services/_converters.py`
3. Merge two YM clients
4. Extract business logic from MCP tools into services
5. Split set_generator.py
6. Unify `TrackFeatures`
7. Update imports
8. Run `make check`

### Phase 4: Adapters (rename + thin)
1. Rename `routers/` → `api/`
2. Create `mcp/helpers/` — move scattered utilities
3. Thin MCP tools (delegate to services)
4. Move CLI commands into `cli/commands/`
5. Update imports
6. Run `make check`

### Phase 5: Enforcement
1. Add `import-linter` contracts
2. Add to CI
3. Update `.claude/rules/` documentation
4. Update `CHANGELOG.md`

---

## 9. Metrics (expected)

| Metric | Before | After |
|--------|--------|-------|
| Max file LOC | 912 (set_generator.py) | ~300 |
| MCP tool max LOC | 563 (curation_discovery.py) | ~80 |
| Flat directories (>15 files) | 3 (services/, repos/, models/) | 0 |
| Duplicate code pairs | 6 | 0 |
| Raw SQL in adapters | 6 files | 0 |
| Direct repo imports in adapters | 13 places | 0 |
| Domain layer framework deps | N/A (mixed) | 0 |
| `make check` | passes | passes |
| Test count | ~156 files | ~156 files (reorganized) |
