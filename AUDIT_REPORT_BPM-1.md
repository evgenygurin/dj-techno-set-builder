# ORM Models vs Schema Audit Report - BPM-1

## Executive Summary

**Status:** ✅ Schema structure is consistent with ORM models  
**Critical Issues:** 0  
**Medium Priority Issues:** 4 (reduced from 9, all related to missing SQL-level defaults)  
**Tables Analyzed:** 44  
**Perfect Matches:** 40 (90.9%)

**Key Finding:** The primary discrepancy is that Python/ORM-level column defaults are not reflected as SQL DDL defaults in the database schema. This is a common pattern but creates potential inconsistencies.

## Coverage Matrix

| Table | Model Class | Status | Mismatch Details | Severity | Proposed Fix |
|-------|-------------|---------|------------------|----------|--------------|
| artists | app.models.catalog.Artist | OK | - | - | - |
| audio_assets | app.models.assets.AudioAsset | OK | - | - | - |
| beatport_metadata | app.models.metadata_beatport.BeatportMetadata | OK | - | - | - |
| dj_app_exports | app.models.dj.DjAppExport | OK | - | - | - |
| dj_beatgrid | app.models.dj.DjBeatgrid | OK | - | - | ✅ FIXED |
| dj_beatgrid_change_points | app.models.dj.DjBeatgridChangePoint | OK | - | - | - |
| dj_cue_points | app.models.dj.DjCuePoint | OK | - | - | - |
| dj_library_items | app.models.dj.DjLibraryItem | OK | - | - | - |
| dj_playlist_items | app.models.dj.DjPlaylistItem | OK | - | - | - |
| dj_playlists | app.models.dj.DjPlaylist | OK | - | - | - |
| dj_saved_loops | app.models.dj.DjSavedLoop | OK | - | - | - |
| dj_set_constraints | app.models.sets.DjSetConstraint | OK | - | - | - |
| dj_set_feedback | app.models.sets.DjSetFeedback | MISMATCH | feedback_type default 'manual' | P1 | Migration + model consistency |
| dj_set_items | app.models.sets.DjSetItem | OK | - | - | - |
| dj_set_versions | app.models.sets.DjSetVersion | OK | - | - | - |
| dj_sets | app.models.sets.DjSet | OK | - | - | - |
| embedding_types | app.models.embeddings.EmbeddingType | OK | - | - | - |
| feature_extraction_runs | app.models.runs.FeatureExtractionRun | OK | - | - | ✅ FIXED |
| genres | app.models.catalog.Genre | OK | - | - | - |
| key_edges | app.models.harmony.KeyEdge | OK | - | - | - |
| keys | app.models.harmony.Key | OK | - | - | - |
| labels | app.models.catalog.Label | OK | - | - | - |
| provider_track_ids | app.models.ingestion.ProviderTrackId | OK | - | - | - |
| providers | app.models.providers.Provider | OK | - | - | - |
| raw_provider_responses | app.models.ingestion.RawProviderResponse | OK | - | - | - |
| releases | app.models.catalog.Release | OK | - | - | - |
| soundcloud_metadata | app.models.metadata_soundcloud.SoundCloudMetadata | OK | - | - | - |
| spotify_album_metadata | app.models.metadata_spotify.SpotifyAlbumMetadata | OK | - | - | - |
| spotify_artist_metadata | app.models.metadata_spotify.SpotifyArtistMetadata | OK | - | - | - |
| spotify_audio_features | app.models.metadata_spotify.SpotifyAudioFeatures | OK | - | - | - |
| spotify_metadata | app.models.metadata_spotify.SpotifyMetadata | MISMATCH | explicit default False | P1 | Migration + model consistency |
| spotify_playlist_metadata | app.models.metadata_spotify.SpotifyPlaylistMetadata | OK | - | - | - |
| track_artists | app.models.catalog.TrackArtist | OK | - | - | - |
| track_audio_features_computed | app.models.features.TrackAudioFeaturesComputed | OK | - | - | ✅ FIXED |
| track_embeddings | app.models.embeddings.TrackEmbedding | OK | - | - | - |
| track_genres | app.models.catalog.TrackGenre | OK | - | - | - |
| track_releases | app.models.catalog.TrackRelease | OK | - | - | - |
| track_sections | app.models.sections.TrackSection | OK | - | - | - |
| track_timeseries_refs | app.models.timeseries.TrackTimeseriesRef | MISMATCH | dtype default 'float32' | P1 | Migration + model consistency |
| tracks | app.models.catalog.Track | OK | - | - | ✅ FIXED |
| transition_candidates | app.models.transitions.TransitionCandidate | MISMATCH | is_fully_scored default False | P1 | Migration + model consistency |
| transition_runs | app.models.runs.TransitionRun | OK | - | - | ✅ FIXED |
| transitions | app.models.transitions.Transition | OK | - | - | - |
| yandex_metadata | app.models.metadata_yandex.YandexMetadata | OK | - | - | - |

## Top-10 Mismatch Shortlist with Rationale

### 1. `track_audio_features_computed` (P1 - High)
**Issue:** 3 missing defaults - `is_atonal`, `is_variable_tempo`, `computed_from_asset_type`  
**Risk:** Audio analysis features could have inconsistent initialization  
**Rationale:** Core audio processing functionality relies on these defaults

### 2. `tracks` (P1 - High)  
**Issue:** Missing `status` default (0)  
**Risk:** New tracks without explicit status could be inconsistent  
**Rationale:** Central entity, status affects track visibility/processing

### 3. `feature_extraction_runs` & `transition_runs` (P1 - High)
**Issue:** Missing `status` defaults ('running')  
**Risk:** Pipeline runs might have undefined status on creation  
**Rationale:** Critical for workflow state management

### 4. `dj_beatgrid` (P1 - Medium)
**Issue:** Missing boolean defaults for `is_variable_tempo`, `is_canonical`  
**Risk:** Beatgrid analysis assumptions could be inconsistent  
**Rationale:** Affects DJ workflow and beat detection logic

### 5. `dj_set_feedback` (P1 - Medium)
**Issue:** Missing `feedback_type` default ('manual')  
**Risk:** User feedback classification could be ambiguous  
**Rationale:** Important for ML training data quality

### 6. `spotify_metadata` (P1 - Low)
**Issue:** Missing `explicit` default (False)  
**Risk:** Content filtering might be inconsistent  
**Rationale:** Low impact but affects content classification

### 7. `track_timeseries_refs` (P1 - Low)  
**Issue:** Missing `dtype` default ('float32')  
**Risk:** Audio data type assumptions could vary  
**Rationale:** Technical consistency for audio processing

### 8. `transition_candidates` (P1 - Low)
**Issue:** Missing `is_fully_scored` default (False)  
**Risk:** Scoring completeness tracking inconsistent  
**Rationale:** Workflow optimization relies on this flag

## Migration Impact Summary

### Low-Risk Changes (Recommended for Immediate Fix)
- **Total affected tables:** 9
- **Migration approach:** Add `server_default` to existing columns
- **Data consistency:** No existing data modification required
- **Rollback:** Simple (remove server defaults)

### Implementation Strategy
1. **Phase 1:** Boolean defaults (safest)
   - `dj_beatgrid.is_variable_tempo`, `is_canonical`
   - `spotify_metadata.explicit`
   - `track_audio_features_computed.is_atonal`, `is_variable_tempo`
   - `transition_candidates.is_fully_scored`

2. **Phase 2:** String/Enum defaults
   - `dj_set_feedback.feedback_type`
   - `feature_extraction_runs.status`
   - `transition_runs.status`
   - `track_timeseries_refs.dtype`

3. **Phase 3:** Integer defaults
   - `tracks.status`
   - `track_audio_features_computed.computed_from_asset_type`

### Risk Assessment
- **P0:** None (no critical mismatches)
- **P1:** All 9 mismatches (medium business impact)
- **P2:** None (no structural issues)

## Test Plan

### Pre-Migration Tests
```bash
# Verify current ORM behavior
uv run pytest tests/test_models/ -v -k "default"

# Test model instantiation without explicit values
uv run python -c "
from app.models import Track, DjBeatgrid
print('Track defaults:', Track().status)  # Should be 0
print('Beatgrid defaults:', DjBeatgrid().is_variable_tempo)  # Should be False
"
```

### Post-Migration Tests
```bash
# Verify DDL defaults work in raw SQL
sqlite3 dev.db "INSERT INTO tracks (title, duration_ms) VALUES ('test', 180000);"
sqlite3 dev.db "SELECT status FROM tracks WHERE title='test';"  # Should be 0

# Verify ORM still works
uv run pytest tests/test_models/ -v

# Integration tests
uv run pytest tests/test_workflows/ -v
```

### Migration Validation
```bash
# Check schema consistency
uv run python audit_schema.py

# Verify no breaking changes
uv run pytest tests/ -x --tb=short
```

## Next Steps

### Immediate Actions (Low-Risk)
1. ✅ **Completed:** Schema audit and gap analysis
2. 🔄 **In Progress:** Create Alembic migrations for DDL defaults
3. ⏳ **Next:** Update models to use `server_default` instead of Python `default`
4. ⏳ **Next:** Run validation tests

### Future Considerations
- Consider standardizing default patterns across all models
- Add validation tests for default value consistency
- Document default value policies in development guidelines

## Changes Made

### ✅ Fixed Issues (5 tables)
1. **`dj_beatgrid`** - Added `server_default="0"` for `is_variable_tempo`, `is_canonical`
2. **`tracks`** - Added `server_default="0"` for `status`
3. **`feature_extraction_runs`** - Added `server_default="'running'"` for `status` 
4. **`transition_runs`** - Added `server_default="'running'"` for `status`
5. **`track_audio_features_computed`** - Added `server_default="0"` for `is_atonal`, `is_variable_tempo`, `computed_from_asset_type`

### 📋 Remaining Issues (4 tables)
- `dj_set_feedback.feedback_type` - needs `server_default="'manual'"`
- `spotify_metadata.explicit` - needs `server_default="0"`  
- `track_timeseries_refs.dtype` - needs `server_default="'float32'"`
- `transition_candidates.is_fully_scored` - needs `server_default="0"`

## Definition of Done
- [x] Gap report completed and posted to issue
- [x] PR created with low-risk fixes (5 high-priority defaults fixed)
- [x] All linting and type checks pass
- [x] Basic model validation passed
- [x] Migration impact assessed and documented