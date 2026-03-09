---
paths:
  - "app/models/**"
  - "app/repositories/**"
  - "app/mcp/tools/**"
  - "migrations/**"
---

# DB Schema Reference (auto-generated)

> Generated: 2026-03-05 21:47 UTC | Source: `dev.db` | Tables: 44
>
> **Do not edit manually.** Regenerate: `make db-schema`

## Overview

| Table | Rows | Cols |
|-------|------|------|
| `artists` | 0 | 5 |
| `audio_assets` | 0 | 11 |
| `beatport_metadata` | 0 | 15 |
| `dj_app_exports` | 0 | 7 |
| `dj_beatgrid` | 0 | 11 |
| `dj_beatgrid_change_points` | 0 | 5 |
| `dj_cue_points` | 0 | 11 |
| `dj_library_items` | 1,206 | 12 |
| `dj_playlist_items` | 809 | 5 |
| `dj_playlists` | 4 | 7 |
| `dj_saved_loops` | 0 | 11 |
| `dj_set_constraints` | 0 | 5 |
| `dj_set_feedback` | 0 | 7 |
| `dj_set_items` | 903 | 13 |
| `dj_set_versions` | 17 | 6 |
| `dj_sets` | 11 | 12 |
| `embedding_types` | 0 | 5 |
| `feature_extraction_runs` | 591 | 9 |
| `genres` | 0 | 3 |
| `key_edges` | 0 | 6 |
| `keys` | 24 | 5 |
| `labels` | 0 | 5 |
| `provider_track_ids` | 1,218 | 7 |
| `providers` | 5 | 3 |
| `raw_provider_responses` | 0 | 7 |
| `releases` | 0 | 7 |
| `soundcloud_metadata` | 0 | 21 |
| `spotify_album_metadata` | 0 | 10 |
| `spotify_artist_metadata` | 0 | 6 |
| `spotify_audio_features` | 0 | 15 |
| `spotify_metadata` | 0 | 12 |
| `spotify_playlist_metadata` | 0 | 9 |
| `track_artists` | 1,371 | 4 |
| `track_audio_features_computed` | 583 | 47 |
| `track_embeddings` | 0 | 6 |
| `track_genres` | 0 | 5 |
| `track_releases` | 0 | 5 |
| `track_sections` | 45,117 | 16 |
| `track_timeseries_refs` | 0 | 11 |
| `tracks` | 1,420 | 8 |
| `transition_candidates` | 0 | 9 |
| `transition_runs` | 0 | 9 |
| `transitions` | 0 | 17 |
| `yandex_metadata` | 1,000 | 15 |

## Tables

### `artists` (0 rows)
- `artist_id` INTEGER PK NOT NULL
- `name` VARCHAR(300) NOT NULL
- `name_sort` VARCHAR(300)
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `audio_assets` (0 rows)
- `asset_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `asset_type` SMALLINT NOT NULL
- `storage_uri` VARCHAR(500) NOT NULL
- `format` VARCHAR(20) NOT NULL
- `sample_rate` INTEGER
- `channels` SMALLINT
- `duration_ms` INTEGER
- `file_size` INTEGER
- `source_run_id` INTEGER -> feature_extraction_runs.run_id
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `beatport_metadata` (0 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `beatport_track_id` VARCHAR(100) NOT NULL
- `beatport_release_id` VARCHAR(100)
- `bpm` FLOAT
- `key_code` SMALLINT
- `length_ms` INTEGER
- `label_name` VARCHAR(300)
- `genre_name` VARCHAR(200)
- `subgenre_name` VARCHAR(200)
- `release_date` DATE
- `preview_url` VARCHAR(500)
- `image_url` VARCHAR(500)
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_app_exports` (0 rows)
- `export_id` INTEGER PK NOT NULL
- `target_app` SMALLINT NOT NULL
- `export_format` VARCHAR(50) NOT NULL
- `playlist_id` INTEGER -> dj_playlists.playlist_id
- `storage_uri` VARCHAR(500)
- `file_size` INTEGER
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_beatgrid` (0 rows)
- `beatgrid_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `source_app` SMALLINT NOT NULL
- `bpm` FLOAT NOT NULL
- `first_downbeat_ms` INTEGER NOT NULL
- `grid_offset_ms` INTEGER
- `grid_confidence` FLOAT
- `is_variable_tempo` BOOLEAN NOT NULL DEFAULT '0'
- `is_canonical` BOOLEAN NOT NULL DEFAULT '0'
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_beatgrid_change_points` (0 rows)
- `point_id` INTEGER PK NOT NULL
- `beatgrid_id` INTEGER NOT NULL -> dj_beatgrid.beatgrid_id
- `position_ms` INTEGER NOT NULL
- `bpm` FLOAT NOT NULL
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_cue_points` (0 rows)
- `cue_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `position_ms` INTEGER NOT NULL
- `cue_kind` SMALLINT NOT NULL
- `hotcue_index` SMALLINT
- `label` VARCHAR(200)
- `color_rgb` INTEGER
- `is_quantized` BOOLEAN
- `source_app` SMALLINT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_library_items` (1,206 rows)
- `library_item_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `file_uri` VARCHAR(1000)
- `file_path` VARCHAR(1000)
- `file_hash` BLOB
- `file_size_bytes` INTEGER
- `mime_type` VARCHAR(50)
- `bitrate_kbps` INTEGER
- `sample_rate_hz` INTEGER
- `channels` SMALLINT
- `source_app` SMALLINT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_playlist_items` (809 rows)
- `playlist_item_id` INTEGER PK NOT NULL
- `playlist_id` INTEGER NOT NULL -> dj_playlists.playlist_id
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `sort_index` INTEGER NOT NULL
- `added_at` DATETIME

### `dj_playlists` (4 rows)
- `playlist_id` INTEGER PK NOT NULL
- `parent_playlist_id` INTEGER -> dj_playlists.playlist_id
- `name` VARCHAR(500) NOT NULL
- `source_app` SMALLINT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `source_of_truth` VARCHAR(20) NOT NULL DEFAULT 'local'
- `platform_ids` JSON

### `dj_saved_loops` (0 rows)
- `loop_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `in_ms` INTEGER NOT NULL
- `out_ms` INTEGER NOT NULL
- `length_ms` INTEGER NOT NULL
- `hotcue_index` SMALLINT
- `label` VARCHAR(200)
- `is_active_on_load` BOOLEAN
- `color_rgb` INTEGER
- `source_app` SMALLINT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_set_constraints` (0 rows)
- `constraint_id` INTEGER PK NOT NULL
- `set_version_id` INTEGER NOT NULL -> dj_set_versions.set_version_id
- `constraint_type` VARCHAR(100) NOT NULL
- `value` JSON NOT NULL
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_set_feedback` (0 rows)
- `feedback_id` INTEGER PK NOT NULL
- `set_version_id` INTEGER NOT NULL -> dj_set_versions.set_version_id
- `set_item_id` INTEGER -> dj_set_items.set_item_id
- `rating` SMALLINT NOT NULL
- `feedback_type` VARCHAR(20) NOT NULL
- `notes` VARCHAR
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_set_items` (903 rows)
- `set_item_id` INTEGER PK NOT NULL
- `set_version_id` INTEGER NOT NULL -> dj_set_versions.set_version_id
- `sort_index` INTEGER NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `transition_id` INTEGER -> transitions.transition_id
- `in_section_id` INTEGER
- `out_section_id` INTEGER
- `mix_in_ms` INTEGER
- `mix_out_ms` INTEGER
- `planned_eq` JSON
- `notes` VARCHAR
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `pinned` BOOLEAN NOT NULL DEFAULT 0

### `dj_set_versions` (17 rows)
- `set_version_id` INTEGER PK NOT NULL
- `set_id` INTEGER NOT NULL -> dj_sets.set_id
- `version_label` VARCHAR(100)
- `generator_run` JSON
- `score` FLOAT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `dj_sets` (11 rows)
- `set_id` INTEGER PK NOT NULL
- `name` VARCHAR(500) NOT NULL
- `description` VARCHAR
- `target_duration_ms` INTEGER
- `target_bpm_min` FLOAT
- `target_bpm_max` FLOAT
- `target_energy_arc` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `ym_playlist_id` INTEGER
- `template_name` VARCHAR(50)
- `source_playlist_id` INTEGER

### `embedding_types` (0 rows)
- `embedding_type` VARCHAR(100) PK NOT NULL
- `dim` INTEGER NOT NULL
- `model_name` VARCHAR(200)
- `description` VARCHAR
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `feature_extraction_runs` (591 rows)
- `run_id` INTEGER PK NOT NULL
- `pipeline_name` VARCHAR(200) NOT NULL
- `pipeline_version` VARCHAR(50) NOT NULL
- `parameters` JSON
- `code_ref` VARCHAR(200)
- `status` VARCHAR(20) NOT NULL DEFAULT 'running'
- `started_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `completed_at` DATETIME
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `genres` (0 rows)
- `genre_id` INTEGER PK NOT NULL
- `name` VARCHAR(200) NOT NULL
- `parent_genre_id` INTEGER -> genres.genre_id

### `key_edges` (0 rows)
- `from_key_code` SMALLINT PK NOT NULL -> keys.key_code
- `to_key_code` SMALLINT PK NOT NULL -> keys.key_code
- `distance` FLOAT NOT NULL
- `weight` FLOAT NOT NULL
- `rule` VARCHAR(100)
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `keys` (24 rows)
- `key_code` SMALLINT PK NOT NULL
- `pitch_class` SMALLINT NOT NULL
- `mode` SMALLINT NOT NULL
- `name` VARCHAR(10) NOT NULL
- `camelot` VARCHAR(5)

### `labels` (0 rows)
- `label_id` INTEGER PK NOT NULL
- `name` VARCHAR(300) NOT NULL
- `name_sort` VARCHAR(300)
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `provider_track_ids` (1,218 rows)
- `id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `provider_id` SMALLINT NOT NULL -> providers.provider_id
- `provider_track_id` VARCHAR(200) NOT NULL
- `provider_country` VARCHAR(2)
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `providers` (5 rows)
- `provider_id` SMALLINT PK NOT NULL
- `provider_code` VARCHAR(50) NOT NULL
- `name` VARCHAR(100) NOT NULL

### `raw_provider_responses` (0 rows)
- `id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `provider_id` SMALLINT NOT NULL -> providers.provider_id
- `provider_track_id` VARCHAR(200) NOT NULL
- `endpoint` VARCHAR(100)
- `payload` JSON NOT NULL
- `ingested_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `releases` (0 rows)
- `release_id` INTEGER PK NOT NULL
- `title` VARCHAR(500) NOT NULL
- `label_id` INTEGER -> labels.label_id
- `release_date` DATE
- `release_date_precision` VARCHAR(5)
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `soundcloud_metadata` (0 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `soundcloud_track_id` VARCHAR(100) NOT NULL
- `soundcloud_user_id` VARCHAR(100)
- `bpm` INTEGER
- `key_signature` VARCHAR(20)
- `genre` VARCHAR(200)
- `duration_ms` INTEGER
- `playback_count` INTEGER
- `favoritings_count` INTEGER
- `reposts_count` INTEGER
- `comment_count` INTEGER
- `downloadable` BOOLEAN
- `streamable` BOOLEAN
- `permalink_url` VARCHAR(500)
- `artwork_url` VARCHAR(500)
- `label_name` VARCHAR(300)
- `release_date` DATE
- `is_explicit` BOOLEAN
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `spotify_album_metadata` (0 rows)
- `spotify_album_id` VARCHAR(100) PK NOT NULL
- `album_type` VARCHAR(50)
- `name` VARCHAR(500)
- `label` VARCHAR(300)
- `popularity` INTEGER
- `release_date` VARCHAR(50)
- `total_tracks` INTEGER
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `spotify_artist_metadata` (0 rows)
- `spotify_artist_id` VARCHAR(100) PK NOT NULL
- `name` VARCHAR(300)
- `popularity` INTEGER
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `spotify_audio_features` (0 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `danceability` FLOAT NOT NULL
- `energy` FLOAT NOT NULL
- `loudness` FLOAT NOT NULL
- `speechiness` FLOAT NOT NULL
- `acousticness` FLOAT NOT NULL
- `instrumentalness` FLOAT NOT NULL
- `liveness` FLOAT NOT NULL
- `valence` FLOAT NOT NULL
- `tempo` FLOAT NOT NULL
- `time_signature` SMALLINT NOT NULL
- `key` SMALLINT NOT NULL
- `mode` SMALLINT NOT NULL
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `spotify_metadata` (0 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `spotify_track_id` VARCHAR(100) NOT NULL
- `spotify_album_id` VARCHAR(100) -> spotify_album_metadata.spotify_album_id
- `explicit` BOOLEAN NOT NULL
- `popularity` SMALLINT
- `duration_ms` INTEGER
- `preview_url` VARCHAR(500)
- `release_date` DATE
- `release_date_precision` VARCHAR(5)
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `spotify_playlist_metadata` (0 rows)
- `spotify_playlist_id` VARCHAR(100) PK NOT NULL
- `name` VARCHAR(500)
- `description` VARCHAR
- `public` BOOLEAN
- `snapshot_id` VARCHAR(100)
- `owner` JSON
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_artists` (1,371 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `artist_id` INTEGER PK NOT NULL -> artists.artist_id
- `role` SMALLINT PK NOT NULL
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_audio_features_computed` (583 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `run_id` INTEGER PK NOT NULL -> feature_extraction_runs.run_id
- `bpm` FLOAT NOT NULL
- `tempo_confidence` FLOAT NOT NULL
- `bpm_stability` FLOAT NOT NULL
- `is_variable_tempo` BOOLEAN NOT NULL DEFAULT '0'
- `lufs_i` FLOAT NOT NULL
- `lufs_s_mean` FLOAT
- `lufs_m_max` FLOAT
- `rms_dbfs` FLOAT NOT NULL
- `true_peak_db` FLOAT
- `crest_factor_db` FLOAT
- `lra_lu` FLOAT
- `energy_mean` FLOAT NOT NULL
- `energy_max` FLOAT NOT NULL
- `energy_std` FLOAT NOT NULL
- `energy_slope_mean` FLOAT
- `sub_energy` FLOAT
- `low_energy` FLOAT
- `lowmid_energy` FLOAT
- `mid_energy` FLOAT
- `highmid_energy` FLOAT
- `high_energy` FLOAT
- `low_high_ratio` FLOAT
- `sub_lowmid_ratio` FLOAT
- `centroid_mean_hz` FLOAT
- `rolloff_85_hz` FLOAT
- `rolloff_95_hz` FLOAT
- `flatness_mean` FLOAT
- `flux_mean` FLOAT
- `flux_std` FLOAT
- `slope_db_per_oct` FLOAT
- `contrast_mean_db` FLOAT
- `key_code` SMALLINT NOT NULL -> keys.key_code
- `key_confidence` FLOAT NOT NULL
- `is_atonal` BOOLEAN NOT NULL DEFAULT '0'
- `chroma` VARCHAR(500)
- `hnr_mean_db` FLOAT
- `chroma_entropy` FLOAT
- `mfcc_vector` VARCHAR(500)
- `hp_ratio` FLOAT
- `onset_rate_mean` FLOAT
- `onset_rate_max` FLOAT
- `pulse_clarity` FLOAT
- `kick_prominence` FLOAT
- `computed_from_asset_type` SMALLINT DEFAULT '0'
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_embeddings` (0 rows)
- `embedding_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `run_id` INTEGER -> feature_extraction_runs.run_id
- `embedding_type` VARCHAR(100) NOT NULL -> embedding_types.embedding_type
- `vector` VARCHAR(10000) NOT NULL
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_genres` (0 rows)
- `track_genre_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `genre_id` INTEGER NOT NULL -> genres.genre_id
- `source_provider_id` SMALLINT -> providers.provider_id
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_releases` (0 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `release_id` INTEGER PK NOT NULL -> releases.release_id
- `track_number` SMALLINT
- `disc_number` SMALLINT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_sections` (45,117 rows)
- `section_id` INTEGER PK NOT NULL
- `track_id` INTEGER NOT NULL -> tracks.track_id
- `run_id` INTEGER NOT NULL -> feature_extraction_runs.run_id
- `start_ms` INTEGER NOT NULL
- `end_ms` INTEGER NOT NULL
- `section_type` SMALLINT NOT NULL
- `section_duration_ms` INTEGER NOT NULL
- `section_energy_mean` FLOAT
- `section_energy_max` FLOAT
- `section_energy_slope` FLOAT
- `section_centroid_hz` FLOAT
- `section_flux` FLOAT
- `section_onset_rate` FLOAT
- `section_pulse_clarity` FLOAT
- `boundary_confidence` FLOAT
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `track_timeseries_refs` (0 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `run_id` INTEGER PK NOT NULL -> feature_extraction_runs.run_id
- `feature_set` VARCHAR(100) PK NOT NULL
- `storage_uri` VARCHAR(500) NOT NULL
- `frame_count` INTEGER NOT NULL
- `hop_length` INTEGER NOT NULL
- `sample_rate` INTEGER NOT NULL
- `dtype` VARCHAR(20) NOT NULL
- `shape` VARCHAR(50)
- `file_size` INTEGER
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `tracks` (1,420 rows)
- `track_id` INTEGER PK NOT NULL
- `title` VARCHAR(500) NOT NULL
- `title_sort` VARCHAR(500)
- `duration_ms` INTEGER NOT NULL
- `status` SMALLINT NOT NULL DEFAULT '0'
- `archived_at` DATETIME
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `transition_candidates` (0 rows)
- `from_track_id` INTEGER PK NOT NULL -> tracks.track_id
- `to_track_id` INTEGER PK NOT NULL -> tracks.track_id
- `run_id` INTEGER PK NOT NULL -> transition_runs.run_id
- `bpm_distance` FLOAT NOT NULL
- `key_distance` FLOAT NOT NULL
- `embedding_similarity` FLOAT
- `energy_delta` FLOAT
- `is_fully_scored` BOOLEAN NOT NULL
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `transition_runs` (0 rows)
- `run_id` INTEGER PK NOT NULL
- `pipeline_name` VARCHAR(200) NOT NULL
- `pipeline_version` VARCHAR(50) NOT NULL
- `weights` JSON
- `constraints` JSON
- `status` VARCHAR(20) NOT NULL DEFAULT 'running'
- `started_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `completed_at` DATETIME
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `transitions` (0 rows)
- `transition_id` INTEGER PK NOT NULL
- `run_id` INTEGER NOT NULL -> transition_runs.run_id
- `from_track_id` INTEGER NOT NULL -> tracks.track_id
- `to_track_id` INTEGER NOT NULL -> tracks.track_id
- `from_section_id` INTEGER
- `to_section_id` INTEGER
- `overlap_ms` INTEGER NOT NULL
- `bpm_distance` FLOAT NOT NULL
- `energy_step` FLOAT NOT NULL
- `centroid_gap_hz` FLOAT
- `low_conflict_score` FLOAT
- `overlap_score` FLOAT
- `groove_similarity` FLOAT
- `key_distance_weighted` FLOAT
- `transition_quality` FLOAT NOT NULL
- `trans_feature` VARCHAR(500)
- `computed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

### `yandex_metadata` (1,000 rows)
- `track_id` INTEGER PK NOT NULL -> tracks.track_id
- `yandex_track_id` VARCHAR(50) NOT NULL
- `yandex_album_id` VARCHAR(50)
- `album_title` VARCHAR(500)
- `album_type` VARCHAR(50)
- `album_genre` VARCHAR(100)
- `album_year` INTEGER
- `label_name` VARCHAR(300)
- `release_date` VARCHAR(10)
- `duration_ms` INTEGER
- `cover_uri` VARCHAR(500)
- `explicit` BOOLEAN
- `extra` JSON
- `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
- `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
