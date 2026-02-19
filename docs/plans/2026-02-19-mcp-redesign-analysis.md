# MCP Redesign — Анализ документов и целевая структура

**Дата**: 2026-02-19
**Статус**: Анализ
**Входные документы**: 11 файлов (1 design doc, 5 implementation plans, 5 critical reviews)

Этот документ — результат глубокого анализа предложенного 5-фазного редизайна MCP-инструментов. Он не повторяет содержание планов, а фиксирует **что работает, что сломано, и как должна выглядеть целевая структура**.

---

## 1. Текущее состояние MCP-слоя

### 1.1 Архитектура

```text
Gateway (FastMCP "DJ Set Builder")
├── YM namespace (ym) — ~30 tools via from_openapi()
│   ├── server.py (188 строк) — OpenAPI → MCP, httpx hooks
│   ├── config.py (47 строк) — route filtering + naming
│   └── response_filters.py (300 строк) — чистка ответов YM
│
├── DJ Workflows namespace (dj) — 19 hand-written tools
│   ├── server.py (51 строк) — register 7 modules + visibility
│   ├── analysis_tools.py (132 строки) — 2 read-only tools
│   ├── import_tools.py (147 строк) — 2 стаба + download
│   ├── discovery_tools.py (265 строк) — 2 tools (search, similar)
│   ├── setbuilder_tools.py (432 строки) — 4 tools (build, rebuild, score, export-дубликат)
│   ├── export_tools.py (703 строки) — 3 экспорта (M3U, JSON, Rekordbox)
│   ├── curation_tools.py (222 строки) — 3 аналитики (classify, gaps, review)
│   └── sync_tools.py (186 строк) — 3 стаба
│
├── dependencies.py (125 строк) — 8 service factories + session
├── types.py (133 строки) — 13 моделей (5 dead code)
├── types_curation.py (81 строка) — 8 моделей (2 dead code)
├── gateway.py (88 строк) — compose & mount
├── observability.py (113 строк) — 6 middleware
├── lifespan.py (31 строка) — startup/shutdown
├── prompts/ — 3 workflow-рецепта
├── resources/ — 3 MCP-ресурса
└── skills/ — 3 Claude Code skills
```

**Итого**: ~3,200 строк Python, ~49 инструментов (19 DJ + ~30 YM), 5 стабов, 5 мёртвых типов, 1 дубликат.

### 1.2 Проблемы текущей архитектуры

| Проблема | Пример | Влияние |
|----------|--------|---------|
| Workflow-ориентация, а не entity-ориентация | `get_playlist_status` возвращает BPM/keys/energy, но нет `list_playlists` | Агент не может просмотреть список плейлистов |
| 5 стабов занимают tool-слоты | `import_playlist`, `import_tracks`, 3× sync | Агент видит инструменты, которые ничего не делают |
| Дубликат `export_set_m3u` | В `setbuilder_tools.py` (простой) и `export_tools.py` (полный) | Агент не знает, какой вызвать |
| Нет пагинации | `list_features` загружает все записи | Overflow контекста при больших библиотеках |
| Нет универсального поиска | `search_by_criteria` (только BPM/key/energy) | Агент не может искать по артисту/названию |
| Жёсткая привязка к YM | `DjSet.ym_playlist_id: int` | Невозможно добавить Spotify |
| 5 мёртвых типов | SwapSuggestion, ReorderSuggestion, AdjustmentPlan, CurateCandidate, CurateSetResult | Засоряют imports |

---

## 2. Обзор предложенного редизайна (5 фаз)

### 2.1 Что предлагают планы

| Фаза | Цель | Новые файлы | Новые инструменты |
|------|------|-------------|-------------------|
| **Phase 1** | Foundation: URN refs, response models, pagination, search | types_v2.py, refs.py, entity_finder.py, pagination.py, library_stats.py, search_tools.py | search, filter_tracks |
| **Phase 2** | CRUD + compute/persist split + unified export | response.py, converters.py, CRUD tools (tracks, playlists, sets, features) | ~20 CRUD + analyze_track + export_set |
| **Phase 3** | Multi-platform abstraction + SyncEngine | platforms/, sync/, yandex_music/adapter.py | sync_playlist, list_platforms, activate_ym_raw |
| **Phase 4** | Cleanup: delete stubs, types, duplicates | DELETE: analysis_tools, types, types_curation | Удаление 5+ инструментов |
| **Phase 5** | FastMCP platform features: OTEL, timeouts, elicitation | Modify: observability.py, lifespan.py, tool decorators | Нет новых (hardening) |

### 2.2 Три правила генерации инструментов (дизайн)

1. **Entity → CRUD**: Track, Playlist, Set, AudioFeatures → list/get/create/update/delete
2. **Compute → Tool**: Каждая audio-функция → отдельный инструмент
3. **External API → Tool**: 1:1 mapping endpoint → tool (уже работает для YM)

### 2.3 Cross-cutting capabilities (дизайн)

- **URN Entity References**: `local:42`, `ym:12345`, `"Boris Brejcha"` → resolver
- **Response Envelope**: summary/detail/full + stats + pagination
- **Universal Search**: один `search()` fan-out по всем источникам
- **Visibility Control**: tags + `activate_*()` для show/hide tool groups
- **SyncEngine**: bidirectional per-playlist sync

---

## 3. Глубокий архитектурный анализ

### 3.1 Rule 1: Entity → CRUD — оценка реализуемости

**Текущее CRUD-покрытие по модулям:**

| Модуль | Инструменты | Реальное покрытие |
|--------|------------|-------------------|
| `analysis_tools.py` | `get_playlist_status`, `get_track_details` | Read only, нет List/Create/Update/Delete |
| `import_tools.py` | 2 стаба + `download_tracks` | Нет CRUD — это action |
| `discovery_tools.py` | `find_similar_tracks`, `search_by_criteria` | Read-like фильтрация |
| `setbuilder_tools.py` | `build_set`, `rebuild_set`, `score_transitions`, `export_set_m3u` | Create (build) + Read (score) + дубликат export |
| `export_tools.py` | 3 экспорта (M3U, JSON, Rekordbox) | Read only (генерация формата) |
| `curation_tools.py` | `classify_tracks`, `analyze_library_gaps`, `review_set` | Read only (аналитика) |
| `sync_tools.py` | 3 стаба | Ничего не работает |

**Целевое количество**: 5×Track + 5×Playlist + 4×Set + 3×Features = 17 CRUD + 11 оркестраторов + 3 sync = 31 DJ tool. Текущих — 19 (включая 5 стабов). CRUD-подход **удвоит** количество DJ-инструментов.

**Риск**: все 5 ревью указывают на одну и ту же ошибку tool output contract (планы возвращают `str`/JSON, а кодовая база — Pydantic models). ~60% code snippets в планах нужно переписать.

### 3.2 Rule 2: Compute → Tool — блокер audio namespace

12 аудио-инструментов 1:1 с `app/utils/audio/`. Разумный подход.

**Критический блокер**: аудио-инструменты принимают `track_ref | audio_path`. Но `Track` модель **не хранит путь к файлу**. Есть `AudioAsset` модель, но нет `AudioAssetRepository`. Без `resolve_audio_path(track_ref)` весь audio-namespace нерабочий. **Ни один из 5 планов не добавляет этот resolver.**

### 3.3 EntityFinder / URN-система

**Принцип**: все `*_id: int` → `*_ref: str` (формат: `local:42`, `ym:12345`, `"Boris Brejcha"`).

**Совместимость с моделями БД:**

| Модель | ID поле | Тип | URN-совместимость |
|--------|---------|-----|-------------------|
| `Track` | `track_id` | `int` PK | `local:42` ✓ |
| `DjPlaylist` | `playlist_id` | `int` PK | `local:5` ✓ |
| `DjSet` | `set_id` | `int` PK | `local:3` ✓ |
| `Artist` | `artist_id` | `int` PK | `local:10` ✓ |
| `ProviderTrackId` | composite | `track_id + provider_id + provider_track_id` | `ym:12345` → нужен JOIN через Provider |
| `DjSet` | `ym_playlist_id` | `int` | Это kind YM плейлиста, не `ym:` URN |

**Проблема platform key (из Phase 3 review)**:

Три разных идентификатора одной платформы:
- `Provider.provider_code = "yandex_music"` (в БД, seed в `app/database.py`)
- `YandexMusicAdapter.name = "ym"` (в протоколе)
- `DownloadService` ищет `provider_code == "yandex"` (третий вариант)

Последствия: `DbTrackMapper` делает `WHERE provider_code = platform.name`. Если `platform.name = "ym"`, а в БД `"yandex_music"` — маппинг всегда пустой. SyncEngine на пустом маппинге в `LOCAL_TO_REMOTE` **удалит все треки с платформы**.

**Решение**: необходим `PlatformKey` enum — отображение `ym → yandex_music`. Отсутствует во всех 5 планах.

### 3.4 Response Envelope

Три уровня (Summary ~150B, Detail ~300B, Full ~2KB) + stats + pagination.

**Что хорошо:**
- `LibraryStats` — полезен агенту (4 COUNT запроса)
- `PaginationInfo` (cursor, has_more) — необходим для `list_*`
- Summary/Detail уровни — экономят токены

**Проблемы из ревью:**
- `total_matches` считается как `len(entities)` вместо реального total (Phase 1 review)
- Один cursor для multi-category search не работает при `scope="all"` (Phase 1 review)
- `level` параметр описан, но нигде не реализован (Phase 1 review)
- 4 COUNT запроса на каждый вызов — overhead для read-only tools

**Решение**: `level: Literal["summary", "detail"] = "summary"` в каждом list/search. `scope="all"` ограничить одной категорией в Phase 1.

### 3.5 Multi-Platform / SyncEngine — критический анализ

Самая амбициозная и наименее проработанная часть.

**Текущая инфраструктура:**
- `app/models/providers.py` — 4 провайдера seeded: spotify, soundcloud, beatport, yandex_music
- `app/models/ingestion.py` — `ProviderTrackId` (local ↔ platform mapping)
- `app/services/yandex_music_client.py` — единственный реальный клиент
- `DjSet.ym_playlist_id` — hardcoded YM reference

**5 нерешённых блокеров из Phase 3 review:**

1. **Platform key mismatch** (`ym` / `yandex_music` / `yandex`) — нет единого mapping
2. **Track ID формат** — тесты используют и `"12345"` и `"ym_12345"` — нет нормализации
3. **Playlist ID формат** — YM playlist = (userId, kind), `DjSet.ym_playlist_id` хранит только kind
4. **Adapter без write-операций** — план бросает `NotImplementedError` для create/add/remove, но SyncEngine **требует** writes
5. **Удаление при неполном маппинге** — 80% mapping coverage → SyncEngine удалит 20% "лишних" треков

**Оценка**: Phase 3 как написана — **не deliverable**. Нужна промежуточная работа: resolve platform keys + adapter writes + safe sync defaults.

### 3.6 Phase 5 (Platform Features) — приоритизация

Phase 5 **независима** и может выполняться параллельно.

| Feature | Ценность | Реализуемость | Приоритет |
|---------|----------|---------------|-----------|
| OTEL exporter | Высокая | ✓ Просто (1 lifespan hook) | P1 |
| Tool timeouts | Высокая | ✓ Просто (декоратор) | P1 |
| Tool versioning | Средняя | ✓ Просто (`version="1.0.0"`) | P2 |
| Background tasks | Высокая | ⚠️ `task=True` требует docket (review) | P2 |
| Elicitation | Средняя | ⚠️ Только clients с поддержкой | P3 |
| Session state | Низкая | ⚠️ Конфликт с visibility tags | P3 |
| ResponseLimiting | Средняя | ⚠️ Ломает structured_content (review) | P3 |
| ResponseCaching | Низкая | ✗ Не решена invalidation | P4 |

### 3.7 Сквозные проблемы всех 5 фаз

**Проблема 1: Tool Contract (критическая, 5/5 планов)**

Каждый план возвращает `str` (JSON), тесты парсят `result[0].text`. Кодовая база возвращает Pydantic models, FastMCP обрабатывает как structured output, тесты проверяют `result.data`. Это системная ошибка генерации: ~200 test snippets нужно переписать.

**Проблема 2: MCP тесты не подключены к test DB**

`dependencies.py:get_session()` создаёт сессию из `app.database.session_factory` (production). Тесты пишут в in-memory SQLite. MCP tools в тестах читают из production session_factory. Ни один план не решает.

**Проблема 3: AudioFeatures дубликаты по run_id**

`track_audio_features_computed` PK = `(track_id, run_id)`. Наивный `list_features()` вернёт N строк на трек. `AudioFeaturesRepository.list_all()` уже фильтрует "latest per track", но `filter_tracks` из плана идёт мимо.

**Проблема 4: Compute-only analyze_track неосуществим**

Phase 2 разделяет: `analyze_track` → JSON, `save_features` → persist. Но `TrackFeatures` — frozen dataclass с numpy arrays. JSON serialization/deserialization невозможна. `FeatureRunRepository` требует `pipeline_name`, `pipeline_version`.

---

## 4. Целевая структура

### 4.1 Правила нейминга

| Правило | Пример |
|---------|--------|
| Директории по домену, не по действию | `tools/`, не `workflows/` |
| Файлы в `tools/` по сущности | `tracks.py`, не `track_tools.py` |
| Нет суффикса `_tools` в `tools/` | Избыточно: `tools/tracks.py`, не `tools/track_tools.py` |
| Нет версионных суффиксов | `schemas.py`, не `types_v2.py` |
| Infrastructure-файлы по конкретной функции | `resolvers.py`, не `entity_finder.py` |

### 4.2 Таблица переименований

| Текущее / Планируемое | Новое | Обоснование |
|----------------------|-------|-------------|
| `workflows/` | `tools/` | CRUD ≠ workflow; "tools" — FastMCP-терминология |
| `types.py` + `types_curation.py` | УДАЛИТЬ | Живые → `schemas.py`, мёртвые → удалить |
| `types_v2.py` (план) | `schemas.py` | Конвенция проекта: `app/schemas/` = Pydantic |
| `entity_finder.py` (план) | `resolvers.py` | "Resolve ref → entity", не "find" |
| `response.py` (план) | `envelope.py` | Конкретно: wraps response в envelope |
| `library_stats.py` (план) | `stats.py` | В контексте `app/mcp/` "library" избыточно |
| `analysis_tools.py` | УДАЛИТЬ | Заменён CRUD в `tools/tracks.py`, `tools/playlists.py` |
| `import_tools.py` | `tools/download.py` | Только `download_tracks` выживает |
| `setbuilder_tools.py` | `tools/sets.py` + `tools/scoring.py` | Split по concern |
| `export_tools.py` | `tools/export.py` | Без суффикса |
| `discovery_tools.py` | `tools/discovery.py` | Без суффикса |
| `curation_tools.py` | `tools/curation.py` | Без суффикса |
| `sync_tools.py` | `tools/sync.py` | Делегирует в `platforms/sync_engine.py` |

### 4.3 Полное дерево `app/mcp/` (после всех фаз)

```sql
app/mcp/
│
├── __init__.py                    # re-export create_dj_mcp
├── gateway.py                     # ~100 строк: compose & mount 3 namespaces
├── dependencies.py                # ~140 строк: 8 service + platform DI
├── lifespan.py                    # ~60 строк: + OTEL init + registry shutdown
├── observability.py               # 113 строк: middleware stack
│
│── # ─── Инфраструктура ref-resolution и response shaping ───
│
├── schemas.py                     # ~150 строк: Summary/Detail/Full + envelope models
│                                  #   TrackSummary, TrackDetail, PlaylistSummary,
│                                  #   SetSummary, ArtistSummary, FeaturesSummary,
│                                  #   LibraryStats, PaginationInfo, SearchResponse,
│                                  #   FindResult, EntityListResponse,
│                                  #   EntityDetailResponse, ActionResponse
│
├── refs.py                        # ~60 строк: parse_ref(), ParsedRef, RefType
├── resolvers.py                   # ~200 строк: Track/Playlist/Set/ArtistResolver
├── pagination.py                  # ~50 строк: cursor encode/decode
├── envelope.py                    # ~80 строк: wrap_list/detail/action
├── converters.py                  # ~120 строк: ORM → schema
├── stats.py                       # ~40 строк: get_library_stats()
│
│── # ─── DJ namespace: CRUD + оркестраторы ───
│
├── tools/
│   ├── __init__.py
│   ├── server.py                  # create_tool_server(): register all modules
│   │
│   │── # CRUD по сущностям
│   ├── tracks.py                  # list/get/create/update/delete tracks
│   ├── playlists.py               # list/get/create/update/delete playlists
│   ├── sets.py                    # list/get/create/update + build/rebuild
│   ├── features.py                # list/get/save features
│   │
│   │── # Оркестраторы
│   ├── search.py                  # search() + filter_tracks()
│   ├── scoring.py                 # score_transitions()
│   ├── export.py                  # export_set(format=...)
│   ├── download.py                # download_tracks()
│   ├── discovery.py               # find_similar_tracks()
│   ├── curation.py                # classify, gaps, review
│   └── sync.py                    # sync_playlist, sync_set_to/from_ym
│
│── # ─── Audio namespace (hidden) ───
│
├── audio/
│   ├── __init__.py
│   ├── server.py                  # create_audio_server() + activate_audio_mode()
│   └── compute.py                 # 12 tools: bpm, key, loudness, bands, spectral,
│                                  #   beats, mfcc, structure, stems,
│                                  #   transition_raw, groove, mood
│
│── # ─── Multi-platform абстракция ───
│
├── platforms/
│   ├── __init__.py
│   ├── protocol.py                # MusicPlatform Protocol
│   ├── registry.py                # PlatformRegistry
│   ├── keys.py                    # PlatformKey enum: ym → yandex_music
│   ├── sync_engine.py             # SyncEngine: diff + apply
│   ├── sync_diff.py               # compute_sync_diff() — pure function
│   └── track_mapper.py            # DbTrackMapper: local ↔ platform IDs
│
│── # ─── YM platform ───
│
├── yandex_music/
│   ├── __init__.py
│   ├── server.py                  # OpenAPI → MCP factory
│   ├── config.py                  # Route filtering + naming
│   ├── response_filters.py        # Response cleaning (~70% token reduction)
│   └── adapter.py                 # NEW: YandexMusicAdapter(MusicPlatform)
│
│── # ─── Prompts, Resources, Skills ───
│
├── prompts/
│   ├── __init__.py
│   └── workflows.py               # 3 рецепта
│
├── resources/
│   ├── __init__.py
│   └── status.py                  # 3 ресурса
│
└── skills/
    ├── build-set-from-scratch/
    │   └── SKILL.md
    ├── expand-playlist/
    │   └── SKILL.md
    └── improve-set/
        └── SKILL.md
```

### 4.4 Инвентарь инструментов

**dj namespace** (видимый, ~31):
- CRUD: 5×Track + 5×Playlist + 4×Set + 3×Features = **17**
- Оркестраторы: search, filter_tracks, score_transitions, export_set, download_tracks, find_similar_tracks, classify_tracks, analyze_library_gaps, review_set, build_set, rebuild_set = **11**
- Sync: sync_playlist, sync_set_to_ym, sync_set_from_ym = **3**

**audio namespace** (скрытый, 12):
- compute_bpm, compute_key, compute_loudness, compute_band_energies, compute_spectral, detect_beats, extract_mfcc, segment_structure, separate_stems, score_transition_raw, groove_similarity, classify_mood

**ym namespace** (скрытый, ~30):
- Без изменений — OpenAPI-generated

**Visibility tools** (2, на gateway):
- activate_audio_mode, activate_ym_raw

**Итого: ~75** (31 + 12 + ~30 + 2)

### 4.5 Что добавляется / удаляется / перемещается

| Действие | Файл | Фаза |
|----------|------|------|
| NEW | `schemas.py`, `refs.py`, `resolvers.py`, `pagination.py`, `stats.py` | Phase 1 |
| NEW | `tools/search.py` | Phase 1 |
| NEW | `envelope.py`, `converters.py` | Phase 2 |
| NEW | `tools/tracks.py`, `tools/playlists.py`, `tools/sets.py`, `tools/features.py` | Phase 2 |
| NEW | `tools/scoring.py` (extract from setbuilder) | Phase 2 |
| NEW | `audio/server.py`, `audio/compute.py` | Phase 2 |
| NEW | `platforms/protocol.py`, `platforms/registry.py`, `platforms/keys.py` | Phase 3 |
| NEW | `platforms/sync_engine.py`, `platforms/sync_diff.py`, `platforms/track_mapper.py` | Phase 3 |
| NEW | `yandex_music/adapter.py` | Phase 3 |
| MOVE | `workflows/server.py` → `tools/server.py` | Phase 2 |
| MOVE | `workflows/export_tools.py` → `tools/export.py` | Phase 2 |
| MOVE | `workflows/discovery_tools.py` → `tools/discovery.py` | Phase 2 |
| MOVE | `workflows/curation_tools.py` → `tools/curation.py` | Phase 2 |
| MOVE+RENAME | `workflows/import_tools.py` → `tools/download.py` | Phase 2 |
| MOVE+SPLIT | `workflows/setbuilder_tools.py` → `tools/sets.py` + `tools/scoring.py` | Phase 2 |
| REWRITE | `workflows/sync_tools.py` → `tools/sync.py` | Phase 3 |
| DELETE | `workflows/analysis_tools.py` | Phase 4 |
| DELETE | `types.py`, `types_curation.py` | Phase 4 |
| DELETE | `workflows/` (directory) | Phase 4 |

### 4.6 Тестовая структура

```text
tests/mcp/
├── conftest.py              # MCP fixtures: session override, mcp client
├── test_schemas.py
├── test_refs.py
├── test_resolvers.py
├── test_pagination.py
├── test_envelope.py
├── test_converters.py
├── test_stats.py
│
├── tools/
│   ├── conftest.py          # Seeded test data
│   ├── test_tracks.py
│   ├── test_playlists.py
│   ├── test_sets.py
│   ├── test_features.py
│   ├── test_search.py
│   ├── test_scoring.py
│   ├── test_export.py
│   ├── test_download.py
│   ├── test_discovery.py
│   ├── test_curation.py
│   └── test_sync.py
│
├── audio/
│   ├── conftest.py          # Synthetic audio fixtures
│   └── test_compute.py
│
├── platforms/
│   ├── test_protocol.py
│   ├── test_registry.py
│   ├── test_keys.py
│   ├── test_sync_engine.py
│   └── test_track_mapper.py
│
└── yandex_music/
    ├── test_adapter.py
    └── test_filters.py
```

---

## 5. Рекомендации по порядку реализации

### 5.1 Что нужно исправить ДО начала кодирования

1. **Tool contract**: решить, что tools возвращают Pydantic models, обновить все тесты на `result.data`
2. **MCP test harness**: создать fixture с override `get_session` для test DB
3. **PlatformKey enum**: определить mapping `ym → yandex_music` до Phase 3
4. **AudioAsset resolver**: определить, как `track_ref → audio_path` (нужно для audio namespace)

### 5.2 Рекомендуемый порядок

```text
Phase 0 (prereq):  test harness + tool contract + PlatformKey
Phase 1:           refs + resolvers + schemas + pagination + stats + search
Phase 5-P1:        OTEL + timeouts + versioning (параллельно)
Phase 2:           CRUD + envelope + converters + export unification + audio namespace
Phase 3:           platforms + adapter + sync (после решения ID/key/write блокеров)
Phase 4:           cleanup (после Phase 3)
Phase 5-rest:      background tasks + elicitation (если нужно)
```
