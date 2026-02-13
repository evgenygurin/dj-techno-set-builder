# API Design (v1)

Все endpoint-ы под префиксом `/api/v1`. Формат ответов — JSON. Пагинация везде через `offset`/`limit`. Списочные ответы обёрнуты в `{ items: [...], total: int }`.

Коды ошибок: `{ code: str, message: str, details?: object }`.

---

## 1. Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Статус приложения |

**Response** `200`:
```json
{ "status": "ok" }
```

---

## 2. Tracks (реализовано)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks` | Список треков с поиском |
| GET | `/api/v1/tracks/{track_id}` | Получить трек |
| POST | `/api/v1/tracks` | Создать трек |
| PATCH | `/api/v1/tracks/{track_id}` | Обновить трек |
| DELETE | `/api/v1/tracks/{track_id}` | Удалить трек (soft delete) |
| POST | `/api/v1/tracks/{track_id}/archive` | Архивировать трек |
| POST | `/api/v1/tracks/{track_id}/unarchive` | Разархивировать трек |

**Query params** (GET list): `offset`, `limit`, `search`, `status` (0/1), `archived` (bool).

**TrackCreate**:
```json
{ "title": "Acid Rain", "title_sort": "acid rain", "duration_ms": 420000 }
```

**TrackRead**:
```json
{
  "track_id": 1,
  "title": "Acid Rain",
  "title_sort": "acid rain",
  "duration_ms": 420000,
  "status": 0,
  "archived_at": null,
  "created_at": "2026-02-12T10:00:00Z",
  "updated_at": "2026-02-12T10:00:00Z"
}
```

---

## 3. Artists

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/artists` | Список артистов |
| GET | `/api/v1/artists/{artist_id}` | Получить артиста |
| POST | `/api/v1/artists` | Создать артиста |
| PATCH | `/api/v1/artists/{artist_id}` | Обновить артиста |
| DELETE | `/api/v1/artists/{artist_id}` | Удалить артиста |
| GET | `/api/v1/artists/{artist_id}/tracks` | Треки артиста |

**ArtistCreate**: `{ "name": "Amelie Lens", "name_sort": "lens amelie" }`

**ArtistRead**: `{ "artist_id", "name", "name_sort", "created_at", "updated_at" }`

---

## 4. Track-Artist Links

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/artists` | Артисты трека с ролями |
| PUT | `/api/v1/tracks/{track_id}/artists` | Заменить список артистов трека |
| POST | `/api/v1/tracks/{track_id}/artists` | Добавить артиста к треку |
| DELETE | `/api/v1/tracks/{track_id}/artists/{artist_id}/{role}` | Убрать связь |

**TrackArtistCreate**: `{ "artist_id": 1, "role": 0 }` — role: 0=primary, 1=featured, 2=remixer.

**TrackArtistRead**: `{ "artist_id", "name", "role" }`

---

## 5. Labels

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/labels` | Список лейблов |
| GET | `/api/v1/labels/{label_id}` | Получить лейбл |
| POST | `/api/v1/labels` | Создать лейбл |
| PATCH | `/api/v1/labels/{label_id}` | Обновить лейбл |
| DELETE | `/api/v1/labels/{label_id}` | Удалить лейбл |

**LabelCreate**: `{ "name": "Drumcode", "name_sort": "drumcode" }`

---

## 6. Releases

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/releases` | Список релизов |
| GET | `/api/v1/releases/{release_id}` | Получить релиз с треками |
| POST | `/api/v1/releases` | Создать релиз |
| PATCH | `/api/v1/releases/{release_id}` | Обновить релиз |
| POST | `/api/v1/tracks/{track_id}/releases` | Привязать трек к релизу |

**ReleaseCreate**:
```json
{ "title": "DC-300", "label_id": 1, "release_date": "2026-01-15", "release_date_precision": "day" }
```

**ReleaseRead**: `{ "release_id", "title", "label": { "label_id", "name" }, "release_date", "release_date_precision", "tracks": [...] }`

---

## 7. Genres

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/genres` | Дерево жанров |
| GET | `/api/v1/genres/{genre_id}` | Жанр с подсчётом треков |
| POST | `/api/v1/genres` | Создать жанр |
| POST | `/api/v1/tracks/{track_id}/genres` | Привязать жанр к треку |
| DELETE | `/api/v1/tracks/{track_id}/genres/{genre_id}` | Убрать жанр |

**GenreCreate**: `{ "name": "Hard Techno", "parent_genre_id": 1 }`

**GenreTree**: `{ "genre_id", "name", "children": [...], "track_count" }`

---

## 8. Providers

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/providers` | Список провайдеров |

Read-only справочник. Seed-данные: Spotify (1), SoundCloud (2), Beatport (3).

**ProviderRead**: `{ "provider_id": 1, "provider_code": "spotify", "name": "Spotify" }`

---

## 9. Ingestion

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ingest/spotify` | Импорт трека из Spotify по ID/URL |
| POST | `/api/v1/ingest/soundcloud` | Импорт трека из SoundCloud по URL |
| POST | `/api/v1/ingest/beatport` | Импорт трека из Beatport по ID/URL |
| POST | `/api/v1/ingest/batch` | Пакетный импорт (playlist/selection) |
| GET | `/api/v1/tracks/{track_id}/provider-ids` | Внешние ID трека |

**IngestRequest**:
```json
{ "url": "https://open.spotify.com/track/...", "provider_track_id": "4iV5W9uYEdYUVa79Axb7Rh" }
```

**IngestResponse**:
```json
{
  "track_id": 42,
  "provider": "spotify",
  "provider_track_id": "4iV5W9uYEdYUVa79Axb7Rh",
  "status": "created",
  "metadata_fetched": true
}
```

**BatchIngestRequest**:
```json
{ "provider": "spotify", "playlist_url": "https://open.spotify.com/playlist/..." }
```

**BatchIngestResponse**:
```json
{ "total": 25, "created": 20, "existing": 5, "failed": 0, "tracks": [...] }
```

---

## 10. Provider Metadata

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/metadata` | Все метаданные трека (все провайдеры) |
| GET | `/api/v1/tracks/{track_id}/metadata/spotify` | Spotify-метаданные трека |
| GET | `/api/v1/tracks/{track_id}/metadata/soundcloud` | SoundCloud-метаданные |
| GET | `/api/v1/tracks/{track_id}/metadata/beatport` | Beatport-метаданные |
| POST | `/api/v1/tracks/{track_id}/metadata/{provider}/refresh` | Обновить метаданные из API провайдера |

**TrackMetadataRead** (агрегированный):
```json
{
  "track_id": 42,
  "spotify": { "spotify_track_id": "...", "popularity": 65, "explicit": false, "preview_url": "..." },
  "soundcloud": { "soundcloud_track_id": "...", "playback_count": 12500, "bpm": 140 },
  "beatport": { "beatport_track_id": "...", "bpm": 140.0, "key_code": 4, "genre_name": "Techno (Peak Time / Driving)" }
}
```

---

## 11. Audio Assets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/assets` | Список аудио-файлов трека |
| POST | `/api/v1/tracks/{track_id}/assets` | Зарегистрировать аудио-файл |
| DELETE | `/api/v1/assets/{asset_id}` | Удалить аудио-файл |

**AssetCreate**:
```json
{
  "asset_type": 0,
  "storage_uri": "s3://bucket/tracks/42/full_mix.flac",
  "format": "flac",
  "sample_rate": 44100,
  "channels": 2,
  "duration_ms": 420000,
  "file_size": 52428800
}
```

asset_type: 0=full_mix, 1=drums_stem, 2=bass_stem, 3=vocals_stem, 4=other_stem, 5=preview_clip.

---

## 12. Pipeline Runs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/runs/features` | Список feature extraction runs |
| GET | `/api/v1/runs/features/{run_id}` | Детали run с прогрессом |
| POST | `/api/v1/runs/features` | Запустить feature extraction |
| POST | `/api/v1/runs/features/{run_id}/cancel` | Отменить run |
| GET | `/api/v1/runs/transitions` | Список transition runs |
| POST | `/api/v1/runs/transitions` | Запустить transition scoring |

**FeatureRunCreate**:
```json
{
  "pipeline_name": "audio_features_v1",
  "pipeline_version": "1.2.0",
  "parameters": { "hop_length": 512, "n_fft": 2048 },
  "track_ids": [1, 2, 3]
}
```

**RunRead**:
```json
{
  "run_id": 1,
  "pipeline_name": "audio_features_v1",
  "pipeline_version": "1.2.0",
  "parameters": { "hop_length": 512, "n_fft": 2048, "full_analysis": true },
  "code_ref": "audio_features_v1@1.2.0",
  "status": "running",
  "started_at": "2026-02-12T10:00:00Z",
  "completed_at": null
}
```

---

## 13. Harmony (Keys)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/keys` | Все 24 ключа |
| GET | `/api/v1/keys/{key_code}` | Ключ с совместимыми ключами |
| GET | `/api/v1/keys/{key_code}/compatible` | Совместимые ключи, отсортированные по distance |

**KeyRead**: `{ "key_code": 0, "pitch_class": 0, "mode": 0, "name": "Cm", "camelot": "5A" }`

**KeyCompatible**:
```json
{
  "from_key": { "key_code": 0, "name": "Cm", "camelot": "5A" },
  "edges": [
    { "to_key": { "key_code": 1, "name": "C", "camelot": "8B" }, "distance": 1.0, "weight": 0.8, "rule": "relative_major_minor" },
    { "to_key": { "key_code": 14, "name": "Gm", "camelot": "6A" }, "distance": 1.0, "weight": 0.9, "rule": "camelot_adjacent" }
  ]
}
```

---

## 14. Audio Features

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/features` | Последние computed features трека |
| GET | `/api/v1/tracks/{track_id}/features/history` | Все runs для трека |
| GET | `/api/v1/features/search` | Поиск треков по фичам |

**Query params** (search): `bpm_min`, `bpm_max`, `key_code`, `energy_min`, `energy_max`, `sort_by` (bpm/energy/key_confidence).

**FeaturesRead** (сокращённо):
```json
{
  "track_id": 42,
  "run_id": 1,
  "bpm": 140.2,
  "tempo_confidence": 0.95,
  "bpm_stability": 0.98,
  "key_code": 4,
  "key_name": "Dm",
  "key_confidence": 0.87,
  "energy_mean": 0.72,
  "energy_max": 0.91,
  "lufs_i": -8.5,
  "kick_prominence": 0.85,
  "pulse_clarity": 0.92,
  "sub_energy": 0.65,
  "low_energy": 0.58,
  "mid_energy": 0.45,
  "high_energy": 0.32,
  "created_at": "2026-02-12T10:00:00Z"
}
```

---

## 15. Sections

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/sections` | Структурная сегментация трека |

**SectionRead**:
```json
{
  "section_id": 1,
  "section_type": 0,
  "section_type_name": "intro",
  "start_ms": 0,
  "end_ms": 32000,
  "section_duration_ms": 32000,
  "section_energy_mean": 0.35,
  "section_energy_max": 0.52,
  "boundary_confidence": 0.91
}
```

---

## 16. Transitions

### Candidates (Stage 1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/candidates` | Кандидаты на переход от трека |
| GET | `/api/v1/candidates/pending` | Ещё не прошедшие full scoring |

**Query params**: `sort_by` (bpm_distance/key_distance/embedding_similarity), `limit`.

**CandidateRead**:
```json
{
  "from_track_id": 1,
  "to_track_id": 42,
  "to_track_title": "Acid Rain",
  "bpm_distance": 2.1,
  "key_distance": 1.0,
  "embedding_similarity": 0.87,
  "energy_delta": 0.15,
  "is_fully_scored": false
}
```

### Transitions (Stage 2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/transitions` | Лучшие переходы от трека |
| GET | `/api/v1/transitions/{transition_id}` | Детальная информация о переходе |
| GET | `/api/v1/transitions/search` | Поиск переходов по качеству |

**Query params** (list): `direction` (from/to/both), `min_quality`, `limit`, `sort_by` (quality/bpm_distance).

**TransitionRead**:
```json
{
  "transition_id": 1,
  "from_track": { "track_id": 1, "title": "Drumcode 300", "bpm": 138.0, "key_name": "Cm" },
  "to_track": { "track_id": 42, "title": "Acid Rain", "bpm": 140.0, "key_name": "Dm" },
  "transition_quality": 0.87,
  "overlap_ms": 16000,
  "bpm_distance": 2.0,
  "energy_step": 0.15,
  "key_distance_weighted": 1.2,
  "groove_similarity": 0.78,
  "low_conflict_score": 0.12,
  "from_section": { "section_id": 5, "section_type_name": "outro" },
  "to_section": { "section_id": 12, "section_type_name": "intro" }
}
```

---

## 17. Embeddings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/embedding-types` | Зарегистрированные типы |
| GET | `/api/v1/tracks/{track_id}/embeddings` | Эмбеддинги трека |
| GET | `/api/v1/tracks/{track_id}/similar` | Похожие треки по эмбеддингам |

**Query params** (similar): `embedding_type` (groove/timbre/genre), `limit`, `min_similarity`.

**SimilarTrackRead**:
```json
{
  "track_id": 42,
  "title": "Acid Rain",
  "bpm": 140.0,
  "key_name": "Dm",
  "similarity": 0.93,
  "embedding_type": "groove"
}
```

---

## 18. DJ Layer

### Library

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/library-items` | Файлы трека из DJ-библиотек |
| POST | `/api/v1/tracks/{track_id}/library-items` | Добавить файл в библиотеку |

### Beatgrid

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/beatgrid` | Бит-гриды трека (все источники) |
| POST | `/api/v1/tracks/{track_id}/beatgrid` | Создать/импортировать грид |
| PATCH | `/api/v1/beatgrids/{beatgrid_id}` | Обновить грид |
| POST | `/api/v1/beatgrids/{beatgrid_id}/set-canonical` | Сделать каноническим |

**BeatgridRead**:
```json
{
  "beatgrid_id": 1,
  "bpm": 140.0,
  "first_downbeat_ms": 250,
  "source_app": 1,
  "source_app_name": "traktor",
  "is_canonical": true,
  "is_variable_tempo": false,
  "change_points": [
    { "position_ms": 120000, "bpm": 141.0 }
  ]
}
```

### Cue Points

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/cues` | Cue-точки трека |
| POST | `/api/v1/tracks/{track_id}/cues` | Создать cue |
| PATCH | `/api/v1/cues/{cue_id}` | Обновить cue |
| DELETE | `/api/v1/cues/{cue_id}` | Удалить cue |

**CuePointCreate**:
```json
{
  "position_ms": 32000,
  "cue_kind": 0,
  "hotcue_index": 1,
  "label": "Drop",
  "color_rgb": 16711680,
  "source_app": 1
}
```

cue_kind: 0=cue, 1=load, 2=grid, 3=fade_in, 4=fade_out, 5=loop_in, 6=loop_out, 7=memory.

### Saved Loops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tracks/{track_id}/loops` | Сохранённые лупы |
| POST | `/api/v1/tracks/{track_id}/loops` | Создать луп |
| DELETE | `/api/v1/loops/{loop_id}` | Удалить луп |

**SavedLoopCreate**:
```json
{ "in_ms": 64000, "out_ms": 96000, "hotcue_index": 4, "label": "Breakdown loop" }
```

`length_ms` вычисляется автоматически: `out_ms - in_ms`.

### Playlists

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/playlists` | Дерево плейлистов |
| GET | `/api/v1/playlists/{playlist_id}` | Плейлист с треками |
| POST | `/api/v1/playlists` | Создать плейлист/папку |
| PATCH | `/api/v1/playlists/{playlist_id}` | Переименовать / переместить |
| DELETE | `/api/v1/playlists/{playlist_id}` | Удалить плейлист |
| PUT | `/api/v1/playlists/{playlist_id}/items` | Заменить порядок треков |
| POST | `/api/v1/playlists/{playlist_id}/items` | Добавить трек |

**PlaylistCreate**: `{ "name": "Peak Time", "parent_playlist_id": null, "source_app": 1 }`

### Exports

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/exports` | Экспорт плейлиста/сета для DJ-приложения |
| GET | `/api/v1/exports/{export_id}` | Статус/ссылка на экспорт |
| GET | `/api/v1/exports` | Список экспортов |

**ExportCreate**:
```json
{ "target_app": 1, "export_format": "nml", "playlist_id": 5 }
```

target_app: 1=traktor, 2=rekordbox, 3=djay. Формат: nml (Traktor), xml (Rekordbox), onelibrary (djay).

**ExportRead**:
```json
{ "export_id": 1, "target_app": 1, "export_format": "nml", "storage_uri": "s3://exports/...", "file_size": 25600, "created_at": "..." }
```

---

## 19. DJ Sets

### Sets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/sets` | Список сетов |
| GET | `/api/v1/sets/{set_id}` | Сет с последней версией |
| POST | `/api/v1/sets` | Создать сет |
| PATCH | `/api/v1/sets/{set_id}` | Обновить параметры |
| DELETE | `/api/v1/sets/{set_id}` | Удалить сет |

**SetCreate**:
```json
{
  "name": "Friday Night Techno",
  "description": "2h peak-time set",
  "target_duration_ms": 7200000,
  "target_bpm_min": 136.0,
  "target_bpm_max": 145.0,
  "target_energy_arc": {
    "type": "piecewise_linear",
    "points": [
      { "t_pct": 0.0, "energy": 0.3 },
      { "t_pct": 0.3, "energy": 0.7 },
      { "t_pct": 0.7, "energy": 1.0 },
      { "t_pct": 1.0, "energy": 0.5 }
    ]
  }
}
```

### Versions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/sets/{set_id}/versions` | Все версии сета |
| GET | `/api/v1/sets/{set_id}/versions/{version_id}` | Версия с полным tracklist |
| POST | `/api/v1/sets/{set_id}/generate` | Сгенерировать новую версию |
| DELETE | `/api/v1/sets/{set_id}/versions/{version_id}` | Удалить версию |

**GenerateRequest**:
```json
{
  "constraints": [
    { "constraint_type": "max_bpm_jump", "value": { "max": 6 } },
    { "constraint_type": "key_policy", "value": { "mode": "camelot_compatible" } },
    { "constraint_type": "required_track", "value": { "track_id": 42, "position": "opener" } },
    { "constraint_type": "excluded_track", "value": { "track_id": 99 } }
  ]
}
```

**VersionRead**:
```json
{
  "set_version_id": 1,
  "set_id": 1,
  "version_label": "v1",
  "score": 0.87,
  "created_at": "2026-02-12T10:00:00Z",
  "items": [
    {
      "set_item_id": 1,
      "sort_index": 0,
      "track": { "track_id": 1, "title": "Opening", "bpm": 136.0, "key_name": "Am" },
      "transition": null,
      "mix_in_ms": null,
      "mix_out_ms": null,
      "notes": null
    },
    {
      "set_item_id": 2,
      "sort_index": 1,
      "track": { "track_id": 42, "title": "Acid Rain", "bpm": 140.0, "key_name": "Dm" },
      "transition": { "transition_id": 5, "transition_quality": 0.91, "overlap_ms": 16000 },
      "mix_in_ms": 16000,
      "mix_out_ms": 384000,
      "planned_eq": { "bass_swap_at_ms": 8000 },
      "notes": "Swap bass at breakdown"
    }
  ],
  "constraints": [
    { "constraint_type": "max_bpm_jump", "value": { "max": 6 } }
  ]
}
```

### Set Items (ручное редактирование)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/api/v1/sets/{set_id}/versions/{version_id}/items` | Заменить весь tracklist |
| POST | `/api/v1/sets/{set_id}/versions/{version_id}/items` | Добавить трек в позицию |
| PATCH | `/api/v1/set-items/{item_id}` | Обновить mix points / notes |
| DELETE | `/api/v1/set-items/{item_id}` | Убрать трек из сета |
| POST | `/api/v1/sets/{set_id}/versions/{version_id}/reorder` | Изменить порядок |

### Feedback

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/sets/{set_id}/versions/{version_id}/feedback` | Отзывы на версию |
| POST | `/api/v1/sets/{set_id}/versions/{version_id}/feedback` | Оставить отзыв |

**FeedbackCreate**:
```json
{
  "set_item_id": 2,
  "rating": 4,
  "feedback_type": "manual",
  "notes": "Smooth bass swap, energy flow is great"
}
```

`set_item_id: null` — отзыв на весь сет. Rating: -1=skip/rejected, 0=neutral, 1-5=quality.

feedback_type: `manual`, `live_crowd`, `a_b_test`.

---

## Общие паттерны

### Пагинация

```text
GET /api/v1/tracks?offset=0&limit=50
```

Ответ:
```json
{ "items": [...], "total": 142 }
```

### Ошибки

| Status | Code | Когда |
|--------|------|-------|
| 404 | NOT_FOUND | Ресурс не найден |
| 409 | CONFLICT | Дубликат (unique constraint) |
| 422 | VALIDATION_ERROR | Невалидные данные |
| 500 | INTERNAL_ERROR | Неожиданная ошибка |

```json
{ "code": "NOT_FOUND", "message": "Track not found", "details": { "track_id": 999 } }
```

### Заголовки

| Header | Description |
|--------|-------------|
| X-Request-ID | UUID запроса (генерируется или передаётся клиентом) |
