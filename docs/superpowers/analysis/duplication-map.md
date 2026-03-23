# Карта дублирования

> 6 пар из дизайн-спека + найденный баг hp_ratio

## Сводная таблица

| # | Пара | Дубл. строк | Приоритет | Стратегия | Баг? |
|---|------|-------------|-----------|-----------|------|
| 1 | Два `TrackFeatures` | 0 (разные домены) | Низкий | Переименовать DSP-версию → `AllFeatures` | Нет |
| 2 | Два YM клиента | ~60 | Высокий | Merge в один с rate limiting | Нет |
| 3 | Два scoring модуля | ~165 (весь v1) | Высокий | Удалить v1, мигрировать persistence | Нет |
| 4 | Два M3U генератора | ~35 | Средний | `_write_m3u8()` → вызов `export_m3u()` | Нет |
| 5 | Две DI системы | ~40 (конструкторов) | Средний | Извлечь `_factories.py` | Нет |
| 6 | Тройной ORM→TrackData | ~50×3 | **Высокий** | Одна `orm_to_track_data()` | **Да: hp_ratio** |

---

## Пара 1: Два TrackFeatures

### Файлы

- `app/utils/audio/_types.py` — DSP-ориентированный, оборачивает result objects (`BpmResult`, `KeyResult`, etc.)
- `app/services/transition_scoring.py:32` — плоский frozen dataclass, 15 числовых полей для scoring

### Анализ

Это НЕ дублирование кода — это коллизия имён. Два класса с одним именем, разные домены:

| Аспект | `_types.py` версия | `transition_scoring.py` версия |
|--------|-------------------|-------------------------------|
| Назначение | Контейнер для DSP результатов | Плоские числа для scoring |
| Поля | `bpm: BpmResult`, `key: KeyResult`, etc. | `bpm: float`, `key_code: int`, etc. |
| Frozen | Да | Да |
| Slots | Да | Да |
| Используется в | DSP pipeline (`extract_all_features`) | Transition scoring, set generation |

### Решение

Переименовать `_types.py:TrackFeatures` → `AllFeatures` (выход `extract_all_features()`). Scoring-версия остаётся `TrackFeatures` — она используется шире и ближе к доменной модели.

---

## Пара 2: Два YM клиента

### Файлы

- `app/clients/yandex_music.py` — тонкий httpx wrapper, ~120 LOC
- `app/services/yandex_music_client.py` — с rate limiting + download, ~200 LOC

### Сравнение методов

| Метод | `clients/` | `services/` | Различие |
|-------|-----------|------------|----------|
| `search_tracks(query)` | Да | Да | services добавляет rate limit |
| `fetch_tracks(track_ids)` | Да | Да | Идентичны |
| `create_playlist(...)` | Да | Нет | — |
| `add_tracks_to_playlist(...)` | Да | Нет | — |
| `get_playlist(...)` | Нет | Да | — |
| `download_track(...)` | Нет | Да | С retry + iCloud path |
| Rate limiting | Нет | Да (`asyncio.sleep(1.5)`) | — |
| Auth | Token + headers | Token + headers (одинаково) | — |

### Решение

Merge в один `YandexMusicClient` в `services/platform/yandex/client.py`:
- Все методы из обоих клиентов
- Rate limiting встроен (configurable delay)
- Download с retry
- `app/clients/` удаляется

---

## Пара 3: Два scoring модуля

### Файлы

- `app/utils/audio/transition_score.py` — v1, ~165 LOC, 3 компонента (BPM, Key, Energy)
- `app/services/transition_scoring.py` — v2, ~250 LOC, 6 компонентов (+ Spectral, Groove, MFCC)

### Сравнение

| Аспект | v1 | v2 |
|--------|----|----|
| Компоненты | BPM (0.30), Key (0.25), Energy (0.45) | BPM (0.30), Key (0.25), Energy (0.20), Spectral (0.15), Groove (0.10) |
| MFCC | Нет | Да (cosine similarity) |
| Camelot enrichment | Нет | Да (60% chroma + 40% HNR) |
| Hard constraints | BPM >10 → 0 | BPM >10, Camelot ≥5, Energy >6 LUFS → 0 |
| Вызывающие файлы | `transition_persistence.py` (legacy) | Всё остальное |

### Решение

Удалить v1 (`transition_score.py`). Мигрировать `TransitionPersistenceService` на v2. Удалить re-export из `app/utils/audio/__init__.py`.

---

## Пара 4: Два M3U генератора

### Файлы

- `app/services/set_export.py:38-156` — `export_m3u()`, полная версия с 15+ тегами
- `app/mcp/tools/delivery.py:259-276` — `_write_m3u8()`, 18 строк, 3 DJ-тега

### Потерянные теги в упрощённой версии

| Тег | `export_m3u()` | `_write_m3u8()` |
|-----|----------------|-----------------|
| `#EXTART:` | ✅ | ❌ |
| `#EXTGENRE:` | ✅ | ❌ |
| `#EXTVLCOPT:` (mix points) | ✅ | ❌ |
| `#EXTDJ-CUE:` | ✅ | ❌ |
| `#EXTDJ-LOOP:` | ✅ | ❌ |
| `#EXTDJ-SECTION:` | ✅ | ❌ |
| `#EXTDJ-EQ:` | ✅ | ❌ |
| `#EXTDJ-TRANSITION:` | ✅ | ❌ |
| `#EXTDJ-NOTE:` | ✅ | ❌ |

Аналогично: `_write_json_guide()` (delivery:279-297) — упрощённая копия `export_json_guide()` (set_export:197-312), пропущены cue points, loops, sections, analytics.

### Решение

Заменить `_write_m3u8()` вызовом `export_m3u()` с подготовленными данными. Один M3U generator в `domain/setbuilder/export/m3u.py`.

---

## Пара 5: Две DI системы

### Файлы

- `app/dependencies.py` — 8 строк, только `DbSession = Annotated[AsyncSession, Depends(get_session)]`
- `app/mcp/dependencies.py` — 176 строк, 13 factory functions

### Дублирование конструкторов

| Сервис | FastAPI (inline в router) | MCP dependencies.py |
|--------|--------------------------|---------------------|
| `TrackService(TrackRepo(db))` | `tracks.py:18` | строка 55 |
| `DjPlaylistService(PlaylistRepo, ItemRepo)` | `playlists.py:26-28` | строки 62-65 |
| `AudioFeaturesService(FeaturesRepo, TrackRepo)` | `features.py:14` | строки 71-75 |
| `DjSetService(SetRepo, VersionRepo, ItemRepo)` | `sets.py:34-37` | строки 93-97 |
| `TrackAnalysisService(TrackRepo, FeaturesRepo, SectionsRepo)` | `analysis.py:22-25` | строки 82-86 |

### Решение

Извлечь `services/_factories.py` с чистыми функциями:
```python
def build_track_service(session: AsyncSession) -> TrackService:
    return TrackService(TrackRepository(session))
```
Обе DI системы вызывают фабрики. DI-фреймворки (`fastapi.Depends` vs `fastmcp.Depends`) остаются разные — это нормально.

---

## Пара 6: Тройной ORM→TrackData (⚠️ СОДЕРЖИТ БАГ)

### Три места

| Файл | Строки | Полнота classify_track() | mood |
|------|--------|--------------------------|------|
| `services/set_generation.py` | 163-190 | 6 параметров | ✅ mood + artist_id |
| `mcp/tools/setbuilder.py` | 73-82 | 0 параметров | ❌ mood=0 по умолчанию |
| `mcp/tools/curation.py` | 206-219 | 0 (pre-classified) | ✅ mood из pre-classified dict |

Бонус: `services/set_curation.py:50-67` — **13 параметров** для classify_track() (полная версия).

### ⚠️ Баг: hp_ratio дефолт

| Поле | `set_generation.py` | `set_curation.py` | P50 техно |
|------|---------------------|--------------------|-----------|
| `hp_ratio` | `or 0.5` | `or 2.0` | ~2.2 |

`set_generation.py` использует дефолт `0.5`, что указывает на percussive-доминантный трек. Реальный P50 для техно — 2.2 (harmonic-dominant). `set_curation.py` правильнее с `2.0`.

Также `set_generation.py` пропускает 7 параметров (flux_mean, flux_std, energy_std, energy_mean, lra_lu, crest_factor_db, flatness_mean), что даёт менее точную классификацию.

### Решение

Одна функция `orm_to_track_data(feat, artist_id=0) -> TrackData` в `services/_converters.py`:
- Вызывает `classify_track()` с ВСЕМИ 13 параметрами
- Единый набор дефолтов (из set_curation.py — правильные)
- Все 3+ call-sites заменяются на вызов этой функции
- Исправляет баг hp_ratio автоматически
