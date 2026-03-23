---
name: mcp-tool-dev
description: Use when adding a new MCP tool, registering tools in gateway, creating Pydantic types for structured_content, or writing MCP tool tests. Triggers on app/mcp/tools/, FastMCP, register_tools, "new tool", "add instrument".
---

# MCP Tool Development

Разработка DJ Workflow инструментов в `app/mcp/tools/`. Паттерны и ловушки.

## Точка входа

| Задача | Образец |
|--------|---------|
| Read-only инструмент | `features.py`, `search.py` |
| Долгая операция (>5 сек) | `delivery.py` (visible-stages) |
| CRUD | `set.py`, `track.py` |
| YM API | `sync.py` + `app/services/yandex_music_client.py` |

## Структура нового инструмента

```python
# app/mcp/tools/mymodule.py
from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.dependencies import Depends  # НЕ FastAPI Depends!
from app.mcp.dependencies import get_track_service

def register_my_tools(mcp: FastMCP) -> None:
    @mcp.tool(annotations={"readOnlyHint": True}, tags={"analysis"})
    async def my_tool(
        track_id: int,
        ctx: Context,  # НИКОГДА ctx: Context = None
        svc: TrackService = Depends(get_track_service),
    ) -> MyResultType:
        ...
```

## Регистрация

1. `register_my_tools(mcp)` в `app/mcp/tools/server.py`
2. Pydantic return type в `app/mcp/types/` → `structured_content`
3. B008 per-file-ignore в `pyproject.toml`

## DI провайдеры (9 шт)

`get_session`, `get_track_service`, `get_playlist_service`, `get_features_service`, `get_analysis_service`, `get_set_service`, `get_set_generation_service`, `get_transition_service`, `get_ym_client`.

## Тестирование

```python
# Метаданные (без DB)
async def test_registered(workflow_mcp):
    tools = await workflow_mcp.list_tools()
    assert "my_tool" in {t.name for t in tools}

# Интеграция (с DB) — сидируй через engine!
async def test_with_db(workflow_mcp_with_db, engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # ... seed data ...
    async with Client(workflow_mcp_with_db) as client:
        raw = await client.call_tool("my_tool", {...})
    assert raw.structured_content["field"] == expected  # НЕ sc["result"]["field"]
```

## Частые ошибки

| Ошибка | Решение |
|--------|---------|
| `ctx: Context = None` | Всегда `ctx: Context` без дефолта |
| `sc["result"]["field"]` | `sc["field"]` напрямую |
| `session_factory()` в тестах | `async_sessionmaker(engine)` |

## Чеклист PR

- [ ] Зарегистрирован в `server.py`
- [ ] `readOnlyHint: True` для read-only
- [ ] Возвращает Pydantic-модель
- [ ] B008 в per-file-ignores
- [ ] Тесты: регистрация + gateway namespacing
- [ ] `make check` прошёл

Подробности: `.claude/rules/mcp.md`.

---

## Iron Law

```text
NO TOOL REGISTRATION WITHOUT PYDANTIC RETURN TYPE AND TEST
```

Инструмент без Pydantic return type не генерирует `structured_content`. Инструмент без теста ломается молча при gateway namespacing.

## Red Flags

| Отговорка | Реальность |
|-----------|------------|
| "Верну просто строку" | `structured_content` требует Pydantic модель — строка = raw text, не structured |
| "ctx: Context = None подойдёт" | FastMCP инъектирует ctx автоматически — дефолт None сломает инъекцию |
| "sc['result']['field']" | FastMCP кладёт поля напрямую в `structured_content`, НЕ в `result` обёртку |
| "Тест потом напишу" | Gateway namespacing (`dj_` prefix) не проверится без теста |
| "Возьму FastAPI Depends" | MCP использует `fastmcp.dependencies.Depends` — другой Depends! |
