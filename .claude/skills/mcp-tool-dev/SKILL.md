---
name: MCP Tool Development
description: Гайд по разработке новых DJ Workflow MCP-инструментов в app/mcp/tools/. Используй когда: добавляется новый MCP tool, нужно зарегистрировать инструмент в gateway, создать Pydantic-тип для structured_content, написать тесты для MCP tool. Триггеры: "новый инструмент", "добавить tool", app/mcp/tools/, FastMCP, register_tools.
---

# MCP Tool Development

## Назначение

Разработка новых DJ Workflow инструментов в `app/mcp/tools/`. Этот скилл описывает реальную структуру, паттерны и ловушки — не теорию, а то, что работает.

---

## Точка входа — определи по контексту

| Задача | С чего начать |
|--------|---------------|
| Новый read-only инструмент (анализ, статистика) | → `app/mcp/tools/features.py` или `search.py` как образец |
| Инструмент с долгой операцией (>5 сек) | → `app/mcp/tools/delivery.py` — образец visible-stages |
| Новый CRUD (создать/обновить/удалить) | → `app/mcp/tools/set.py` или `track.py` |
| Инструмент с YM API | → `app/mcp/tools/sync.py` + `app/clients/yandex_music.py` |
| Внешний вызов через elicitation | → `app/mcp/elicitation.py` |

---

## Структура нового инструмента

```python
# app/mcp/tools/mymodule.py

from __future__ import annotations
from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.dependencies import Depends
from app.mcp.dependencies import get_track_service
from app.mcp.types import TrackDetails  # или создай новый Pydantic-тип в types/

def register_my_tools(mcp: FastMCP) -> None:

    @mcp.tool(annotations={"readOnlyHint": True}, tags={"analysis"})
    async def my_tool(
        track_id: int,              # видно в MCP-клиенте
        ctx: Context,               # инжектится FastMCP, НИКОГДА не делай ctx: Context = None
        svc: TrackService = Depends(get_track_service),  # инжектится, скрыто от клиента
    ) -> TrackDetails:              # Pydantic-тип → structured_content
        await ctx.info("Processing...")
        track = await svc.get(track_id)
        if not track:
            raise ValueError(f"Track {track_id} not found")
        return TrackDetails(...)
```

---

## DI провайдеры (`app/mcp/dependencies.py`)

8 провайдеров, все готовы к использованию:

| Depends | Возвращает |
|---------|-----------|
| `get_session` | `AsyncSession` |
| `get_track_service` | `TrackService` |
| `get_playlist_service` | `PlaylistService` |
| `get_features_service` | `FeaturesService` |
| `get_analysis_service` | `AnalysisOrchestrator` |
| `get_set_service` | `DjSetService` |
| `get_set_generation_service` | `SetGenerationService` |
| `get_transition_service` | `TransitionScoringService` |
| `get_ym_client` | `YandexMusicClient` |

---

## Регистрация нового модуля

1. Создай функцию `register_my_tools(mcp: FastMCP) -> None:` в `app/mcp/tools/mymodule.py`
2. Добавь импорт в `app/mcp/tools/server.py`:
   ```python
   from app.mcp.tools.mymodule import register_my_tools
   # в create_workflow_mcp():
   register_my_tools(mcp)
   ```
3. **Ruff B008**: `Depends()` в аргументах по умолчанию → добавь в `pyproject.toml`:
   ```toml
   [tool.ruff.lint.per-file-ignores]
   "app/mcp/tools/mymodule.py" = ["B008"]
   ```

---

## Типы возврата (`app/mcp/types/`)

Все инструменты возвращают Pydantic-модели. FastMCP кладёт поля НАПРЯМУЮ в `structured_content`:

```python
# structured_content["set_id"] ← правильно
# structured_content["result"]["set_id"] ← неправильно!
```

Текущие типы: `PlaylistStatus`, `TrackDetails`, `ImportResult`, `AnalysisResult`, `SimilarTracksResult`, `SearchStrategy`, `SetBuildResult`, `TransitionScoreResult`, `ExportResult`, `DeliveryResult`.

Создавай новый тип в `app/mcp/types/workflows.py` или `app/mcp/types/analysis.py`.

---

## Visible-stages паттерн (для операций > 5 сек)

```python
@mcp.tool(tags={"setbuilder"}, timeout=300)
async def long_operation(ctx: Context, ...) -> ResultModel:
    # Stage 1: быстро, обратимо
    await ctx.info("Stage 1/3 — проверка...")
    await ctx.report_progress(progress=0, total=3)
    result = await check_something()

    if result.has_problem:
        from app.mcp.elicitation import resolve_conflict
        decision = await resolve_conflict(ctx, "Продолжить?", options=["continue", "abort"])
        if decision != "continue":
            return ResultModel(status="aborted", ...)

    # Stage 2: мутация (необратимо)
    await ctx.info("Stage 2/3 — запись файлов...")
    await ctx.report_progress(progress=1, total=3)
    await write_files(...)

    # Stage 3: опциональный внешний сервис
    await ctx.info("Stage 3/3 — синхронизация...")
    await ctx.report_progress(progress=2, total=3)
    await sync_to_ym(...)

    await ctx.report_progress(progress=3, total=3)
    return ResultModel(status="ok", ...)
```

---

## Tags и видимость

| Tag | Видимость | Назначение |
|-----|-----------|------------|
| `analysis` | По умолчанию | read-only анализ |
| `discovery` | По умолчанию | Поиск похожих |
| `setbuilder` | По умолчанию | Построение сетов |
| `sync`, `yandex` | По умолчанию | YM синхронизация |
| `import`, `download` | По умолчанию | Импорт треков |
| `curation` | По умолчанию | Курирование |
| `admin` | По умолчанию | Управление |
| `heavy` | **Скрыт** | Тяжёлые вычисления (активация через `activate_heavy_mode`) |

---

## Тестирование нового инструмента

### Минимальный набор (для каждого нового инструмента)

```python
# tests/mcp/test_workflow_mymodule.py

async def test_my_tool_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    assert "my_tool" in {t.name for t in tools}

async def test_my_tool_has_correct_tags(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "my_tool")
    assert "analysis" in tool.tags

async def test_gateway_has_dj_my_tool(gateway_mcp: FastMCP):
    tools = await gateway_mcp.list_tools()
    assert "dj_my_tool" in {t.name for t in tools}
```

### Интеграционный тест (с DB)

```python
async def test_my_tool_with_db(workflow_mcp_with_db: FastMCP, engine):
    # Сидируй через engine, НЕ через session_factory!
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        track = Track(title="Test", duration_ms=300_000, status=0)
        session.add(track)
        await session.commit()

    async with Client(workflow_mcp_with_db) as client:
        raw = await client.call_tool("my_tool", {"track_id": track.track_id})

    sc = raw.structured_content
    assert sc["track_id"] == track.track_id
    assert not raw.is_error
```

---

## Частые ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `ctx: Context = None` | FastMCP не принимает опциональный ctx | Всегда `ctx: Context` без дефолта |
| `f"#EXTM3U"` → ruff warning | f-string без интерполяции | Убрать `f` префикс |
| `keys = [t.get("key") for t in tracks]` → mypy `list[Any \| None]` | `.get()` возвращает `None` | Walrus: `[k for t in tracks if (k := t.get("key")) is not None]` |
| `session_factory()` в тестах | Сидирует в реальную базу, а не тестовую | `async_sessionmaker(engine)` |
| `sc["result"]["field"]` в тестах | FastMCP не оборачивает в `result` | `sc["field"]` напрямую |
| B008 ruff | `Depends()` в дефолтных аргументах | Добавь per-file-ignores в pyproject.toml |

---

## Быстрое тестирование через CLI (без перезапуска сервера)

```bash
make mcp-call TOOL=dj_my_tool ARGS='{"track_id": 42}'
# Первая строка — echo команды make, JSON со второй строки
make mcp-call TOOL=dj_my_tool ARGS='{"track_id": 42}' | sed '1d' | jq .
```

---

## Чеклист для PR

- [ ] Инструмент зарегистрирован в `server.py`
- [ ] `ctx: Context` без дефолтного значения
- [ ] Возвращает Pydantic-модель (не dict)
- [ ] `readOnlyHint: True` для read-only инструментов
- [ ] B008 добавлен в per-file-ignores если используется Depends
- [ ] Тесты: регистрация + тег + gateway namespacing
- [ ] Тест: интеграционный (если инструмент работает с DB)
- [ ] `make check` прошёл (ruff + mypy + pytest)
