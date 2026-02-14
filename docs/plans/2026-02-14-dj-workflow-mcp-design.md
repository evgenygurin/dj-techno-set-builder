# DJ Workflow MCP Server — Design Document

## Goal

Создать высокоуровневый MCP-сервер с "умными" workflow-инструментами, которые
используют `ctx.sample()` (LLM внутри инструмента), `ctx.elicit()` (запрос к
пользователю), Background Tasks и Dependency Injection для надёжной оркестрации
сложных DJ-сценариев через Claude Desktop.

## Проблема

У нас есть:
- 30 MCP-инструментов Yandex Music (сырой API)
- 60+ REST-эндпоинтов FastAPI (треки, анализ, переходы, сеты, плейлисты)
- 23 сервиса с бизнес-логикой

AI-агент не может надёжно оркестрировать 90+ инструментов в правильной
последовательности. Шаги взаимозависимы, агент пропускает шаги, не видит контекст.

## Решение

**Гибридная оркестрация**: сервер координирует подпроцессы внутри каждого
инструмента (sampling, elicitation, progress), а AI координирует между
инструментами с помощью MCP Prompts.

## Ключевые фичи FastMCP 3.0

| Фича | Применение |
|------|-----------|
| `ctx.sample()` | Инструмент вызывает LLM для принятия решений mid-workflow |
| `ctx.elicit()` | Спрашивает пользователя (выбрать треки, подтвердить) |
| `task=True` | Background Tasks — долгие операции не блокируют |
| `Depends()` | DI — инжекция DB session, сервисов в MCP-инструменты |
| `ctx.set_state()` | Состояние сессии между вызовами |
| `ctx.report_progress()` | Прогресс для пользователя |
| MCP Prompts | Рецепты с аргументами ("expand_playlist") |
| MCP Resources | Динамические данные (playlist status, catalog stats) |
| `mount()` + namespace | Объединение серверов |
| Visibility (per-session) | Скрытие тяжёлых инструментов до активации |
| PromptsAsTools | Совместимость с tool-only клиентами |
| ResourcesAsTools | Совместимость с tool-only клиентами |
| Tool Transformation | Переименование/скрытие аргументов |

## Архитектура

### Файловая структура

```text
app/mcp/
├── __init__.py
├── gateway.py                 # create_dj_mcp() — gateway, mount + transforms
├── dependencies.py            # DI: get_session, get_services, get_ym_client
├── types.py                   # Pydantic модели для structured output
│
├── yandex_music/              # (существует) OpenAPI → MCP
│   ├── __init__.py
│   ├── config.py
│   └── server.py
│
├── workflows/                 # Высокоуровневые DJ-инструменты
│   ├── __init__.py
│   ├── server.py              # FastMCP("DJ Workflows") + регистрация
│   ├── import_tools.py        # import_playlist, import_tracks
│   ├── analysis_tools.py      # analyze_playlist, get_playlist_status, get_track_details
│   ├── discovery_tools.py     # find_similar_tracks, search_by_criteria
│   ├── setbuilder_tools.py    # build_set, score_transitions, adjust_set
│   └── export_tools.py        # export_set_m3u, export_set_json
│
├── prompts/                   # MCP Prompts — рецепты
│   ├── __init__.py
│   └── workflows.py           # expand_playlist, build_set_from_scratch, improve_set
│
└── resources/                 # MCP Resources — состояние
    ├── __init__.py
    └── status.py              # playlist://{id}/status, catalog://stats, set://{id}/summary
```

### Gateway — точка входа

```python
# app/mcp/gateway.py
from fastmcp import FastMCP
from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools

def create_dj_mcp() -> FastMCP:
    gateway = FastMCP("DJ Set Builder")

    # Yandex Music — 30 инструментов с namespace "ym"
    ym = create_yandex_music_mcp()
    gateway.mount(ym, namespace="ym")

    # DJ Workflows — 12 инструментов с namespace "dj"
    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    # Transforms для tool-only клиентов
    gateway.add_transform(PromptsAsTools(gateway))
    gateway.add_transform(ResourcesAsTools(gateway))

    return gateway
```

### Монтирование в FastAPI

```python
# app/main.py — обновление
mcp = create_dj_mcp()           # gateway вместо yandex_music_mcp
mcp_app = mcp.http_app(path="/mcp")
app = FastAPI(lifespan=combine_lifespans(lifespan, mcp_app.lifespan))
app.mount("/mcp", mcp_app)
```

### Клиент видит

```text
Claude Desktop / Claude Code
  └── MCP: DJ Set Builder
       ├── ym_search_yandex_music         # Yandex Music (30 tools)
       ├── ym_get_tracks
       ├── ym_get_genres
       ├── ...
       ├── dj_import_playlist             # DJ Workflows (12 tools)
       ├── dj_analyze_playlist
       ├── dj_find_similar_tracks
       ├── dj_build_set
       ├── dj_score_transitions
       ├── dj_adjust_set
       ├── dj_export_set_m3u
       ├── ...
       ├── dj_expand_playlist (prompt)    # MCP Prompts (3)
       ├── dj_build_set_from_scratch
       ├── dj_improve_set
       ├── playlist://{id}/status         # MCP Resources (3)
       ├── catalog://stats
       └── set://{id}/summary
```

## Workflow Tools — 12 инструментов

### Import (2)

| Tool | Описание | Фичи |
|------|----------|------|
| `import_playlist(source, playlist_id)` | Импорт плейлиста из YM → создание треков в БД → enrichment | `task=True`, `progress` |
| `import_tracks(track_ids: list[int])` | Импорт конкретных треков по Yandex Music ID | `task=True` |

### Analysis (3)

| Tool | Описание | Фичи |
|------|----------|------|
| `analyze_playlist(playlist_id)` | Полный анализ всех непроанализированных треков | `task=True`, `progress`, `tags={"heavy"}` |
| `get_playlist_status(playlist_id)` | Статистика: треки, анализ, BPM, тональности, энергия | `readOnlyHint=True` |
| `get_track_details(track_id)` | Полные данные трека + audio features + секции | `readOnlyHint=True` |

### Discovery (2)

| Tool | Описание | Фичи |
|------|----------|------|
| `find_similar_tracks(playlist_id, count, criteria)` | LLM-стратегия поиска → YM search → scoring → elicitation выбора | `task=True`, `sample`, `elicit` |
| `search_by_criteria(bpm_range, keys, energy, genre)` | Ручной поиск по конкретным критериям | — |

### Set Building (3)

| Tool | Описание | Фичи |
|------|----------|------|
| `build_set(playlist_id, config)` | GA-оптимизация порядка треков | `task=True`, `sample` |
| `score_transitions(set_id)` | 5-компонентная оценка всех переходов | `task=True`, `readOnlyHint=True` |
| `adjust_set(set_id, instructions)` | LLM анализирует + предлагает перестановки → elicitation подтверждения | `sample`, `elicit` |

### Export (2)

| Tool | Описание | Фичи |
|------|----------|------|
| `export_set_m3u(set_id)` | M3U файл с порядком треков | — |
| `export_set_json(set_id)` | JSON: треки, переходы, оценки, энерг. кривая | — |

## MCP Prompts — 3 рецепта

### expand_playlist(playlist_name, count, style)

Рецепт: get_status → analyze (если нужно) → find_similar → build_set → show result.

### build_set_from_scratch(genre, duration_minutes, energy_arc)

Рецепт: ym_search → import_tracks → analyze → find_similar (если мало) → build_set.

### improve_set(set_id, feedback)

Рецепт: score_transitions → get_status → adjust_set → show comparison.

## MCP Resources — 3 ресурса

| URI | Описание |
|-----|----------|
| `playlist://{playlist_id}/status` | Треки, анализ, BPM range, тональности, энергия |
| `catalog://stats` | Общая статистика: кол-во треков, проанализированных, сетов |
| `set://{set_id}/summary` | Порядок треков, оценки переходов, энерг. кривая |

## Dependency Injection

MCP-инструменты получают DB session и сервисы через FastMCP `Depends()`:

```python
@asynccontextmanager
async def get_session():
    async with session_factory() as session:
        yield session

def get_track_service(session=Depends(get_session)):
    return TrackService(TrackRepository(session))

def get_analysis_service(session=Depends(get_session)):
    return TrackAnalysisService(
        TrackRepository(session),
        AudioFeaturesRepository(session),
        SectionsRepository(session),
    )
```

Зависимости кэшируются per-request: один `get_session` — одна сессия для всех
сервисов в рамках одного вызова инструмента.

## Visibility — управление доступом

- Тяжёлые инструменты (`tags={"heavy"}`) скрыты по умолчанию
- `activate_heavy_mode()` включает их для текущей сессии через `ctx.enable_components()`
- Клиент автоматически получает notification об изменении списка инструментов

## Structured Output

Все инструменты возвращают типизированные Pydantic-модели:

```python
class PlaylistStatus(BaseModel):
    playlist_id: int
    name: str
    total_tracks: int
    analyzed_tracks: int
    bpm_range: tuple[float, float] | None
    keys: list[str]
    avg_energy: float | None
    duration_minutes: float

class SimilarTracksResult(BaseModel):
    added_count: int
    playlist_id: int
    candidates_found: int
    candidates_selected: int

class SetBuildResult(BaseModel):
    set_id: int
    track_order: list[int]
    total_score: float
    transition_scores: list[float]
    energy_curve: list[float]

class SearchStrategy(BaseModel):
    """Результат ctx.sample() — LLM формирует стратегию поиска."""
    queries: list[str]
    target_bpm_range: tuple[float, float]
    target_keys: list[str]
    target_energy_range: tuple[float, float]
    reasoning: str
```

## Клиент: Claude Desktop

```json
{
  "mcpServers": {
    "dj-set-builder": {
      "command": "uv",
      "args": ["run", "uvicorn", "app.main:app", "--port", "8000"],
      "cwd": "/path/to/dj-techno-set-builder"
    }
  }
}
```

Или через HTTP transport:

```json
{
  "mcpServers": {
    "dj-set-builder": {
      "transport": "streamable-http",
      "url": "http://localhost:8000/mcp/mcp"
    }
  }
}
```

## Пример пользовательского сценария

> "Возьми мой плейлист 'Techno Dark' из Яндекс.Музыки, проанализируй все треки,
> найди ещё 20 похожих с тем же BPM и настроением, и собери DJ-сет с классической
> энергетической кривой."

Claude Desktop выбирает промпт `expand_playlist` или самостоятельно:

1. `dj_import_playlist(source="yandex", playlist_id=1234)` — импорт + enrichment
2. `dj_analyze_playlist(playlist_id=42)` — полный аудио-анализ (background task)
3. `dj_find_similar_tracks(playlist_id=42, count=20, criteria="dark techno mood")`
   - Внутри: `ctx.sample()` → стратегия поиска
   - Внутри: поиск в YM, scoring кандидатов
   - Внутри: `ctx.elicit()` → пользователь выбирает 20 из 40
4. `dj_analyze_playlist(playlist_id=42)` — анализ новых треков
5. `dj_build_set(playlist_id=42, config={"energy_arc": "classic"})` — GA оптимизация

Каждый шаг самодостаточен. Если Claude пропустит шаг — инструмент вернёт ошибку
с подсказкой ("tracks not analyzed, call analyze_playlist first").

## Зависимости

```toml
# pyproject.toml — новые зависимости
fastmcp[tasks] >= 3.0.0rc1   # Background Tasks (docket)
```

## Совместимость

- Существующий REST API не затрагивается
- Существующий Yandex Music MCP монтируется в gateway
- `app/clients/yandex_music.py` остаётся для REST-сервисов
- Все 300+ тестов продолжают работать
