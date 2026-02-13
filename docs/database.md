# Database Schema (v6)

Source of truth: [`schema_v6.sql`](../data/schema_v6.sql) (PostgreSQL 16+ DDL).

## Extensions

| Extension | Purpose |
|-----------|---------|
| pgvector | Vector similarity (chroma, embeddings, transition features) |
| btree_gist | GiST indexes for range exclusion constraints (track_sections) |
| pg_trgm | Trigram indexes for fuzzy text search (track/artist titles) |

## Entity-Relationship Overview

```text
                    ┌──────────────┐
                    │   providers  │
                    └──────┬───────┘
                           │
┌─────────┐  track_artists ├──────────────┐  provider_track_ids
│ artists ├────────────────┤    tracks     ├──────────────────────┐
└─────────┘                │              │                      │
┌─────────┐  track_genres  │  track_id PK │  raw_provider_responses
│  genres ├────────────────┤              │
└─────────┘                │              │
┌─────────┐  track_releases│              │   ┌──────────────────────────┐
│releases ├────────────────┤              ├───┤ spotify/soundcloud/      │
└────┬────┘                └──────┬───────┘   │ beatport_metadata        │
     │                            │           └──────────────────────────┘
┌────┴────┐                       │
│ labels  │                       │
└─────────┘                       │
            ┌─────────────────────┼─────────────────────────────┐
            │                     │                             │
            ▼                     ▼                             ▼
  ┌──────────────────┐  ┌────────────────┐            ┌──────────────┐
  │ audio_assets     │  │ track_sections │            │ dj_library_  │
  │ (stems, files)   │  │ (segmentation) │            │ items, cues, │
  └──────────────────┘  └───────┬────────┘            │ loops, grids │
            │                   │                     └──────────────┘
            ▼                   ▼
  ┌──────────────────┐  ┌────────────────┐   ┌─────────────────────┐
  │ feature_         │  │ transitions    │   │ track_audio_        │
  │ extraction_runs  │  │ (full scoring) │   │ features_computed   │
  └──────────────────┘  └───────┬────────┘   │ (~35 DSP columns)  │
                                │            └─────────────────────┘
                                │                     │
  ┌──────────────────┐          │            ┌────────┴────────┐
  │ transition_runs  ├──────────┘            │      keys       │
  └──────────────────┘                       │ (24 key codes)  │
                                             └────────┬────────┘
  ┌──────────────────┐                                │
  │    dj_sets       │                       ┌────────┴────────┐
  │  └ versions      │                       │   key_edges     │
  │    └ items ──────┼── FK to transitions   │ (compatibility) │
  │    └ constraints │                       └─────────────────┘
  │    └ feedback    │
  └──────────────────┘
```

## Table Groups

### 1. Catalog (core music metadata)

#### tracks
Primary entity. All domain models reference `track_id`.

| Column | Type | Constraints |
|--------|------|-------------|
| track_id | integer PK | GENERATED ALWAYS AS IDENTITY |
| fingerprint_sha1 | bytea | UNIQUE, exactly 20 bytes |
| title | text | NOT NULL |
| title_sort | text | Sortable title (strip "The", etc.) |
| duration_ms | integer | NOT NULL, > 0 |
| status | smallint | 0=active, 1=broken. Default 0 |
| archived_at | timestamptz | NULL=active (soft delete) |
| created_at, updated_at | timestamptz | Auto-managed |

Indexes: partial `idx_tracks_active` (WHERE archived_at IS NULL), trigram `idx_tracks_title_trgm`.

#### artists
| Column | Type |
|--------|------|
| artist_id | integer PK |
| name | text NOT NULL |
| name_sort | text |

#### track_artists (junction)
Composite PK: `(track_id, artist_id, role)`. Role: 0=primary, 1=featured, 2=remixer.

#### labels, releases, track_releases
Releases have optional label FK and `release_date_precision` CHECK ('year', 'month', 'day').

#### genres
Self-referencing hierarchy via `parent_genre_id`. Unique `name`.

#### track_genres
Surrogate PK. Composite unique: `(track_id, genre_id, source_provider_id)` with NULLS NOT DISTINCT.

### 2. Providers & Ingestion

#### providers
Static reference table (seeded: Spotify=1, SoundCloud=2, Beatport=3). SmallInteger PK.

#### provider_track_ids
Maps internal `track_id` to external provider IDs. Unique: `(provider_id, provider_track_id, provider_country)` NULLS NOT DISTINCT.

#### raw_provider_responses
Raw JSON payloads from API calls. **Partitioned by `ingested_at`** (range partitioning). Retention policy: 6 months.

### 3. Provider Metadata

#### spotify_metadata
Track-level Spotify data. PK=track_id (FK to tracks). Popularity CHECK 0-100.

#### spotify_audio_features
Spotify's audio analysis. 8 float columns with CHECK 0-1 (danceability, energy, speechiness, etc.). Mode CHECK 0 or 1.

#### spotify_album_metadata, spotify_artist_metadata, spotify_playlist_metadata
Text PKs (Spotify IDs). Extra data in `jsonb extra` column.

#### soundcloud_metadata
PK=track_id. `soundcloud_track_id` unique.

#### beatport_metadata
PK=track_id. `key_code` FK to keys (0-23).

### 4. Pipeline Versioning

#### feature_extraction_runs
Tracks DSP/ML pipeline executions. `status` CHECK: 'running', 'completed', 'failed'. Stores pipeline_name, version, parameters, code_ref.

#### transition_runs
Same structure for transition scoring pipelines. Stores scoring weights and constraints as JSONB.

### 5. Audio Assets

#### audio_assets
Registry of audio files: originals, Demucs stems, preview clips. `asset_type`: 0=full_mix, 1=drums_stem, 2=bass_stem, 3=vocals_stem, 4=other_stem, 5=preview_clip. Unique: `(track_id, asset_type, source_run_id)`.

### 6. Harmony Model

#### keys
Static reference: 24 musical keys. Deterministic constraint: `key_code = pitch_class * 2 + mode`.

| key_code | name | camelot | pitch_class | mode |
|----------|------|---------|-------------|------|
| 0 | Cm | 5A | 0 | 0 (minor) |
| 1 | C | 8B | 0 | 1 (major) |
| ... | ... | ... | ... | ... |
| 23 | B | 1B | 11 | 1 (major) |

#### key_edges
Compatibility graph between keys. Composite PK: `(from_key_code, to_key_code)`. Distance >= 0 (0 = perfect compatibility). Max 576 edges. Used by `camelot_distance()` and `key_distance_weighted()` SQL functions.

### 7. Computed Audio Features

#### track_audio_features_computed
~35 columns of DSP/ML analysis results. Composite PK: `(track_id, run_id)`.

| Group | Columns | Range |
|-------|---------|-------|
| Tempo | bpm, tempo_confidence, bpm_stability, is_variable_tempo | bpm: 20-300, others: 0-1 |
| Loudness | lufs_i, lufs_s_mean, lufs_m_max, rms_dbfs, true_peak_db, crest_factor_db, lra_lu | dB values |
| Energy | energy_mean, energy_max, energy_std, energy_slope_mean | mean/max/std: 0-1, slope: float |
| Band energies | sub/low/lowmid/mid/highmid/high_energy, ratios | 0-1 |
| Spectral | centroid_mean_hz, rolloff_85/95_hz, flatness_mean, flux_mean/std, slope_db_per_oct, contrast_mean_db | Hz / dB / float |
| Tonal | key_code (FK), key_confidence, is_atonal, chroma (vector(12)), hnr_mean_db | confidence: 0-1, HNR: dB |
| Rhythm | hp_ratio, onset_rate_mean/max, pulse_clarity, kick_prominence | mixed units (ratio, onsets/s, 0-1) |

HNSW index on `chroma` for harmonic profile similarity search.

Runtime population notes:

- `feature_extraction_runs.parameters` and `feature_extraction_runs.code_ref` are written by `AnalysisOrchestrator` when a run is created.
- `energy_slope_mean` and `energy_std` are derived from frame-level RMS energy.
- `slope_db_per_oct` is computed as a linear fit of spectrum magnitude (dB) over log2-frequency (octaves).
- `hnr_mean_db` is computed as frame-level Harmonics-to-Noise Ratio and averaged over track frames.

### 8. Track Sections

#### track_sections
Structural segmentation results. `range_ms` (int4range in PostgreSQL, start_ms/end_ms in ORM). `section_type`: 0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro, 5=break, 6=inst, 7=verse, 8=chorus, 9=bridge, 10=solo, 11=unknown.

Per-section aggregates: energy_mean, energy_max, centroid_hz, flux, onset_rate, pulse_clarity, boundary_confidence.

Section metric notes:

- `section_centroid_hz` and `section_flux` are computed per section from frame-level spectra.
- `section_onset_rate` uses beat density inside section boundaries.
- `section_pulse_clarity` is computed from beat-interval regularity (IOI coefficient of variation) with fallback to track-level pulse clarity.
- `boundary_confidence` is normalized novelty at section boundary.

Composite unique `(section_id, track_id)` enables composite FKs from transitions and set items.

### 9. Timeseries References

#### track_timeseries_refs
Pointers to frame-level numpy arrays in object storage (S3/MinIO). Composite PK: `(track_id, run_id, feature_set)`. Feature sets: onset_env, rms_frames, chroma_frames, spectral_centroid_frames.

### 10. Transition Scoring (two-stage)

#### transition_candidates (Stage 1: pre-filter)
Lightweight metrics from existing scalars + ANN. Composite PK: `(from_track_id, to_track_id, run_id)`. Direction constraint: `from_track_id <> to_track_id`. Filters ~500K candidates from ~12.5M pairs (for 5000 tracks).

| Metric | Type |
|--------|------|
| bpm_distance | real >= 0 |
| key_distance | real >= 0 |
| embedding_similarity | real (cosine) |
| energy_delta | real |

#### transitions (Stage 2: full scoring)
Detailed transition analysis. Identity PK. `transition_quality` CHECK 0-1 (higher = better). `trans_feature` vector(32) for ANN search.

Scoring components: overlap_ms, bpm_distance, energy_step, centroid_gap_hz, low_conflict_score, overlap_score, groove_similarity, key_distance_weighted.

Composite FKs: `(from_section_id, from_track_id)` and `(to_section_id, to_track_id)` reference track_sections.

### 11. Embeddings

#### embedding_types (registry)
Text PK (e.g., 'groove', 'timbre', 'genre'). `dim > 0`. Trigger validates vector dimensions on insert/update.

#### track_embeddings
Unified table for all embedding types. pgvector `vector` column. Unique: `(track_id, embedding_type, run_id)`. HNSW indexes created per embedding_type via partial indexes.

### 12. DJ Layer

#### dj_library_items
File references per track (URI, path, hash, metadata). `source_app` CHECK 1-5.

#### dj_beatgrid
BPM grid per track per source. Unique: `(track_id, source_app)`. Partial unique index on `is_canonical = true` (one canonical grid per track). BPM CHECK 20-300.

#### dj_beatgrid_change_points
Variable-tempo grid markers. FK to dj_beatgrid.

#### dj_cue_points
Hot cues, load points, fade markers. `cue_kind` CHECK 0-7: cue, load, grid, fade_in, fade_out, loop_in, loop_out, memory.

#### dj_saved_loops
Loop regions. Range check: `out_ms > in_ms AND length_ms = out_ms - in_ms`.

#### dj_playlists, dj_playlist_items
Self-referencing hierarchy (folders). Items have unique `(playlist_id, sort_index)`.

#### dj_app_exports
Export files for DJ apps. `target_app` CHECK 1-3 (Traktor, Rekordbox, djay). Storage URI instead of binary.

### 13. DJ Sets

#### dj_sets
Set definition with optional constraints: `target_duration_ms > 0`, BPM range, energy arc (JSON).

#### dj_set_versions
Multiple generated versions per set. `score` (0-1). `generator_run` JSON stores algorithm params.

#### dj_set_constraints
Per-version constraints: max_bpm_jump, key_policy, min_transition_ms, required/excluded tracks, genre filter. JSON `value` payload.

#### dj_set_items
Ordered track list. Unique: `(set_version_id, sort_index)`. Links to transition_id and sections. Stores mix_in_ms, mix_out_ms, planned_eq (JSON).

#### dj_set_feedback
Rating (-1 to 5) on version or individual item. `feedback_type`: manual, live_crowd, a_b_test. Closes the learning loop.

## Views

| View | Purpose |
|------|---------|
| v_latest_track_features | Latest computed features per track (DISTINCT ON track_id, ORDER BY run_id DESC) |
| v_active_tracks_with_features | Active tracks + BPM/key/energy joined from latest features + key names |
| v_pending_scoring | Unscored transition candidates prioritized by normalized BPM + key distance |

## Functions

| Function | Volatility | Description |
|----------|-----------|-------------|
| camelot_distance(a, b) | STABLE | Key distance from key_edges graph (default 12.0 if no edge) |
| key_distance_weighted(a, conf_a, b, conf_b) | STABLE | Weighted key distance with confidence interpolation |
| trg_set_updated_at() | trigger | Auto-updates `updated_at` on 15 tables |
| trg_check_embedding_dim() | trigger | Validates vector dimension matches embedding_types.dim |

## SQLite Compatibility (ORM)

The ORM models are designed to work on both PostgreSQL and SQLite (for tests):

| PostgreSQL | ORM (SQLite-compatible) |
|------------|------------------------|
| `JSONB` | `JSON` |
| `server_default='now()'` | `server_default=func.now()` |
| `vector(N)` | `String` (placeholder) |
| `int4range` | `start_ms` / `end_ms` integer pair |
| `text[]` | Not mapped (app-level only) |
| `bytea` with CHECK | Not mapped in ORM |
| `NULLS NOT DISTINCT` | Standard UNIQUE (SQLite ignores) |

## Backfill and Validation (dev.db)

For historical rows created before recent pipeline changes, run:

```bash
.venv/bin/python scripts/fix_db_gaps.py
.venv/bin/python scripts/reanalyze_partial.py --all
```

Recommended validation queries:

```sql
-- artist sort keys
SELECT COUNT(*) AS artists_name_sort_nulls
FROM artists
WHERE name_sort IS NULL;

-- run metadata
SELECT
  SUM(CASE WHEN parameters IS NULL THEN 1 ELSE 0 END) AS parameters_nulls,
  SUM(CASE WHEN code_ref IS NULL THEN 1 ELSE 0 END) AS code_ref_nulls
FROM feature_extraction_runs
WHERE run_id IN (SELECT DISTINCT run_id FROM track_audio_features_computed);

-- feature columns
SELECT
  SUM(CASE WHEN energy_slope_mean IS NULL THEN 1 ELSE 0 END) AS energy_slope_nulls,
  SUM(CASE WHEN hnr_mean_db IS NULL THEN 1 ELSE 0 END) AS hnr_nulls,
  SUM(CASE WHEN slope_db_per_oct IS NULL THEN 1 ELSE 0 END) AS spectral_slope_nulls
FROM track_audio_features_computed;

-- section columns
SELECT
  SUM(CASE WHEN section_centroid_hz IS NULL THEN 1 ELSE 0 END) AS centroid_nulls,
  SUM(CASE WHEN section_flux IS NULL THEN 1 ELSE 0 END) AS flux_nulls,
  SUM(CASE WHEN section_onset_rate IS NULL THEN 1 ELSE 0 END) AS onset_rate_nulls,
  SUM(CASE WHEN section_pulse_clarity IS NULL THEN 1 ELSE 0 END) AS pulse_clarity_nulls
FROM track_sections;
```

## Enum Mappings

Enums stored as `smallint` in the database, mapped to Python `IntEnum`/`StrEnum` in `app/models/enums.py`:

| Enum | Values |
|------|--------|
| ArtistRole | 0=primary, 1=featured, 2=remixer |
| SectionType | 0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro, 5=break, 6=inst, 7=verse, 8=chorus, 9=bridge, 10=solo, 11=unknown |
| CueKind | 0=cue, 1=load, 2=grid, 3=fade_in, 4=fade_out, 5=loop_in, 6=loop_out, 7=memory |
| SourceApp | 1=traktor, 2=rekordbox, 3=djay, 4=import, 5=generated |
| TargetApp | 1=traktor, 2=rekordbox, 3=djay |
| AssetType | 0=full_mix, 1=drums_stem, 2=bass_stem, 3=vocals_stem, 4=other_stem, 5=preview_clip |
| RunStatus | 'running', 'completed', 'failed' (StrEnum) |
| FeedbackType | 'manual', 'live_crowd', 'a_b_test' (StrEnum) |
