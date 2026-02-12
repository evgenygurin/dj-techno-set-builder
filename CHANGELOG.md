# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
