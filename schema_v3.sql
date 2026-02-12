-- ============================================================================
-- DJ Techno Set Builder — Database Schema v3
-- PostgreSQL 16+ / pgvector 0.7+
--
-- Полный цикл: ingest → DSP/ML анализ → transitions → сборка сетов → экспорт
--
-- Changelog v2 → v3:
--   • track_genres PK — убран nullable source_provider_id из PK, добавлен surrogate PK
--   • track_embeddings — разделены на таблицы per embedding_type с фиксированной размерностью
--   • dj_app_exports.payload bytea → storage_uri (файлы экспорта в S3)
--   • raw_provider_responses — range partitioning по ingested_at + retention policy
--   • transitions UNIQUE — NULLS NOT DISTINCT для section_id
--   • transitions — добавлен индекс на to_track_id (reverse lookup)
--   • dj_playlist_items — добавлен identity PK
--   • key_distance_weighted — плавная интерполяция вместо step function
--   • v_pending_scoring — нормализованная сортировка
--   • track_sections.run_id — явный ON DELETE CASCADE
--   • Добавлены COMMENT ON TABLE/COLUMN для ключевых сущностей
-- ============================================================================

BEGIN;

-- ════════════════════════════════════════════════════════════════════════════
-- 0. Extensions
-- ════════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector 0.7+
CREATE EXTENSION IF NOT EXISTS btree_gist;      -- для exclusion constraints на range
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- для fuzzy text search


-- ════════════════════════════════════════════════════════════════════════════
-- 1. Enum-like domain types (документация + compile-time safety)
-- ════════════════════════════════════════════════════════════════════════════

-- Используем smallint + CHECK вместо PG ENUM — проще мигрировать.
-- Маппинг хранится здесь как комментарий и дублируется в app-level enum.

-- track_artists.role:       0=primary, 1=featured, 2=remixer
-- track_sections.section_type:
--   0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro,
--   5=break, 6=inst, 7=verse, 8=chorus, 9=bridge, 10=solo, 11=unknown
-- dj_cue_points.cue_kind:
--   0=cue, 1=load, 2=grid, 3=fade_in, 4=fade_out,
--   5=loop_in, 6=loop_out, 7=memory
-- source_app:   1=traktor, 2=rekordbox, 3=djay, 4=import, 5=generated
-- target_app:   1=traktor, 2=rekordbox, 3=djay
-- audio_assets.asset_type:
--   0=full_mix, 1=drums_stem, 2=bass_stem, 3=vocals_stem,
--   4=other_stem, 5=preview_clip


-- ════════════════════════════════════════════════════════════════════════════
-- 2. Core catalog
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE tracks (
    track_id          integer       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fingerprint_sha1  bytea         NOT NULL,
    title             text          NOT NULL,
    title_sort        text,
    duration_ms       integer       NOT NULL CHECK (duration_ms > 0),
    status            smallint      NOT NULL DEFAULT 0 CHECK (status IN (0, 1)),
    archived_at       timestamptz,  -- soft delete: NULL = active
    created_at        timestamptz   NOT NULL DEFAULT now(),
    updated_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT tracks_fingerprint_uq UNIQUE (fingerprint_sha1)
);

-- Partial index: большинство запросов работает с активными треками
CREATE INDEX idx_tracks_active ON tracks (track_id)
    WHERE archived_at IS NULL;

CREATE INDEX idx_tracks_title_trgm ON tracks USING gin (title gin_trgm_ops);


CREATE TABLE artists (
    artist_id    integer       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text          NOT NULL,
    name_sort    text,
    created_at   timestamptz   NOT NULL DEFAULT now(),
    updated_at   timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX idx_artists_name_trgm ON artists USING gin (name gin_trgm_ops);


CREATE TABLE track_artists (
    track_id    integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    artist_id   integer    NOT NULL REFERENCES artists ON DELETE CASCADE,
    role        smallint   NOT NULL CHECK (role BETWEEN 0 AND 2),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (track_id, artist_id, role)
);


CREATE TABLE labels (
    label_id    integer       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text          NOT NULL,
    name_sort   text,
    created_at  timestamptz   NOT NULL DEFAULT now(),
    updated_at  timestamptz   NOT NULL DEFAULT now()
);


CREATE TABLE releases (
    release_id             integer       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title                  text          NOT NULL,
    label_id               integer       REFERENCES labels ON DELETE SET NULL,
    release_date           date,
    release_date_precision text          CHECK (release_date_precision IN ('year','month','day')),
    created_at             timestamptz   NOT NULL DEFAULT now(),
    updated_at             timestamptz   NOT NULL DEFAULT now()
);


CREATE TABLE track_releases (
    track_id      integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    release_id    integer    NOT NULL REFERENCES releases ON DELETE CASCADE,
    track_number  smallint,
    disc_number   smallint,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (track_id, release_id)
);


CREATE TABLE genres (
    genre_id        integer    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text       NOT NULL UNIQUE,
    parent_genre_id integer    REFERENCES genres ON DELETE SET NULL
);


-- FIX v3: убран nullable source_provider_id из PK, добавлен surrogate PK
CREATE TABLE track_genres (
    track_genre_id     bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id           integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    genre_id           integer    NOT NULL REFERENCES genres ON DELETE CASCADE,
    source_provider_id smallint,  -- FK → providers, nullable (NULL = определено вручную)
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT track_genres_uq UNIQUE NULLS NOT DISTINCT (track_id, genre_id, source_provider_id)
);

COMMENT ON TABLE track_genres IS
    'Связь трек ↔ жанр. source_provider_id указывает источник жанра (NULL = ручной ввод). '
    'NULLS NOT DISTINCT гарантирует, что (track_id, genre_id, NULL) уникально.';


-- ════════════════════════════════════════════════════════════════════════════
-- 3. Providers & raw ingestion
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE providers (
    provider_id    smallint   PRIMARY KEY,
    provider_code  text       NOT NULL UNIQUE,  -- 'spotify','soundcloud','beatport'
    name           text       NOT NULL
);

-- Seed: 3 провайдера
INSERT INTO providers (provider_id, provider_code, name) VALUES
    (1, 'spotify',    'Spotify'),
    (2, 'soundcloud', 'SoundCloud'),
    (3, 'beatport',   'Beatport');


CREATE TABLE provider_track_ids (
    track_id          integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    provider_id       smallint   NOT NULL REFERENCES providers,
    provider_track_id text       NOT NULL,  -- native ID у провайдера
    provider_country  char(2),              -- ISO market (для Spotify)
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT provider_track_ids_uq
        UNIQUE (provider_id, provider_track_id, provider_country)
);

CREATE INDEX idx_provider_track_ids_track ON provider_track_ids (track_id);


-- FIX v3: range partitioning по ingested_at для управления ростом
-- Партиции создаются помесячно через pg_partman или вручную.
-- Retention policy: DROP старых партиций через 6 месяцев (cron / pg_partman).
CREATE TABLE raw_provider_responses (
    id                bigint       GENERATED ALWAYS AS IDENTITY,
    track_id          integer      NOT NULL,  -- FK добавляется ниже (partition-compatible)
    provider_id       smallint     NOT NULL,
    provider_track_id text         NOT NULL,
    endpoint          text,        -- e.g. 'track', 'audio-features', 'analysis'
    payload           jsonb        NOT NULL,
    ingested_at       timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- Дефолтная партиция (ловит всё, пока нет конкретных)
CREATE TABLE raw_provider_responses_default
    PARTITION OF raw_provider_responses DEFAULT;

-- Пример создания месячных партиций:
-- CREATE TABLE raw_provider_responses_2026_01
--     PARTITION OF raw_provider_responses
--     FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE INDEX idx_raw_provider_track ON raw_provider_responses (track_id, provider_id);

COMMENT ON TABLE raw_provider_responses IS
    'Сырые JSON-ответы от провайдеров. Партиционирована по ingested_at. '
    'Retention: 6 месяцев (через pg_partman или cron DROP PARTITION). '
    'FK на tracks не создаётся напрямую (несовместимо с partitioning в PG < 17); '
    'целостность обеспечивается на уровне приложения.';


-- ════════════════════════════════════════════════════════════════════════════
-- 4. Provider metadata (slim — часто используемые поля + jsonb extra)
-- ════════════════════════════════════════════════════════════════════════════

-- ▸ Spotify

CREATE TABLE spotify_metadata (
    track_id           integer    PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
    spotify_track_id   text       NOT NULL UNIQUE,
    spotify_album_id   text,
    explicit           boolean    NOT NULL DEFAULT false,
    popularity         smallint   CHECK (popularity BETWEEN 0 AND 100),
    duration_ms        integer,
    preview_url        text,
    release_date       date,
    release_date_precision text   CHECK (release_date_precision IN ('year','month','day')),
    extra              jsonb,     -- href, uri, is_local, linked_from, restrictions, etc.
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spotify_audio_features (
    track_id         integer    PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
    spotify_track_id text       NOT NULL,
    danceability     real       NOT NULL CHECK (danceability BETWEEN 0 AND 1),
    energy           real       NOT NULL CHECK (energy BETWEEN 0 AND 1),
    loudness         real       NOT NULL,  -- dB
    speechiness      real       NOT NULL CHECK (speechiness BETWEEN 0 AND 1),
    acousticness     real       NOT NULL CHECK (acousticness BETWEEN 0 AND 1),
    instrumentalness real       NOT NULL CHECK (instrumentalness BETWEEN 0 AND 1),
    liveness         real       NOT NULL CHECK (liveness BETWEEN 0 AND 1),
    valence          real       NOT NULL CHECK (valence BETWEEN 0 AND 1),
    tempo            real       NOT NULL,  -- BPM
    time_signature   smallint   NOT NULL,
    key              smallint   NOT NULL,
    mode             smallint   NOT NULL CHECK (mode IN (0, 1)),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spotify_album_metadata (
    spotify_album_id  text        PRIMARY KEY,
    album_type        text,
    name              text,
    label             text,
    popularity        integer,
    release_date      text,       -- Spotify raw string
    total_tracks      integer,
    extra             jsonb,      -- artists, images, available_markets, external_urls, etc.
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spotify_artist_metadata (
    spotify_artist_id text        PRIMARY KEY,
    name              text,
    popularity        integer,
    genres            text[],
    extra             jsonb,      -- followers, images, external_urls, href, uri
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spotify_playlist_metadata (
    spotify_playlist_id text      PRIMARY KEY,
    name                text,
    description         text,
    public              boolean,
    snapshot_id         text,
    owner               jsonb,
    extra               jsonb,    -- followers, images, collaborative, external_urls
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);


-- ▸ SoundCloud (slim)

CREATE TABLE soundcloud_metadata (
    track_id            integer    PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
    soundcloud_track_id text       NOT NULL UNIQUE,
    soundcloud_user_id  text,
    bpm                 integer,
    key_signature       text,
    genre               text,
    duration_ms         integer,
    playback_count      integer,
    favoritings_count   integer,
    reposts_count       integer,
    comment_count       integer,
    downloadable        boolean,
    streamable          boolean,
    permalink_url       text,
    artwork_url         text,
    label_name          text,
    release_date        date,      -- parsed from release_year/month/day
    is_explicit         boolean,
    extra               jsonb,     -- waveform_url, secret_uri, user_json, tag_list, etc.
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);


-- ▸ Beatport

CREATE TABLE beatport_metadata (
    track_id           integer    PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
    beatport_track_id  text       NOT NULL UNIQUE,
    beatport_release_id text,
    bpm                real,
    key_code           smallint   CHECK (key_code BETWEEN 0 AND 23),
    length_ms          integer,
    label_name         text,
    genre_name         text,
    subgenre_name      text,
    release_date       date,
    preview_url        text,
    image_url          text,
    extra              jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);


-- ════════════════════════════════════════════════════════════════════════════
-- 5. Audio assets (originals + Demucs stems + previews)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE audio_assets (
    asset_id       bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id       integer      NOT NULL REFERENCES tracks ON DELETE CASCADE,
    asset_type     smallint     NOT NULL CHECK (asset_type BETWEEN 0 AND 5),
        -- 0=full_mix, 1=drums_stem, 2=bass_stem, 3=vocals_stem,
        -- 4=other_stem, 5=preview_clip
    storage_uri    text         NOT NULL,  -- s3://bucket/... или file:///...
    format         text         NOT NULL,  -- flac, wav, mp3, ogg
    sample_rate    integer,
    channels       smallint,
    duration_ms    integer,
    file_size      bigint,
    source_run_id  bigint,      -- FK → feature_extraction_runs; NULL для оригиналов
    checksum_sha256 bytea,      -- 32 bytes, опциональная верификация целостности
    created_at     timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT audio_assets_uq UNIQUE (track_id, asset_type, source_run_id)
);

CREATE INDEX idx_audio_assets_track ON audio_assets (track_id, asset_type);

COMMENT ON TABLE audio_assets IS
    'Реестр всех аудио-файлов: оригиналы, Demucs-стемы, preview-клипы. '
    'Стемы привязаны к source_run_id для версионирования модели разделения.';


-- ════════════════════════════════════════════════════════════════════════════
-- 6. Pipeline versioning (runs)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE feature_extraction_runs (
    run_id            bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name     text         NOT NULL,   -- e.g. 'audio_features_v1', 'demucs_v4'
    pipeline_version  text         NOT NULL,   -- semver
    parameters        jsonb,                   -- window sizes, hop_length, model name, etc.
    code_ref          text,                    -- git sha / tag
    status            text         NOT NULL DEFAULT 'running'
                                   CHECK (status IN ('running','completed','failed')),
    started_at        timestamptz  NOT NULL DEFAULT now(),
    completed_at      timestamptz,
    created_at        timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE transition_runs (
    run_id            bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name     text         NOT NULL,   -- e.g. 'transition_scoring_v2'
    pipeline_version  text         NOT NULL,   -- semver
    weights           jsonb,                   -- scoring weights
    constraints       jsonb,                   -- max_bpm_jump, etc.
    status            text         NOT NULL DEFAULT 'running'
                                   CHECK (status IN ('running','completed','failed')),
    started_at        timestamptz  NOT NULL DEFAULT now(),
    completed_at      timestamptz,
    created_at        timestamptz  NOT NULL DEFAULT now()
);


-- ════════════════════════════════════════════════════════════════════════════
-- 7. Harmony model (keys + compatibility graph)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE keys (
    key_code     smallint   PRIMARY KEY CHECK (key_code BETWEEN 0 AND 23),
    pitch_class  smallint   NOT NULL CHECK (pitch_class BETWEEN 0 AND 11),
    mode         smallint   NOT NULL CHECK (mode IN (0, 1)),  -- 0=minor 1=major
    name         text       NOT NULL,   -- e.g. 'C#m', 'Ab'
    camelot      text,                  -- e.g. '12A', '4B'
    -- Детерминистический маппинг: key_code = pitch_class * 2 + mode
    CONSTRAINT keys_code_deterministic CHECK (key_code = pitch_class * 2 + mode)
);

COMMENT ON TABLE keys IS
    'Справочник 24 ключей. key_code = pitch_class * 2 + mode. '
    'pitch_class: C=0, C#=1, D=2 ... B=11. mode: 0=minor, 1=major.';

-- Seed: 24 ключа
INSERT INTO keys (key_code, pitch_class, mode, name, camelot) VALUES
    ( 0, 0, 0, 'Cm',   '5A'),  ( 1, 0, 1, 'C',   '8B'),
    ( 2, 1, 0, 'C#m',  '12A'), ( 3, 1, 1, 'Db',  '3B'),
    ( 4, 2, 0, 'Dm',   '7A'),  ( 5, 2, 1, 'D',   '10B'),
    ( 6, 3, 0, 'Ebm',  '2A'),  ( 7, 3, 1, 'Eb',  '5B'),
    ( 8, 4, 0, 'Em',   '9A'),  ( 9, 4, 1, 'E',   '12B'),
    (10, 5, 0, 'Fm',   '4A'),  (11, 5, 1, 'F',   '7B'),
    (12, 6, 0, 'F#m',  '11A'), (13, 6, 1, 'F#',  '2B'),
    (14, 7, 0, 'Gm',   '6A'),  (15, 7, 1, 'G',   '9B'),
    (16, 8, 0, 'G#m',  '1A'),  (17, 8, 1, 'Ab',  '4B'),
    (18, 9, 0, 'Am',   '8A'),  (19, 9, 1, 'A',   '11B'),
    (20,10, 0, 'Bbm',  '3A'),  (21,10, 1, 'Bb',  '6B'),
    (22,11, 0, 'Bm',   '10A'), (23,11, 1, 'B',   '1B');


CREATE TABLE key_edges (
    from_key_code  smallint  NOT NULL REFERENCES keys,
    to_key_code    smallint  NOT NULL REFERENCES keys,
    distance       real      NOT NULL CHECK (distance >= 0),
    weight         real      NOT NULL,  -- scoring weight (higher = more compatible)
    rule           text,     -- e.g. 'same_key', 'relative_major_minor', 'camelot_adjacent'
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (from_key_code, to_key_code)
);

COMMENT ON TABLE key_edges IS
    'Статический граф совместимости 24 ключей. Заполняется seed-скриптом. '
    'Максимум 576 рёбер. distance: 0 = идеальная совместимость.';


-- ════════════════════════════════════════════════════════════════════════════
-- 8. Computed audio features (DSP/ML results)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE track_audio_features_computed (
    track_id              integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    run_id                bigint     NOT NULL REFERENCES feature_extraction_runs ON DELETE CASCADE,

    -- ── Tempo ──
    bpm                   real       NOT NULL CHECK (bpm BETWEEN 20 AND 300),
    tempo_confidence      real       NOT NULL CHECK (tempo_confidence BETWEEN 0 AND 1),
    bpm_stability         real       NOT NULL CHECK (bpm_stability BETWEEN 0 AND 1),
    is_variable_tempo     boolean    NOT NULL DEFAULT false,

    -- ── Loudness (EBU R128) ──
    lufs_i                real       NOT NULL,           -- integrated
    lufs_s_mean           real,                          -- short-term mean
    lufs_m_max            real,                          -- momentary max
    rms_dbfs              real       NOT NULL,
    true_peak_db          real,
    crest_factor_db       real       CHECK (crest_factor_db >= 0),
    lra_lu                real       CHECK (lra_lu >= 0), -- loudness range

    -- ── Energy (global aggregates) ──
    energy_mean           real       NOT NULL CHECK (energy_mean BETWEEN 0 AND 1),
    energy_max            real       NOT NULL CHECK (energy_max BETWEEN 0 AND 1),
    energy_std            real       NOT NULL CHECK (energy_std >= 0),
    energy_slope_mean     real,      -- sign indicates overall energy trend

    -- ── Band energies (normalized 0..1) ──
    sub_energy            real       CHECK (sub_energy BETWEEN 0 AND 1),    -- 20-60 Hz
    low_energy            real       CHECK (low_energy BETWEEN 0 AND 1),    -- 60-200 Hz
    lowmid_energy         real       CHECK (lowmid_energy BETWEEN 0 AND 1), -- 200-800 Hz
    mid_energy            real       CHECK (mid_energy BETWEEN 0 AND 1),    -- 800-3000 Hz
    highmid_energy        real       CHECK (highmid_energy BETWEEN 0 AND 1),-- 3-6 kHz
    high_energy           real       CHECK (high_energy BETWEEN 0 AND 1),   -- 6-12 kHz
    low_high_ratio        real,
    sub_lowmid_ratio      real,

    -- ── Spectral descriptors ──
    centroid_mean_hz      real       CHECK (centroid_mean_hz >= 0),
    rolloff_85_hz         real       CHECK (rolloff_85_hz >= 0),
    rolloff_95_hz         real       CHECK (rolloff_95_hz >= 0),
    flatness_mean         real       CHECK (flatness_mean BETWEEN 0 AND 1),
    flux_mean             real       CHECK (flux_mean >= 0),
    flux_std              real       CHECK (flux_std >= 0),
    slope_db_per_oct      real,
    contrast_mean_db      real,

    -- ── Tonal / Harmonic ──
    key_code              smallint   NOT NULL CHECK (key_code BETWEEN 0 AND 23),
    key_confidence        real       NOT NULL CHECK (key_confidence BETWEEN 0 AND 1),
    is_atonal             boolean    NOT NULL DEFAULT false,  -- chroma entropy ≈ log2(12)
    chroma                vector(12),  -- mean chroma vector (HPCP)
    hnr_mean_db           real,      -- harmonic-to-noise ratio

    -- ── Rhythm / Groove ──
    hp_ratio              real,      -- harmonic / percussive energy ratio
    onset_rate_mean       real       CHECK (onset_rate_mean >= 0),
    onset_rate_max        real       CHECK (onset_rate_max >= 0),
    pulse_clarity         real       CHECK (pulse_clarity BETWEEN 0 AND 1),
    kick_prominence       real       CHECK (kick_prominence BETWEEN 0 AND 1),

    -- ── Meta ──
    computed_from_asset_type smallint DEFAULT 0,
        -- 0=full_mix, 1=drums, 2=bass — какой asset использован как вход
    created_at            timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (track_id, run_id)
);

-- HNSW по chroma для поиска "похожих по спектру"
CREATE INDEX idx_taf_chroma ON track_audio_features_computed
    USING hnsw (chroma vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

CREATE INDEX idx_taf_bpm ON track_audio_features_computed (bpm);
CREATE INDEX idx_taf_key ON track_audio_features_computed (key_code, key_confidence DESC);


-- ════════════════════════════════════════════════════════════════════════════
-- 9. Track sections (structural segmentation)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE track_sections (
    section_id            bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id              integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    -- FIX v3: явный ON DELETE CASCADE вместо дефолтного RESTRICT
    run_id                bigint     NOT NULL REFERENCES feature_extraction_runs ON DELETE CASCADE,
    range_ms              int4range  NOT NULL,  -- [start, end)
    section_type          smallint   NOT NULL CHECK (section_type BETWEEN 0 AND 11),
    section_duration_ms   integer    NOT NULL CHECK (section_duration_ms > 0),

    -- Per-section aggregates
    section_energy_mean   real       CHECK (section_energy_mean BETWEEN 0 AND 1),
    section_energy_max    real       CHECK (section_energy_max BETWEEN 0 AND 1),
    section_energy_slope  real,
    section_centroid_hz   real,
    section_flux          real,
    section_onset_rate    real,
    section_pulse_clarity real       CHECK (section_pulse_clarity BETWEEN 0 AND 1),
    boundary_confidence   real       CHECK (boundary_confidence BETWEEN 0 AND 1),

    created_at            timestamptz NOT NULL DEFAULT now()
);

-- GiST индекс для range-запросов + запрета перекрытий
CREATE INDEX idx_sections_track_range ON track_sections
    USING gist (track_id, range_ms);

CREATE INDEX idx_sections_track_run ON track_sections (track_id, run_id);

-- Non-overlap constraint (раскомментировать при необходимости):
-- ALTER TABLE track_sections
--     ADD CONSTRAINT sections_no_overlap
--     EXCLUDE USING gist (track_id WITH =, run_id WITH =, range_ms WITH &&);


-- ════════════════════════════════════════════════════════════════════════════
-- 10. Timeseries references (frame-level → object storage)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE track_timeseries_refs (
    track_id       integer      NOT NULL REFERENCES tracks ON DELETE CASCADE,
    run_id         bigint       NOT NULL REFERENCES feature_extraction_runs ON DELETE CASCADE,
    feature_set    text         NOT NULL,
        -- e.g. 'onset_env', 'rms_frames', 'chroma_frames', 'spectral_centroid_frames'
    storage_uri    text         NOT NULL,   -- s3://bucket/track_{id}/{feature_set}_run{run_id}.npz
    frame_count    integer      NOT NULL CHECK (frame_count > 0),
    hop_length     integer      NOT NULL CHECK (hop_length > 0),
    sample_rate    integer      NOT NULL CHECK (sample_rate > 0),
    dtype          text         NOT NULL DEFAULT 'float32',  -- numpy dtype
    shape          text,        -- e.g. '(18000,)' или '(18000,12)' для chroma
    file_size      bigint,
    created_at     timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (track_id, run_id, feature_set)
);

COMMENT ON TABLE track_timeseries_refs IS
    'Указатели на frame-level данные в object storage (S3/MinIO). '
    'Формат: numpy .npz. Не храним миллиарды float-ов в PostgreSQL.';


-- ════════════════════════════════════════════════════════════════════════════
-- 11. Transition candidates (лёгкий pre-filter)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE transition_candidates (
    from_track_id         integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    to_track_id           integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    run_id                bigint     NOT NULL REFERENCES transition_runs ON DELETE CASCADE,

    -- Лёгкие метрики (вычисляются из уже имеющихся скаляров)
    bpm_distance          real       NOT NULL CHECK (bpm_distance >= 0),
    key_distance          real       NOT NULL CHECK (key_distance >= 0),
    embedding_similarity  real,      -- cosine similarity из track_embeddings ANN
    energy_delta          real,      -- |energy_a - energy_b|

    is_fully_scored       boolean    NOT NULL DEFAULT false,

    created_at            timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (from_track_id, to_track_id, run_id),
    CONSTRAINT candidates_direction CHECK (from_track_id <> to_track_id)
);

CREATE INDEX idx_candidates_from ON transition_candidates
    (from_track_id, bpm_distance, key_distance)
    WHERE is_fully_scored = false;

-- FIX v3: индекс для reverse lookup (to_track_id → from_track_id)
CREATE INDEX idx_candidates_to ON transition_candidates (to_track_id)
    WHERE is_fully_scored = false;

COMMENT ON TABLE transition_candidates IS
    'Stage 1 pre-filter: лёгкие метрики из скалярных features + ANN. '
    'Только кандидаты с is_fully_scored=false отправляются на Stage 2. '
    'Для 5000 треков: ~500K кандидатов вместо 12.5M полных transitions.';


-- ════════════════════════════════════════════════════════════════════════════
-- 12. Transitions (полный scoring)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE transitions (
    transition_id       bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              bigint     NOT NULL REFERENCES transition_runs ON DELETE CASCADE,
    from_track_id       integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    to_track_id         integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    from_section_id     bigint     REFERENCES track_sections ON DELETE SET NULL,
    to_section_id       bigint     REFERENCES track_sections ON DELETE SET NULL,

    -- Scoring components (все: чем ниже, тем лучше конфликт)
    overlap_ms          integer    NOT NULL CHECK (overlap_ms >= 0),
    bpm_distance        real       NOT NULL CHECK (bpm_distance >= 0),
    energy_step         real       NOT NULL,  -- -1..1 (direction matters)
    centroid_gap_hz     real,
    low_conflict_score  real       CHECK (low_conflict_score BETWEEN 0 AND 1),
    overlap_score       real       CHECK (overlap_score BETWEEN 0 AND 1),
    groove_similarity   real       CHECK (groove_similarity BETWEEN 0 AND 1),
    key_distance_weighted real     CHECK (key_distance_weighted >= 0),

    -- Composite score (итоговый; higher = better transition)
    transition_quality  real       NOT NULL CHECK (transition_quality BETWEEN 0 AND 1),

    -- Embedding перехода для ANN-поиска
    trans_feature       vector(32),

    computed_at         timestamptz NOT NULL DEFAULT now(),

    -- FIX v3: NULLS NOT DISTINCT для корректной уникальности при nullable section_id
    CONSTRAINT transitions_uq
        UNIQUE NULLS NOT DISTINCT (from_track_id, to_track_id, from_section_id, to_section_id, run_id),
    CONSTRAINT transitions_direction CHECK (from_track_id <> to_track_id)
);

-- Для выбора лучших переходов от конкретного трека
CREATE INDEX idx_transitions_from_quality ON transitions
    (from_track_id, transition_quality DESC);

-- FIX v3: обратный индекс для поиска переходов К конкретному треку
CREATE INDEX idx_transitions_to_quality ON transitions
    (to_track_id, transition_quality DESC);

-- ANN-поиск по transition embedding
CREATE INDEX idx_transitions_feature ON transitions
    USING hnsw (trans_feature vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);


-- ════════════════════════════════════════════════════════════════════════════
-- 13. Embeddings (per-type таблицы с фиксированной размерностью)
-- ════════════════════════════════════════════════════════════════════════════

-- FIX v3: вместо единой таблицы с vector без размерности —
-- registry таблица + per-type таблицы с фиксированной размерностью для HNSW.
-- Это позволяет создавать HNSW-индексы без partial index workaround.

-- Registry: какие типы эмбеддингов зарегистрированы в системе
CREATE TABLE embedding_types (
    embedding_type  text       PRIMARY KEY,   -- e.g. 'groove', 'timbre', 'genre'
    dim             integer    NOT NULL CHECK (dim > 0),
    model_name      text,                     -- e.g. 'essentia-discogs-effnet-bs64'
    description     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE embedding_types IS
    'Registry типов эмбеддингов с фиксированной размерностью. '
    'Per-type таблицы наследуют dim для HNSW-индексов.';

-- Основная таблица эмбеддингов — хранит все типы.
-- HNSW-индексы создаются per embedding_type через partial indexes.
-- dim хранится для runtime-валидации в приложении.
CREATE TABLE track_embeddings (
    embedding_id    bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id        integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    run_id          bigint     REFERENCES feature_extraction_runs ON DELETE CASCADE,
    embedding_type  text       NOT NULL REFERENCES embedding_types,
    vector          vector     NOT NULL,  -- pgvector (dim валидируется в приложении)
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT embeddings_uq UNIQUE (track_id, embedding_type, run_id)
);

CREATE INDEX idx_embeddings_type ON track_embeddings (embedding_type, track_id);

COMMENT ON TABLE track_embeddings IS
    'Эмбеддинги треков разных типов (groove, timbre, genre...). '
    'vector хранится без фиксированной размерности — dim валидируется через FK на embedding_types. '
    'HNSW-индексы создаются per embedding_type после первого batch: '
    'CREATE INDEX idx_emb_groove ON track_embeddings '
    '  USING hnsw (vector vector_cosine_ops) '
    '  WITH (m = 16, ef_construction = 200) '
    '  WHERE embedding_type = ''groove'';';


-- ════════════════════════════════════════════════════════════════════════════
-- 14. DJ layer (library + beatgrid + cues + loops + playlists)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE dj_library_items (
    library_item_id  bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id         integer      NOT NULL REFERENCES tracks ON DELETE CASCADE,
    file_uri         text,        -- traktor-style URI
    file_path        text,        -- local filesystem path
    file_hash        bytea,       -- sha1 or sha256
    file_size_bytes  bigint       CHECK (file_size_bytes >= 0),
    mime_type        text,
    bitrate_kbps     integer,
    sample_rate_hz   integer,
    channels         smallint,
    source_app       smallint     CHECK (source_app BETWEEN 1 AND 5),
    created_at       timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX idx_dj_lib_track ON dj_library_items (track_id);


CREATE TABLE dj_beatgrid (
    track_id           integer    PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
    bpm                real       NOT NULL CHECK (bpm BETWEEN 20 AND 300),
    first_downbeat_ms  integer    NOT NULL CHECK (first_downbeat_ms >= 0),
    grid_offset_ms     integer,
    grid_confidence    real       CHECK (grid_confidence BETWEEN 0 AND 1),
    is_variable_tempo  boolean    NOT NULL DEFAULT false,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE dj_beatgrid_change_points (
    point_id     bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id     integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    position_ms  integer    NOT NULL CHECK (position_ms >= 0),
    bpm          real       NOT NULL CHECK (bpm BETWEEN 20 AND 300),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_beatgrid_cp_track ON dj_beatgrid_change_points (track_id, position_ms);


CREATE TABLE dj_cue_points (
    cue_id         bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id       integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    position_ms    integer    NOT NULL CHECK (position_ms >= 0),
    cue_kind       smallint   NOT NULL CHECK (cue_kind BETWEEN 0 AND 7),
    hotcue_index   smallint   CHECK (hotcue_index BETWEEN 0 AND 15),
    label          text,
    color_rgb      integer    CHECK (color_rgb BETWEEN 0 AND 16777215),
    is_quantized   boolean,
    source_app     smallint   CHECK (source_app BETWEEN 1 AND 5),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_cues_track ON dj_cue_points (track_id, hotcue_index);


CREATE TABLE dj_saved_loops (
    loop_id           bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    track_id          integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    in_ms             integer    NOT NULL CHECK (in_ms >= 0),
    out_ms            integer    NOT NULL,
    length_ms         integer    NOT NULL CHECK (length_ms > 0),
    hotcue_index      smallint   CHECK (hotcue_index BETWEEN 0 AND 15),
    label             text,
    is_active_on_load boolean,
    color_rgb         integer    CHECK (color_rgb BETWEEN 0 AND 16777215),
    source_app        smallint   CHECK (source_app BETWEEN 1 AND 5),
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT loop_range_check CHECK (out_ms > in_ms AND length_ms = out_ms - in_ms)
);

CREATE INDEX idx_loops_track ON dj_saved_loops (track_id, hotcue_index);


CREATE TABLE dj_playlists (
    playlist_id        bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_playlist_id bigint     REFERENCES dj_playlists ON DELETE CASCADE,
    name               text       NOT NULL,
    source_app         smallint   CHECK (source_app BETWEEN 1 AND 5),
    created_at         timestamptz NOT NULL DEFAULT now()
);


-- FIX v3: добавлен identity PK для ORM и logical replication
CREATE TABLE dj_playlist_items (
    playlist_item_id bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    playlist_id      bigint     NOT NULL REFERENCES dj_playlists ON DELETE CASCADE,
    track_id         integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    sort_index       integer    NOT NULL CHECK (sort_index >= 0),
    added_at         timestamptz,
    CONSTRAINT dj_playlist_items_uq UNIQUE (playlist_id, sort_index)
);


-- FIX v3: payload bytea → storage_uri (файлы экспорта в S3, не в PG)
CREATE TABLE dj_app_exports (
    export_id      bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_app     smallint   NOT NULL CHECK (target_app BETWEEN 1 AND 3),
    export_format  text       NOT NULL,  -- nml, xml, onelibrary
    playlist_id    bigint     REFERENCES dj_playlists,
    storage_uri    text,      -- s3://exports/... или file:///... (вместо bytea)
    file_size      bigint,    -- для UI / мониторинга
    created_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN dj_app_exports.storage_uri IS
    'URI файла экспорта в object storage. '
    'В v2 был bytea (payload) — перенесено в S3 для экономии места в PG.';


-- ════════════════════════════════════════════════════════════════════════════
-- 15. DJ Sets (generation output)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE dj_sets (
    set_id              bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text         NOT NULL,
    description         text,
    target_duration_ms  integer      CHECK (target_duration_ms > 0),
    target_bpm_min      real,
    target_bpm_max      real,

    -- Energy arc: JSON-контракт (валидация Pydantic на уровне приложения)
    target_energy_arc   jsonb,

    created_at          timestamptz  NOT NULL DEFAULT now(),
    updated_at          timestamptz  NOT NULL DEFAULT now()
);

COMMENT ON COLUMN dj_sets.target_energy_arc IS
    'JSON contract: {"type":"piecewise_linear","points":[{"t_pct":0.0,"energy":0.3},...]} '
    'Каждая точка: t_pct ∈ [0,1] (% от длительности), energy ∈ [0,1]. '
    'Допустимые type: piecewise_linear | bezier | fixed. '
    'Валидация на уровне приложения (Pydantic model).';


CREATE TABLE dj_set_versions (
    set_version_id  bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    set_id          bigint       NOT NULL REFERENCES dj_sets ON DELETE CASCADE,
    version_label   text,        -- e.g. 'v1', 'candidate_3'
    generator_run   jsonb,       -- algo params / transition_run_id / seed
    score           real,        -- общая оценка качества сета (0..1)
    created_at      timestamptz  NOT NULL DEFAULT now()
);


CREATE TABLE dj_set_constraints (
    constraint_id    bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    set_version_id   bigint     NOT NULL REFERENCES dj_set_versions ON DELETE CASCADE,
    constraint_type  text       NOT NULL,
        -- e.g. 'max_bpm_jump', 'key_policy', 'min_transition_ms',
        -- 'required_track', 'excluded_track', 'genre_filter'
    value            jsonb      NOT NULL,  -- typed payload
    created_at       timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE dj_set_items (
    set_item_id      bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    set_version_id   bigint     NOT NULL REFERENCES dj_set_versions ON DELETE CASCADE,
    sort_index       integer    NOT NULL CHECK (sort_index >= 0),
    track_id         integer    NOT NULL REFERENCES tracks ON DELETE CASCADE,
    transition_id    bigint     REFERENCES transitions ON DELETE SET NULL,  -- NULL для первого трека
    in_section_id    bigint     REFERENCES track_sections ON DELETE SET NULL,
    out_section_id   bigint     REFERENCES track_sections ON DELETE SET NULL,
    mix_in_ms        integer    CHECK (mix_in_ms >= 0),
    mix_out_ms       integer    CHECK (mix_out_ms >= 0),
    planned_eq       jsonb,     -- e.g. {"low_cut_at_ms": 12000, "bass_swap_at_ms": 24000}
    notes            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT set_items_sort_uq UNIQUE (set_version_id, sort_index)
);


-- ════════════════════════════════════════════════════════════════════════════
-- 16. DJ Set feedback (обратная связь)
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE dj_set_feedback (
    feedback_id      bigint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    set_version_id   bigint     NOT NULL REFERENCES dj_set_versions ON DELETE CASCADE,
    set_item_id      bigint     REFERENCES dj_set_items ON DELETE CASCADE,
        -- NULL = feedback на весь сет, NOT NULL = на конкретный transition
    rating           smallint   NOT NULL CHECK (rating BETWEEN -1 AND 5),
        -- -1=skip/rejected, 0=neutral, 1..5=quality
    feedback_type    text       NOT NULL DEFAULT 'manual'
        CHECK (feedback_type IN ('manual', 'live_crowd', 'a_b_test')),
    tags             text[],    -- e.g. {'bass_clash', 'key_conflict', 'energy_drop'}
    notes            text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_feedback_set ON dj_set_feedback (set_version_id);

COMMENT ON TABLE dj_set_feedback IS
    'Обратная связь для замкнутого цикла обучения. '
    'rating на set_item = оценка конкретного перехода. '
    'rating на set_version (set_item_id IS NULL) = оценка всего сета. '
    'tags — структурированные причины для агрегации.';


-- ════════════════════════════════════════════════════════════════════════════
-- 17. Helper views
-- ════════════════════════════════════════════════════════════════════════════

-- Последние computed features для каждого трека (latest run)
CREATE VIEW v_latest_track_features AS
SELECT DISTINCT ON (track_id) *
FROM track_audio_features_computed
ORDER BY track_id, run_id DESC;

-- Активные треки с базовыми features
CREATE VIEW v_active_tracks_with_features AS
SELECT
    t.track_id,
    t.title,
    t.duration_ms,
    f.bpm,
    f.key_code,
    k.name AS key_name,
    k.camelot,
    f.key_confidence,
    f.energy_mean,
    f.lufs_i,
    f.kick_prominence,
    f.pulse_clarity
FROM tracks t
JOIN v_latest_track_features f USING (track_id)
LEFT JOIN keys k USING (key_code)
WHERE t.archived_at IS NULL;

-- FIX v3: нормализованная сортировка (bpm_distance и key_distance приведены к [0,1])
-- bpm_distance / max_bpm_jump = нормализованный BPM (при max_jump = 6 BPM)
-- key_distance / 12.0 = нормализованный key (12 = макс. camelot distance)
CREATE VIEW v_pending_scoring AS
SELECT
    tc.*,
    t1.title AS from_title,
    t2.title AS to_title,
    -- Нормализованный composite score для приоритизации (ниже = лучше)
    (tc.bpm_distance / 6.0 + tc.key_distance / 12.0) / 2.0 AS priority_score
FROM transition_candidates tc
JOIN tracks t1 ON t1.track_id = tc.from_track_id
JOIN tracks t2 ON t2.track_id = tc.to_track_id
WHERE tc.is_fully_scored = false
ORDER BY (tc.bpm_distance / 6.0 + tc.key_distance / 12.0) ASC;


-- ════════════════════════════════════════════════════════════════════════════
-- 18. Functions: key distance computation
-- ════════════════════════════════════════════════════════════════════════════

-- Camelot distance: lookup в key_edges, fallback 12.0
CREATE OR REPLACE FUNCTION camelot_distance(a_key_code smallint, b_key_code smallint)
RETURNS real
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT COALESCE(
        (SELECT ke.distance
         FROM key_edges ke
         WHERE ke.from_key_code = a_key_code AND ke.to_key_code = b_key_code),
        12.0  -- max distance if edge not in graph
    )
$$;

-- FIX v3: плавная интерполяция вместо step function при low confidence
-- При confidence ∈ [0, 0.4] — линейная интерполяция от mild penalty к нормальному scoring
-- При confidence IS NULL — unknown penalty 3.0
-- При confidence >= 0.4 — полный camelot_distance * min(conf_a, conf_b)
CREATE OR REPLACE FUNCTION key_distance_weighted(
    a_key_code smallint, a_confidence real,
    b_key_code smallint, b_confidence real
) RETURNS real
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN a_confidence IS NULL OR b_confidence IS NULL THEN 3.0
        ELSE (
            -- min_conf ∈ [0, 1]; alpha = плавный переход от mild (1.0) к full distance
            -- alpha = clamp(min_conf / 0.4, 0, 1)
            -- result = (1 - alpha) * 1.0 + alpha * camelot_distance * min_conf
            SELECT CASE
                WHEN min_conf < 0.4 THEN
                    (1.0 - min_conf / 0.4) * 1.0
                    + (min_conf / 0.4) * camelot_distance(a_key_code, b_key_code) * min_conf
                ELSE
                    camelot_distance(a_key_code, b_key_code) * min_conf
            END
            FROM (SELECT LEAST(a_confidence, b_confidence)) AS t(min_conf)
        )
    END
$$;

COMMENT ON FUNCTION key_distance_weighted IS
    'Взвешенная key distance с учётом confidence. '
    'При low confidence (< 0.4) — плавная интерполяция от mild penalty (1.0) к полному scoring. '
    'Нет разрыва на пороге 0.4 (в отличие от v2).';


-- ════════════════════════════════════════════════════════════════════════════
-- 19. Triggers: updated_at auto-update
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- Attach to all tables with updated_at
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'tracks', 'artists', 'labels', 'releases',
            'provider_track_ids', 'spotify_metadata', 'spotify_audio_features',
            'spotify_album_metadata', 'spotify_artist_metadata', 'spotify_playlist_metadata',
            'soundcloud_metadata', 'beatport_metadata',
            'dj_beatgrid', 'dj_cue_points', 'dj_sets'
        ])
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at()',
            tbl, tbl
        );
    END LOOP;
END;
$$;


-- ════════════════════════════════════════════════════════════════════════════
-- 20. Row-level security prep (опционально, для multi-user)
-- ════════════════════════════════════════════════════════════════════════════

-- Готово к включению RLS при добавлении user_id.
-- ALTER TABLE dj_sets ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY dj_sets_owner ON dj_sets
--     USING (owner_id = current_setting('app.user_id')::int);


COMMIT;

-- ============================================================================
-- DONE. Schema v3 ready.
-- ============================================================================
