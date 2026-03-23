# Анализ God Objects

> 3 файла, суммарно 2484 LOC. Извлекаемый домен: ~1340 LOC.

## Сводка

| Файл | LOC | Ответственностей | Нарушения архитектуры | Приоритет |
|------|-----|-------------------|-----------------------|-----------|
| `set_generator.py` | 912 | 5 (engine, fitness, operators, local search, config) | Нет (pure domain) | P2 |
| `delivery.py` | 518 | 3 (scoring, file I/O, YM sync) | Raw SQL, ORM imports | P1 |
| `curation_discovery.py` | 563 | 3 (discovery, import, playlist) | **Raw SQL, ORM напрямую, обход repos** | **P0** |
| `curation.py` | 491 | 4 (classify, gaps, review, audit) | Бизнес-логика в adapter | P1 |

---

## 1. set_generator.py (912 LOC) — PURE DOMAIN

### Структура

| Блок | Строки | LOC | Категория |
|------|--------|-----|-----------|
| `EnergyArcType(StrEnum)` | 21-27 | 7 | CONFIG |
| `GAConfig` | 30-50 | 21 | CONFIG |
| `TrackData` | 53-62 | 10 | CONFIG |
| `GAConstraints` | 65-70 | 6 | CONFIG |
| `GAResult` | 73-83 | 11 | CONFIG |
| `_interpolate_breakpoints()` | 86-103 | 18 | DOMAIN: energy arcs |
| Arc breakpoints (4 dicts) | 116-168 | 53 | CONFIG: energy arcs |
| `target_energy_curve()` | 171-188 | 18 | DOMAIN: energy arcs |
| `lufs_to_energy()` | 191-196 | 6 | DOMAIN: utility |
| `variety_score()` | 199-227 | 29 | DOMAIN: fitness |
| `template_slot_fit()` | 230-279 | 50 | DOMAIN: fitness |
| `GeneticSetGenerator.__init__` | 298-331 | 34 | ENGINE: setup |
| `GeneticSetGenerator.run` | 333-418 | 86 | ENGINE: main loop |
| Population init (4 методов) | 422-581 | 160 | DOMAIN: init |
| Fitness methods (7) | 585-685 | 101 | DOMAIN: fitness |
| `_tournament_select` | 689-696 | 8 | DOMAIN: selection |
| `_order_crossover` | 700-741 | 42 | DOMAIN: operators |
| `_mutate`, `_mutate_replace` | 745-813 | 69 | DOMAIN: operators |
| `_relocate_worst`, `_two_opt` | 815-912 | 98 | DOMAIN: local search |

### Зависимости

- `numpy`, `random` — стандартные
- `app.utils.audio.set_templates.SetSlot` — единственная внутренняя

**Нет framework imports.** Файл уже pure domain logic.

### Проблема

5 ответственностей в одном классе `GeneticSetGenerator`:
1. **GA Engine** — run loop, population management
2. **Fitness** — 7 evaluation methods
3. **Operators** — crossover, mutation
4. **Local search** — two-opt, relocate
5. **Energy arc config** — breakpoints, curves

### Предложенный сплит

| Новый файл | Содержимое | LOC |
|------------|-----------|-----|
| `domain/setbuilder/types.py` | GAConfig, TrackData, GAConstraints, GAResult, EnergyArcType | ~60 |
| `domain/setbuilder/energy_arcs.py` | Breakpoints, target_energy_curve, _interpolate, lufs_to_energy | ~110 |
| `domain/setbuilder/genetic/engine.py` | GeneticSetGenerator (run, init, population, selection, fitness) | ~350 |
| `domain/setbuilder/genetic/operators.py` | order_crossover, mutate, mutate_replace (standalone) | ~120 |
| `domain/setbuilder/genetic/local_search.py` | two_opt, relocate_worst (standalone) | ~100 |
| `domain/setbuilder/genetic/fitness.py` | variety_score, template_slot_fit, pinned_spread (standalone) | ~130 |

**Важно**: fitness methods, использующие `self._matrix`, `self._energies`, `self._bpms` — остаются в `engine.py` (тесно связаны с внутренним state). Extractable — только standalone functions.

---

## 2. delivery.py (518 LOC) — MCP TOOL С БИЗНЕС-ЛОГИКОЙ

### Структура

| Функция | Строки | LOC | Категория |
|---------|--------|-----|-----------|
| `_safe_name()` | 57-60 | 4 | DOMAIN: string util |
| `_output_dir()` | 63-67 | 5 | DOMAIN: path resolution |
| `_score_version()` | 70-81 | 12 | ADAPTER: service delegation |
| `_build_transition_summary()` | 84-92 | 9 | DOMAIN: pure aggregation |
| `_score_bar()` | 95-100 | 6 | DOMAIN: formatting |
| `_energy_bar()` | 103-109 | 7 | DOMAIN: formatting |
| `_generate_cheat_sheet()` | 112-173 | 62 | DOMAIN: text generation |
| `_collect_track_data()` | 176-221 | 46 | **ADAPTER: DB queries (session, ORM)** |
| `_is_icloud_stub()` | 224-230 | 7 | DOMAIN: filesystem check |
| `_copy_mp3_files()` | 233-256 | 24 | DOMAIN: file I/O |
| `_write_m3u8()` | 259-276 | 18 | DOMAIN: M3U (дупликат export_m3u) |
| `_write_json_guide()` | 279-297 | 19 | DOMAIN: JSON (дупликат export_json) |
| `_sync_to_ym()` | 303-346 | 44 | **ADAPTER: YM API + ORM** |
| `deliver_set()` (MCP tool) | 356-518 | 163 | ADAPTER: MCP orchestration |

### Нарушения

- `_collect_track_data()` — прямые ORM queries (select DjLibraryItem, join features)
- `_sync_to_ym()` — прямой select YandexMetadata + YM API calls
- `_write_m3u8()` / `_write_json_guide()` — дублирование `set_export.py`

### Предложенный сплит

| Новый файл | Содержимое | LOC |
|------------|-----------|-----|
| `services/dj/delivery.py` | `DeliveryService`: collect_track_data, copy_mp3, generate_cheat_sheet, write_exports, sync_to_ym | ~300 |
| `mcp/tools/delivery.py` (slim) | `deliver_set()` — DI, ctx.info, ctx.report_progress, resolve_conflict, delegate to service | ~80 |

**DeliveryService** инжектит: DjSetService, AudioFeaturesService, UnifiedScoringService, TrackService, DjLibraryItemRepository, YandexMetadataRepository, YandexMusicClient.

---

## 3. curation_discovery.py (563 LOC) — **КРИТИЧЕСКИЙ** GOD OBJECT

### Структура

| Функция | Строки | LOC | Категория |
|---------|--------|-----|-----------|
| `_BAD_VERSION_WORDS` | 31-41 | 11 | CONFIG |
| `_MIN_DURATION_MS` | 42 | 1 | CONFIG |
| `_is_techno()` | 45-51 | 7 | DOMAIN: genre filter |
| `_has_bad_version()` | 54-60 | 7 | DOMAIN: title filter |
| `discover_candidates()` | 67-150 | 84 | MIXED: YM API + filtering |
| `expand_playlist_discover()` | 153-264 | 112 | MIXED: DB + YM + filtering |
| `expand_playlist_full()` | 267-563 | **297** | **GOD FUNCTION: discovery + import + DB writes** |

### Нарушения (наихудшие в проекте)

1. **Прямые ORM imports**: `Track`, `DjPlaylistItem`, `ProviderTrackId`, `YandexMetadata`
2. **Raw SQL**: `func, select` — обход Repository pattern
3. **session.add() / session.flush()** прямо в MCP tool — обход Repository layer
4. **297-строчная функция** `expand_playlist_full()` делает ВСЁ: discovery, import, track creation, playlist management
5. **Тройное дублирование**: логика фильтрации (genre check, duration, bad version) повторяется в 3 функциях

### Предложенный сплит

| Новый файл | Содержимое | LOC |
|------------|-----------|-----|
| `domain/platform/filters.py` | `_is_techno()`, `_has_bad_version()`, constants | ~30 |
| `services/platform/yandex/discovery.py` | `CandidateDiscoveryService`: discover_from_seed, filter_candidates, batch_import, add_to_playlist | ~250 |
| `mcp/tools/curation_discovery.py` (slim) | 3 thin MCP adapters: DI + ctx + delegate | ~100 |

---

## 4. curation.py (491 LOC) — MCP TOOL С БИЗНЕС-ЛОГИКОЙ

### Структура

| Функция | Строки | LOC | Категория |
|---------|--------|-----|-----------|
| `classify_tracks()` | 43-72 | 30 | ADAPTER (thin): → SetCurationService |
| `analyze_library_gaps()` | 75-135 | 61 | MIXED: template logic + formatting |
| `review_set()` | 138-257 | 120 | **DOMAIN: scoring + arc analysis в adapter** |
| `audit_playlist()` | 264-378 | 115 | **DOMAIN: techno criteria (hardcoded thresholds)** |
| `subgenre_display` | 381-397 | 17 | CONFIG |
| `distribute_to_subgenres()` | 400-491 | 92 | MIXED: classification + playlist routing |

### Нарушения

- `review_set()` — 120 LOC бизнес-логики: imports `TrackData`, `lufs_to_energy`, `variety_score` из set_generator, строит track_data_list, считает arc adherence
- `audit_playlist()` — 12 hardcoded techno thresholds, должны быть в domain

### Предложенный сплит

| Новый файл | Содержимое | LOC |
|------------|-----------|-----|
| `domain/audio/techno_criteria.py` | Пороги, `audit_track()` pure function | ~80 |
| `services/dj/review.py` | `SetReviewService`: review logic, arc adherence, weak transitions | ~120 |
| `mcp/tools/curation.py` (slim) | 5 thin MCP adapters | ~150 |

---

## Порядок рефакторинга God Objects

| Шаг | Файл | Причина приоритета |
|-----|------|--------------------|
| 1 | `curation_discovery.py` | P0: максимум нарушений, god function 297 LOC |
| 2 | `delivery.py` | P1: raw SQL + ORM в adapter, дубликаты export |
| 3 | `curation.py` | P1: 120 LOC бизнес-логики в adapter |
| 4 | `set_generator.py` | P2: уже pure domain, нет framework deps — split для читаемости |
