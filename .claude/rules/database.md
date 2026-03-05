---
paths:
  - "app/models/**"
  - "app/repositories/**"
  - "migrations/**"
  - "data/schema_v6.sql"
---

# Models & Database

## Overview

- **DDL source of truth**: `data/schema_v6.sql` (PostgreSQL DDL with pgvector, btree_gist, pg_trgm)
- **Dev DB**: SQLite via aiosqlite (auto-created by `init_db()` when URL starts with `sqlite`)
- **Prod DB**: PostgreSQL 16+ with asyncpg
- **30+ ORM models** in `app/models/` — all re-exported through `app/models/__init__.py`

## Configuration

`app/config.py` — `Settings(BaseSettings)` with `.env`:

```python
database_url: str = "sqlite+aiosqlite:///./dev.db"  # default
```

PostgreSQL: `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dj_set_builder`

## Database initialization

`app/database.py` — `init_db()`:
- Imports `app.models` to register all ORM classes in `Base.metadata`
- For SQLite: auto-creates all tables via `Base.metadata.create_all()`
- Seeds providers table with 4 standard entries (Spotify, SoundCloud, Beatport, Yandex Music)

## Model conventions

- All models inherit from `Base` (DeclarativeBase) in `app/models/base.py`
- Updatable tables use `TimestampMixin` (created_at + updated_at with `server_default=func.now()`)
- Append-only tables use `CreatedAtMixin` (created_at only)
- **CHECK constraints inline** in `mapped_column()` matching the DDL exactly
- `__all__` lists in `__init__.py` must be **alphabetically sorted** (ruff RUF022)

## Model files (20 files)

| File | Models | Purpose |
|------|--------|---------|
| `base.py` | Base, TimestampMixin, CreatedAtMixin | Foundation |
| `catalog.py` | Track, Artist, Genre, Label, Release, TrackArtist, TrackGenre, TrackRelease | Core metadata |
| `features.py` | TrackAudioFeaturesComputed | ~35 DSP/ML audio descriptors |
| `dj.py` | DjLibraryItem, DjBeatgrid, DjCuePoint, DjPlaylist, DjPlaylistItem | DJ app data |
| `sets.py` | DjSet, DjSetVersion, DjSetItem, DjSetConstraint, DjSetFeedback | Generated sets |
| `transitions.py` | Transition, TransitionCandidate | Two-stage scoring |
| `sections.py` | TrackSection | Structural segmentation |
| `harmony.py` | Key, KeyEdge | 24-key compatibility graph |
| `runs.py` | FeatureExtractionRun, TransitionRun | Pipeline runs |
| `embeddings.py` | EmbeddingType, TrackEmbedding | Vector embeddings |
| `metadata_yandex.py` | YandexMusicMetadata | YM-specific enriched data |
| `ingestion.py` | Provider, ProviderTrackId, RawProviderResponse | Multi-source mapping |
| `assets.py` | AudioAsset | Original files + stems |
| `timeseries.py` | TrackTimeseriesRef | Frame-level data pointers |
| `enums.py` | 8 enum classes | IntEnum/StrEnum for DB values |

## Enums

Domain enums in `app/models/enums.py` — DB stores raw smallint/text, not the enum type:

| Enum | Type | Values |
|------|------|--------|
| `ArtistRole` | IntEnum | PRIMARY(0), FEATURED(1), REMIXER(2) |
| `SectionType` | IntEnum | INTRO(0)..UNKNOWN(11) — 12 section types |
| `CueKind` | IntEnum | CUE(0)..MEMORY(7) — 8 cue types |
| `SourceApp` | IntEnum | TRAKTOR(1)..GENERATED(5) |
| `TargetApp` | IntEnum | TRAKTOR(1), REKORDBOX(2), DJAY(3) |
| `AssetType` | IntEnum | FULL_MIX(0)..PREVIEW_CLIP(5) |
| `RunStatus` | StrEnum | running, completed, failed |
| `FeedbackType` | StrEnum | manual, live_crowd, a_b_test |

## SQLite compatibility (tests)

Models must work on both SQLite (tests) and PostgreSQL (prod):
- Use `JSON` (not `JSONB` from `sqlalchemy.dialects.postgresql`)
- Use `server_default=func.now()` (not string `"now()"`)
- pgvector `vector(N)` columns use `String` as placeholder
- `int4range` columns use `start_ms`/`end_ms` integer pairs instead

## Repository pattern

`BaseRepository[ModelT: Base]` (`app/repositories/base.py`) — PEP 695 type params:

```python
class BaseRepository[ModelT: Base]:
    model: type[ModelT]  # set by subclass

    async def get_by_id(self, pk: int) -> ModelT | None
    async def list(*, offset, limit, filters) -> tuple[list[ModelT], int]
    async def create(**kwargs) -> ModelT     # flush, not commit!
    async def update(instance, **kwargs) -> ModelT  # flush + refresh
    async def delete(instance) -> None       # flush, not commit!
```

**Critical pattern**: All repository methods use `await session.flush()`, never `commit()`. The commit is done in the **router** (HTTP boundary).

19 specialized repositories with custom queries:
- `TrackRepository` — `search_by_title(query, offset, limit)` with ILIKE
- `AudioFeaturesRepository` — `get_by_track()`, `list_all()` (subquery for latest per track), `save_features()`
- `CandidateRepository` — `list_unscored()`, `list_for_track()` with multiple filters
- `ProviderRepository` — `get_or_create()` for seeding

## Important gotchas

- **async SA + onupdate**: `onupdate=func.now()` requires `session.refresh()` after flush to see updated value — already handled in `BaseRepository.update()`
- **Critical import**: `from app.models import Base` (not `from app.models.base`) — triggers all model registrations so `create_all` sees every table
- **PEP 695**: ruff UP046 requires `class Foo[T: Base]:` instead of `Generic[T]`
- **DjSetVersion PK**: field is `set_version_id` (not `version_id`) — easy to confuse in tests and FK references
- **dj_set_items columns**: `set_version_id` (FK to DjSetVersion), `sort_index` (not `position`), `track_id`
- **Track.status**: SmallInteger, 0=active, 1=archived (NOT a string — `status="active"` is a Pydantic error)
- **SQLite column names**: `track_audio_features_computed` uses `onset_rate_mean` (not `onset_rate`), `hnr_mean_db` (not `hnr_db`), `chroma_entropy` — always check `PRAGMA table_info(table)` before raw SQL
