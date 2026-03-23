# План атомарных шагов рефакторинга

> Каждый шаг = 1 коммит. Тесты зелёные после каждого шага.
> Приоритет: сначала DRY (merge дублирования), потом extract (split god objects), потом move (layer structure).

---

## Phase 0: Bug fix + DRY merges (без структурных изменений)

### Step 0.1: Fix hp_ratio bug + create `orm_to_track_data()`

**Что**: Создать `app/utils/audio/feature_conversion.py:orm_to_track_data()` — единая функция ORM→TrackData с classify_track(). Использовать ПРАВИЛЬНЫЕ дефолты из `set_curation.py` (hp_ratio=2.0).

**Файлы**:
- `app/utils/audio/feature_conversion.py` — добавить `orm_to_track_data()`
- `app/services/set_generation.py:163-190` — заменить inline конструкцию
- `app/mcp/tools/setbuilder.py:73-82` — заменить inline конструкцию
- `app/mcp/tools/curation.py:206-219` — заменить inline конструкцию
- `app/services/set_curation.py:50-67` — заменить inline classify_track()

**Метрика**: `rg "TrackData(" app/ --count` уменьшается на 3. `rg "hp_ratio.*0\.5" app/` = 0.
**Верификация**: `make check` проходит. Классификация треков стала консистентной.

```text
commit: fix(audio): unify ORM→TrackData conversion, fix hp_ratio default 0.5→2.0
```

### Step 0.2: Delete v1 scoring module

**Что**: Удалить `app/utils/audio/transition_score.py` (v1, 165 LOC). Мигрировать единственный импортёр `TransitionPersistenceService`.

**Файлы**:
- `app/utils/audio/transition_score.py` — DELETE
- `app/utils/audio/__init__.py` — убрать re-export
- `app/services/transition_persistence.py` — мигрировать на v2 `TransitionScoringService`

**Метрика**: `fd transition_score.py app/utils/` = 0. Файлов scoring = 1 (не 2).
**Верификация**: `make check`. `rg "transition_score" app/ --count` = 0 (кроме transition_scoring).

```text
commit: refactor(audio): remove v1 scoring module, consolidate into TransitionScoringService
```

### Step 0.3: Create `services/_factories.py` for unified DI

**Что**: Извлечь фабричные функции из inline router `_service()` и `mcp/dependencies.py`.

**Файлы**:
- `app/services/_factories.py` — NEW: `build_track_service()`, `build_playlist_service()`, etc.
- `app/routers/v1/tracks.py` — `_service()` вызывает factory
- `app/routers/v1/playlists.py` — аналогично
- `app/routers/v1/features.py` — аналогично
- `app/routers/v1/sets.py` — аналогично
- `app/routers/v1/analysis.py` — аналогично
- `app/mcp/dependencies.py` — вызывает factories

**Метрика**: `rg "Repository\(.*session\)" app/routers/ --count` уменьшается. Routers и MCP DI вызывают одни фабрики.
**Верификация**: `make check`.

```bash
commit: refactor(di): create services/_factories.py for unified service construction
```

### Step 0.4: Merge two M3U generators

**Что**: Заменить `delivery.py:_write_m3u8()` вызовом `set_export.py:export_m3u()`.

**Файлы**:
- `app/mcp/tools/delivery.py` — удалить `_write_m3u8()`, вызывать `export_m3u()`
- `app/services/set_export.py` — при необходимости добавить параметр для локальных путей

**Метрика**: `rg "def _write_m3u8" app/` = 0. Один M3U generator.
**Верификация**: `make check`. Delivery M3U теперь содержит ВСЕ DJ-теги.

```text
commit: refactor(export): consolidate M3U generation into single export_m3u()
```

### Step 0.5: Merge two YM clients

**Что**: Объединить `clients/yandex_music.py` и `services/yandex_music_client.py` в один.

**Файлы**:
- `app/services/yandex_music_client.py` — добавить недостающие методы из clients/
- `app/clients/yandex_music.py` — DELETE
- `app/clients/__init__.py` — DELETE (или оставить пустым)
- Все импортёры `from app.clients.yandex_music` → `from app.services.yandex_music_client`

**Метрика**: `rg "class YandexMusicClient" app/` = 1. `fd yandex_music.py app/clients/` = 0.
**Верификация**: `make check`.

```text
commit: refactor(ym): merge two YandexMusicClient classes into single implementation
```

---

## Phase 1: Extract business logic from MCP tools

### Step 1.1: Extract CandidateDiscoveryService from curation_discovery.py

**Что**: Самое критичное — god function 297 LOC с прямыми ORM вызовами.

**Файлы**:
- `app/services/candidate_discovery.py` — NEW: `CandidateDiscoveryService` (~250 LOC)
  - `discover_from_seed(seed_track_ids, session)` — YM recommendations + filter
  - `filter_candidates(tracks)` — is_techno, bad_version, duration
  - `batch_import(ym_tracks, session)` — create Track, ProviderTrackId, YandexMetadata through repos
  - `add_to_playlist(track_ids, playlist_id, session)` — через PlaylistRepository
- `app/mcp/tools/curation_discovery.py` — SLIM to ~100 LOC (3 thin adapters)
- `app/mcp/dependencies.py` — add `get_discovery_service()`

**Метрика**: `wc -l app/mcp/tools/curation_discovery.py` ≤ 120. `rg "session\.add\|session\.flush\|session\.execute" app/mcp/tools/` уменьшается на 6+.
**Верификация**: `make check`. `rg "from sqlalchemy" app/mcp/tools/curation_discovery.py` = 0.

```text
commit: refactor(mcp): extract CandidateDiscoveryService from curation_discovery.py (563→~100 LOC)
```

### Step 1.2: Extract DeliveryService from delivery.py

**Что**: Бизнес-логика delivery (scoring, file copy, cheat sheet, YM sync) → service.

**Файлы**:
- `app/services/delivery.py` — NEW: `DeliveryService` (~300 LOC)
- `app/mcp/tools/delivery.py` — SLIM to ~80 LOC
- `app/mcp/dependencies.py` — add `get_delivery_service()`

**Метрика**: `wc -l app/mcp/tools/delivery.py` ≤ 100. `rg "from sqlalchemy" app/mcp/tools/delivery.py` = 0.
**Верификация**: `make check`.

```text
commit: refactor(mcp): extract DeliveryService from delivery.py (518→~80 LOC)
```

### Step 1.3: Extract SetReviewService from curation.py

**Что**: review_set бизнес-логика (120 LOC) → service.

**Файлы**:
- `app/services/set_review.py` — NEW: `SetReviewService` (~120 LOC)
- `app/mcp/tools/curation.py` — slim review_set to ~20 LOC adapter
- `app/mcp/dependencies.py` — add `get_review_service()`

**Метрика**: `wc -l app/mcp/tools/curation.py` ≤ 300. review_set в tool ≤ 30 LOC.
**Верификация**: `make check`.

```text
commit: refactor(mcp): extract SetReviewService from curation.py review_set
```

### Step 1.4: Remove direct repo/model imports from remaining MCP tools

**Что**: Шаг за шагом — убрать `from app.repositories` и `from app.models` из MCP tools, делегируя через services/DI.

**Sub-steps** (можно отдельными коммитами):
- `tools/search.py` — 5 repo imports → SearchService или DI
- `tools/playlist.py` — 2 repos + 2 models → PlaylistService
- `tools/set.py` — 3 repos → DI через dependencies
- `tools/track.py` — 2 repos → DI через dependencies
- `tools/features.py` — 2 repos → DI через dependencies
- `tools/sync.py` — 2 models → через SyncEngine/services
- `tools/compute.py` — 3 repos + 1 model (lazy) → through services

**Метрика**: `rg "from app\.repositories\." app/mcp/tools/ --count` = 0. `rg "from app\.models\." app/mcp/tools/ --count` = 0.
**Верификация**: `make check` после каждого sub-step.

```text
commit: refactor(mcp): remove direct repo imports from tools/search.py
commit: refactor(mcp): remove direct repo imports from tools/playlist.py
...
```

---

## Phase 2: Split god objects (pure domain)

### Step 2.1: Extract energy_arcs from set_generator.py

**Что**: EnergyArcType, breakpoints, target_energy_curve, lufs_to_energy → отдельный модуль.

**Файлы**:
- `app/utils/audio/energy_arcs.py` — NEW (~110 LOC)
- `app/utils/audio/set_generator.py` — import from energy_arcs
- Все импортёры `lufs_to_energy`, `target_energy_curve` → from energy_arcs

**Метрика**: `wc -l app/utils/audio/set_generator.py` уменьшается на ~110.
**Верификация**: `make check`.

```text
commit: refactor(ga): extract energy arc logic from set_generator.py
```

### Step 2.2: Extract types from set_generator.py

**Что**: GAConfig, TrackData, GAConstraints, GAResult, EnergyArcType → `_types.py` или `set_types.py`.

**Файлы**:
- Добавить в `app/utils/audio/_types.py` или создать `app/utils/audio/set_types.py`
- `app/utils/audio/set_generator.py` — import types
- Обновить все импортёры

**Метрика**: `wc -l app/utils/audio/set_generator.py` уменьшается на ~60.
**Верификация**: `make check`.

```text
commit: refactor(ga): extract GA types (GAConfig, TrackData, etc.) from set_generator.py
```

### Step 2.3: Extract operators and local search from GeneticSetGenerator

**Что**: Сделать _order_crossover, _mutate, _mutate_replace, _two_opt, _relocate_worst standalone functions.

**Файлы**:
- `app/utils/audio/ga_operators.py` — NEW (~120 LOC)
- `app/utils/audio/ga_local_search.py` — NEW (~100 LOC)
- `app/utils/audio/set_generator.py` — GeneticSetGenerator вызывает standalone functions

**Метрика**: `wc -l app/utils/audio/set_generator.py` ≤ 500. Класс — чистый orchestrator.
**Верификация**: `make check`.

```text
commit: refactor(ga): extract GA operators and local search into standalone modules
```

---

## Phase 3: Layer structure (move to target dirs)

> Выполняется ПОСЛЕ Phase 0-2. Файлы уже тонкие и чистые — перемещение безопасно.

### Step 3.1: Create core/ layer

Move: `config.py`, `database.py`, `errors.py`, `_compat.py` + base classes.

### Step 3.2: Create domain/ layer

Move: `utils/audio/` → `domain/audio/` (DSP, scoring, classifier, set builder).

### Step 3.3: Restructure repositories/ into subdirs

Group: catalog/, audio/, dj/, platform/.

### Step 3.4: Restructure services/ into subdirs

Group: catalog/, audio/, dj/, platform/, library/.

### Step 3.5: Rename routers/ → api/

### Step 3.6: Add import-linter contracts

### Step 3.7: Update documentation

---

## Метрики валидации (после всех фаз)

| Метрика | Before | After |
|---------|--------|-------|
| Max file LOC | 912 | ≤300 |
| MCP tool max LOC | 563 | ≤80 |
| Duplicate code pairs | 6 | 0 |
| Raw SQL in adapters | 7 files | 0 |
| Direct repo imports in MCP | 18 | 0 |
| Direct model imports in MCP | 11 | 0 |
| `make check` | passes | passes |
| hp_ratio bug | present | fixed |
