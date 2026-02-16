# DJ Techno Set Builder — План реализации (готовность к коду)

Дата: 2026-02-15  
Назначение: практический backlog для начала разработки сразу после ревью

## 1) Цель этапа

Перевести проект из режима “богатые данные, частичное использование” в режим:

- единый scoring engine,
- section-aware transition logic,
- заполнение transition/mix metadata в БД,
- feedback loop для калибровки.

## 2) Milestones

## M1 — Консолидация скоринга (1-2 дня)

- [ ] Передать DB session в `CamelotLookupService` там, где строится transition matrix.
- [ ] Убрать divergence двух скореров (выбрать единый вычислительный путь).
- [ ] Добавить тесты консистентности GA/API/MCP scoring.

Done-criteria:

- одинаковые входные пары дают одинаковые компонентные/итоговые скоры во всех entry points.

## M2 — Transition persistence в production потоке (2-3 дня)

- [ ] Реализовать массовый precompute кандидатов и full transitions.
- [ ] Писать `transition_runs` и статусы выполнения.
- [ ] Добавить индексы/ограничения для устойчивого batch режима.

Done-criteria:

- `transition_candidates` и `transitions` заполняются для latest features без ручных вызовов `/compute`.

## M3 — Section-aware set generation (3-5 дней)

- [ ] Включить `track_sections` в выбор перехода.
- [ ] Заполнять `dj_set_items.mix_in_ms`, `mix_out_ms`, `transition_id`, section refs.
- [ ] Добавить heuristics phrase-safe окон.

Done-criteria:

- для новой версии сета >80% элементов имеют валидные `mix_in/out` и привязанный transition.

## M4 — Feedback loop (2-3 дня)

- [ ] CRUD для `dj_set_feedback`.
- [ ] Базовый offline recalibration job весов компонентов.
- [ ] Отчет по качеству до/после калибровки.

Done-criteria:

- весовые коэффициенты могут быть переоценены на реальных оценках без ручного редактирования кода.

## 3) Инженерные задачи по файлам

## Core services

- `app/services/set_generation.py`
- `app/services/transition_persistence.py`
- `app/services/transition_scoring.py`
- `app/services/camelot_lookup.py`

## API/routers

- `app/routers/v1/transitions.py`
- новые роутеры для feedback (или расширение `sets.py`)

## MCP

- `app/mcp/workflows/setbuilder_tools.py`
- при необходимости `analysis_tools.py` / `export_tools.py` для section/mix метаданных

## Data layer

- `app/models/sets.py` (поля уже есть)
- при необходимости новая таблица precompute score cache

## 4) Набор метрик релиз-контроля

Перед merge каждого milestone:

1. Correctness
- unit/integration tests зеленые

2. Quality
- harmonic-compatible transitions доля не падает
- median BPM jump и LUFS jump не ухудшаются

3. Coverage
- доля set items с `mix_in/out` растет по целевому порогу

4. Performance
- время генерации сета на 100-150 треков в SLA

## 5) Риски запуска

- Низкая дискриминативность части признаков (`pulse_clarity` близок к константе).
- Пересегментация секций.
- Удорожание O(N^2) precompute.

## Mitigation

- robust scaling/клиппинг признаков,
- merge-short-sections,
- candidate pre-filter + батчевые джобы.

## 6) Definition of Ready для начала кодинга

Считаем задачу готовой к реализации, если:

1. Зафиксирован единый scoring engine.
2. Выбран формат section-aware переходов (что пишем в `dj_set_items`).
3. Утверждены KPI релиза (harmonic continuity, BPM/LUFS smoothness, mix metadata coverage).
4. Определен порядок milestones M1 -> M4.

На момент подготовки этого документа все 4 пункта могут быть взяты в работу без дополнительных исследований данных.
