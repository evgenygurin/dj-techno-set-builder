# DJ Techno Set Builder — Python/архитектурный аудит и план внедрения

Дата: 2026-02-15  
Область: код, библиотеки, архитектура сервисов, точки интеграции для реализации  
Источники: `app/services/*`, `app/utils/audio/*`, `app/mcp/workflows/*`, `app/repositories/*`, `pyproject.toml`, `dev.db`

## 1) Текущая архитектурная картина

Стек:

- FastAPI + SQLAlchemy async + Pydantic
- DSP extraction в `app/utils/audio/*` (Essentia/NumPy/SciPy)
- orchestration через сервисы `app/services/*`
- MCP инструменты поверх сервисов (`app/mcp/workflows/*`)

Главные контуры:

1. Feature extraction:
- `TrackAnalysisService` -> `extract_all_features` / `analyze_track_full`
- сохранение в `track_audio_features_computed` (+ `track_sections` для full analysis)

2. Set generation:
- `SetGenerationService.generate()` -> `GeneticSetGenerator`
- transition matrix строится в `_build_transition_matrix_scored`

3. Transition API:
- `/api/v1/transitions/compute` -> `TransitionPersistenceService` -> `utils.audio.transition_score`

Итог: в проекте два разных “источника истины” для transition scoring.

## 2) Критичные архитектурные разрывы

## 2.1 Дублирование скоринга (divergence risk)

Параллельно существуют:

- `app/services/transition_scoring.py` (используется в GA/MCP setbuilder)
- `app/utils/audio/transition_score.py` (используется в TransitionPersistenceService/API)

Риски:

- разные веса, разные компоненты, разная интерпретация признаков;
- пользователь видит одну оценку в set generation и другую в `/transitions/compute`.

## 2.2 Key-edge lookup в GA не использует БД

В `SetGenerationService`:

- `CamelotLookupService()` создаётся без session.

Поведение в таком режиме:

- fallback same-key=1.0, остальное=0.5.

Риск:

- таблица `key_edges` (и её музыкальная логика) фактически не участвует в генерации.

## 2.3 Section pipeline не доведён до set items

Есть:

- `track_sections` persistence.

Нет:

- автоматического заполнения `mix_in_ms`, `mix_out_ms`, `transition_id`, `in_section_id`, `out_section_id` в `dj_set_items`.

Риск:

- данные структуры есть, но execution layer сета ими не управляет.

## 2.4 Learning loop не подключен

`dj_set_feedback` модель есть, но нет сервиса/эндпоинтов/обновления весов на её основе.

Риск:

- система не обучается на фактическом результате выступления/прослушивания.

## 3) Библиотеки и код: что использовать для реализации

## DSP/analysis

- `essentia`:
  - BPM, key detection, loudness, spectral, beats
- `numpy`, `scipy`:
  - фильтрация band energy, статистика, similarity

## API/data

- `fastapi`, `pydantic`, `sqlalchemy[asyncio]`, `aiosqlite`/PostgreSQL

## Что уже реализовано и пригодно для переиспользования

- extraction модульность (`TrackFeatures` dataclasses)
- GA инфраструктура (`GeneticSetGenerator`, energy arc templates)
- ORM слой для sections, transitions, set_items
- MCP workflow инструменты для exploratory работы

## 4) Implementation plan по коду (конкретные файлы)

## Шаг 1. Устранить разрыв в Camelot lookup

Изменения:

- `app/services/set_generation.py`
  - передать в `CamelotLookupService` реальный session (через repo/session)
- `app/mcp/workflows/setbuilder_tools.py`
  - аналогично использовать lookup с DB session

Тесты:

- добавить проверку, что при наличии `key_edges` score меняется в соответствии с весами из БД.

## Шаг 2. Выбрать единый transition scoring engine

Решение:

- оставить один компонент (рекомендуется service-based с явными dataclass input).
- второй слой превратить в thin adapter или удалить после миграции.

Изменения:

- `app/services/transition_persistence.py`
- `app/routers/v1/transitions.py`
- `app/services/set_generation.py`
- `app/mcp/workflows/setbuilder_tools.py`

Тесты:

- parity tests: одинаковые входы -> одинаковые скоры в API/GA/MCP.

## Шаг 3. Section-aware scoring pipeline

Изменения:

- новый сервис, например `app/services/section_transition_scoring.py`
- расширение `SetGenerationService`:
  - при сборке версии выбирать `out_section`/`in_section`
  - заполнять `mix_in_ms`, `mix_out_ms`, section references
- возможно: отдельная таблица precomputed section transitions

Тесты:

- корректность выбора валидных секций
- invariants: `mix_in_ms >= 0`, `mix_out_ms >= mix_in_ms`

## Шаг 4. Persist transitions/candidates в рабочем потоке

Сейчас `transitions`/`candidates` пусты. Нужно:

- batch job или endpoint для массового precompute pair scores
- запись кандидатов + full transitions по политике top-K

Изменения:

- `app/services/transition_persistence.py` (+ orchestration service)
- `app/services/runs.py`/`transition_runs` lifecycle

Тесты:

- run completion + expected row counts
- idempotency (повторный запуск не ломает данные)

## Шаг 5. Feedback loop

Изменения:

- добавить сервис/роутер для `dj_set_feedback` CRUD
- добавить offline calibration job весов

Тесты:

- сохранение feedback на уровень set/item
- воспроизводимая калибровка весов на sample dataset

## 5) Data contracts и валидации

Нужные инварианты:

- `bpm` range, `key_code` range уже проверяются DB constraints
- добавить runtime guards:
  - не использовать “почти константные” признаки без масштабирования
  - normalize feature blocks перед cosine/euclidean

Рекомендация:

- ввести единый `FeatureVectorBuilder`:
  - получает ORM row
  - возвращает валидированный/нормализованный вектор для scoring
  - единообразно используется в API, GA и MCP

## 6) План тестирования

1. Unit:
- scoring components, lookup behavior, section mix-point heuristics

2. Integration:
- analyze -> features -> generate -> set_items populated with mix metadata

3. Regression:
- snapshot сравнение quality distribution до/после

4. Performance:
- `N x N` precompute latency и память
- GA runtime на 100/500/1000 треков

5. Quality gates:
- не менее заданной доли harmonic-compatible transitions
- меньше median BPM/LUFS jumps

## 7) Риски и mitigation

Риск: деградация генерации при резком усилении новых penalties  
Mitigation: feature flags + A/B по весам

Риск: рост O(N^2) стоимости  
Mitigation: candidate pre-filter + кэш/precompute

Риск: шумная сегментация  
Mitigation: пост-объединение секций + min duration + confidence thresholds

## 8) Резюме

Проект технически готов к эволюции без переписывания с нуля: extraction слой зрелый, ORM и API достаточные.  
Главная инженерная задача — убрать архитектурное расхождение скореров и провести данные (key_edges, sections, feedback) через единый production scoring pipeline.
