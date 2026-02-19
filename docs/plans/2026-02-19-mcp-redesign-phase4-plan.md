# MCP Redesign Phase 4 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Переключить MCP gateway на новую архитектуру (`tools/` вместо `workflows/`), удалить все legacy-модули (`workflows/`, `types.py`, `types_curation.py`), обновить тесты и skill-ссылки — завершить миграцию на agent-first MCP.

**Architecture:** Phase 4 — чистый cleanup. Все новые инструменты уже созданы в Phases 1–3 (`app/mcp/tools/`, `app/mcp/platforms/`). Phase 4 переключает gateway, удаляет старый код, обновляет тесты и документацию. Ни одного нового инструмента.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest + pytest-asyncio

**Phase 0+1 delivers:** `schemas.py`, `refs.py`, `resolvers.py`, `converters.py`, `pagination.py`, `stats.py`, `platforms/keys.py`
**Phase 2 delivers:** `envelope.py`, `tools/tracks.py`, `tools/playlists.py`, `tools/sets.py`, `tools/features.py`, `tools/scoring.py`, `tools/export.py`, `tools/download.py`, `tools/discovery.py`, `tools/curation.py`, `tools/server.py` (`create_tools_mcp()`)
**Phase 3 delivers:** `platforms/protocol.py`, `platforms/registry.py`, `platforms/sync_engine.py`, `platforms/track_mapper.py`, `yandex_music/adapter.py`, `tools/sync.py`

**Критичное из ревью (все 9 блокеров учтены):**
1. Sync module location ambiguity → Phase 3 кладёт sync в `tools/sync.py`, Phase 4 безопасно удаляет `workflows/sync_tools.py` (blocker #1) ✅
2. Тест-файлы, которые не существуют → добавлен Task 4 для обновления ВСЕХ тестовых ожиданий (blocker #2) ✅
3. "No new modules" contradiction → Phase 4 допускает перенос visibility tools и переименования (blocker #3) ✅
4. Неправильные тест-паттерны → все тесты через `Client.call_tool()` + `result.data` (blocker #4) ✅
5. Export unification → Phase 2 создаёт `export_set(format=...)`, Phase 4 удаляет дубликаты из `setbuilder_tools.py` (blocker #5) ✅
6. Потеря aggregate stats → Phase 2 `get_playlist` включает агрегаты через envelope (blocker #6) ✅
7. Mutable defaults → `Field(default_factory=list)` для list-полей в schemas (blocker #7) ✅
8. N+1 ref resolution → Phase 2 уже включает batch resolution в resolvers (blocker #8) ✅
9. ValueError vs project errors → `raise ToolError(msg)` вместо `ValueError` (blocker #9) ✅

---

## Что удаляется / что остаётся

### Файлы для УДАЛЕНИЯ

| Файл | Причина | Заменён чем |
|------|---------|-------------|
| `app/mcp/workflows/analysis_tools.py` | `get_playlist_status`, `get_track_details` | Phase 2: `tools/tracks.py`, `tools/playlists.py` |
| `app/mcp/workflows/sync_tools.py` | 3 стаба | Phase 3: `tools/sync.py` |
| `app/mcp/workflows/import_tools.py` | 2 стаба + `download_tracks` | Phase 2: `tools/download.py` |
| `app/mcp/workflows/discovery_tools.py` | `search_by_criteria` + `find_similar_tracks` | Phase 1: `tools/search.py`, Phase 2: `tools/discovery.py` |
| `app/mcp/workflows/setbuilder_tools.py` | `build_set`, `rebuild_set`, `score_transitions`, export дубли | Phase 2: `tools/sets.py`, `tools/scoring.py`, `tools/export.py` |
| `app/mcp/workflows/export_tools.py` | 3 export tools | Phase 2: `tools/export.py` (unified) |
| `app/mcp/workflows/curation_tools.py` | `classify_tracks`, `analyze_library_gaps`, `review_set` | Phase 2: `tools/curation.py` |
| `app/mcp/workflows/server.py` | `create_workflow_mcp()` factory | Phase 2: `tools/server.py` (`create_tools_mcp()`) |
| `app/mcp/workflows/__init__.py` | Package init | Не нужен |
| `app/mcp/types.py` | 13 legacy моделей | Phase 0+1: `schemas.py` |
| `app/mcp/types_curation.py` | 8 моделей (2 мёртвые) | Phase 0+1: `schemas.py` |
| `tests/mcp/test_workflow_analysis.py` | Тесты для удалённых tools | Phase 2: `tests/mcp/tools/test_tracks.py`, `test_playlists.py` |
| `tests/mcp/test_workflow_sync.py` | Тесты для стабов | Phase 3: `tests/mcp/tools/test_sync.py` |
| `tests/mcp/test_workflow_import.py` | Тесты для стабов | Phase 2: `tests/mcp/tools/test_download.py` |
| `tests/mcp/test_import_playlist.py` | Тесты для стаба | Phase 2: `tools/test_download.py` |
| `tests/mcp/test_workflow_discovery.py` | Тесты для `search_by_criteria` | Phase 2: `tests/mcp/tools/test_discovery.py` |
| `tests/mcp/test_workflow_setbuilder.py` | Тесты для дублей | Phase 2: `tests/mcp/tools/test_sets.py`, `test_scoring.py` |
| `tests/mcp/test_workflow_export.py` | Тесты для 3 exports | Phase 2: `tests/mcp/tools/test_export.py` |
| `tests/mcp/test_workflow_curation.py` | Тесты для curation | Phase 2: `tests/mcp/tools/test_curation.py` |

### Файлы для МОДИФИКАЦИИ

| Файл | Что меняется |
|------|-------------|
| `app/mcp/gateway.py` | `create_workflow_mcp()` → `create_tools_mcp()` |
| `tests/mcp/test_client_integration.py` | Обновить ожидаемый список инструментов |
| `tests/mcp/test_progress.py` | Убрать `import_playlist`, `import_tracks` |
| `tests/mcp/test_visibility.py` | Обновить tool names (`dj_get_playlist_status` → `dj_get_playlist`) |
| `tests/mcp/test_skills.py` | Обновить skill text references |
| `app/mcp/skills/*/SKILL.md` | Обновить ссылки на инструменты |

---

## Task 1: Preflight audit — проверить существование Phases 1–3 модулей

**Files:**
- No changes — verification only

Перед удалением legacy кода убеждаемся, что все заменяющие модули из Phases 1–3 существуют.

**Step 1: Проверить Phase 0+1 модули**

```bash
test -f app/mcp/schemas.py && echo "OK: schemas.py" || echo "MISSING: schemas.py"
test -f app/mcp/refs.py && echo "OK: refs.py" || echo "MISSING: refs.py"
test -f app/mcp/resolvers.py && echo "OK: resolvers.py" || echo "MISSING: resolvers.py"
test -f app/mcp/converters.py && echo "OK: converters.py" || echo "MISSING: converters.py"
test -f app/mcp/pagination.py && echo "OK: pagination.py" || echo "MISSING: pagination.py"
test -f app/mcp/stats.py && echo "OK: stats.py" || echo "MISSING: stats.py"
test -f app/mcp/platforms/keys.py && echo "OK: platforms/keys.py" || echo "MISSING: platforms/keys.py"
```

Expected: Все OK.

**Step 2: Проверить Phase 2 модули**

```bash
test -f app/mcp/envelope.py && echo "OK: envelope.py" || echo "MISSING: envelope.py"
test -f app/mcp/tools/__init__.py && echo "OK: tools/__init__.py" || echo "MISSING: tools/__init__.py"
test -f app/mcp/tools/server.py && echo "OK: tools/server.py" || echo "MISSING: tools/server.py"
test -f app/mcp/tools/tracks.py && echo "OK: tools/tracks.py" || echo "MISSING: tools/tracks.py"
test -f app/mcp/tools/playlists.py && echo "OK: tools/playlists.py" || echo "MISSING: tools/playlists.py"
test -f app/mcp/tools/sets.py && echo "OK: tools/sets.py" || echo "MISSING: tools/sets.py"
test -f app/mcp/tools/features.py && echo "OK: tools/features.py" || echo "MISSING: tools/features.py"
test -f app/mcp/tools/scoring.py && echo "OK: tools/scoring.py" || echo "MISSING: tools/scoring.py"
test -f app/mcp/tools/export.py && echo "OK: tools/export.py" || echo "MISSING: tools/export.py"
test -f app/mcp/tools/download.py && echo "OK: tools/download.py" || echo "MISSING: tools/download.py"
test -f app/mcp/tools/discovery.py && echo "OK: tools/discovery.py" || echo "MISSING: tools/discovery.py"
test -f app/mcp/tools/curation.py && echo "OK: tools/curation.py" || echo "MISSING: tools/curation.py"
test -f app/mcp/tools/search.py && echo "OK: tools/search.py" || echo "MISSING: tools/search.py"
```

Expected: Все OK.

**Step 3: Проверить Phase 3 модули**

```bash
test -f app/mcp/platforms/protocol.py && echo "OK: platforms/protocol.py" || echo "MISSING"
test -f app/mcp/platforms/registry.py && echo "OK: platforms/registry.py" || echo "MISSING"
test -f app/mcp/platforms/sync_engine.py && echo "OK: platforms/sync_engine.py" || echo "MISSING"
test -f app/mcp/platforms/sync_diff.py && echo "OK: platforms/sync_diff.py" || echo "MISSING"
test -f app/mcp/platforms/track_mapper.py && echo "OK: platforms/track_mapper.py" || echo "MISSING"
test -f app/mcp/yandex_music/adapter.py && echo "OK: yandex_music/adapter.py" || echo "MISSING"
test -f app/mcp/tools/sync.py && echo "OK: tools/sync.py" || echo "MISSING"
```

Expected: Все OK.

**Step 4: Проверить Phase 2 тесты**

```bash
test -f tests/mcp/tools/test_tracks.py && echo "OK" || echo "MISSING: tests/mcp/tools/test_tracks.py"
test -f tests/mcp/tools/test_playlists.py && echo "OK" || echo "MISSING: tests/mcp/tools/test_playlists.py"
test -f tests/mcp/tools/test_sets.py && echo "OK" || echo "MISSING: tests/mcp/tools/test_sets.py"
test -f tests/mcp/tools/test_export.py && echo "OK" || echo "MISSING: tests/mcp/tools/test_export.py"
test -f tests/mcp/tools/test_sync.py && echo "OK" || echo "MISSING: tests/mcp/tools/test_sync.py"
```

Expected: Все OK.

**Step 5: Запустить все Phase 2–3 тесты**

```bash
uv run pytest tests/mcp/tools/ tests/mcp/platforms/ -v --tb=short
```

Expected: Все тесты проходят. Если нет — **СТОП, сначала исправить Phase 2–3 перед Phase 4**.

**Step 6: Commit — нет, это verification only**

Не коммитим, переходим к Task 2.

---

## Task 2: Переключить gateway на `create_tools_mcp()`

**Files:**
- Modify: `app/mcp/gateway.py`
- Test: `tests/mcp/test_gateway_switch.py`

Центральное изменение Phase 4: gateway монтирует `create_tools_mcp()` вместо `create_workflow_mcp()`. После этого шага все запросы идут через новые tools.

**Step 1: Написать failing тест**

```python
# tests/mcp/test_gateway_switch.py
"""Tests for gateway using new tools/ server instead of workflows/."""

from __future__ import annotations

from fastmcp import Client

async def test_gateway_mounts_tools_server():
    """Gateway should mount create_tools_mcp(), not create_workflow_mcp()."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        # Phase 2 CRUD tools должны быть доступны через gateway
        assert "dj_list_tracks" in tool_names, "Missing Phase 2 CRUD tool: list_tracks"
        assert "dj_get_track" in tool_names, "Missing Phase 2 CRUD tool: get_track"
        assert "dj_list_playlists" in tool_names, "Missing Phase 2 CRUD tool: list_playlists"

        # Phase 2 unified export
        assert "dj_export_set" in tool_names, "Missing Phase 2 unified export_set"

        # Phase 3 sync tools
        assert "dj_sync_playlist" in tool_names, "Missing Phase 3 sync_playlist"

        # Legacy tools НЕ должны быть доступны
        assert "dj_get_playlist_status" not in tool_names, "Legacy tool still registered"
        assert "dj_get_track_details" not in tool_names, "Legacy tool still registered"
        assert "dj_import_playlist" not in tool_names, "Legacy stub still registered"
        assert "dj_import_tracks" not in tool_names, "Legacy stub still registered"
        assert "dj_search_by_criteria" not in tool_names, "Legacy tool still registered"

async def test_gateway_ym_tools_still_available():
    """YM tools should still be available via gateway."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        # YM namespace tools (prefixed with ym_)
        ym_tools = [n for n in tool_names if n.startswith("ym_")]
        assert len(ym_tools) > 10, f"Expected >10 YM tools, got {len(ym_tools)}"

async def test_gateway_health_resource_available():
    """Health resource should still work after gateway switch."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        resources = await client.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        # Ресурсы должны быть доступны
        assert len(resource_uris) > 0, "No resources registered"
```

**Step 2: Запустить тест — должен упасть**

```bash
uv run pytest tests/mcp/test_gateway_switch.py -v --tb=short
```

Expected: FAIL — gateway ещё использует `create_workflow_mcp()`, поэтому `dj_list_tracks` отсутствует.

**Step 3: Обновить gateway.py**

Текущий `app/mcp/gateway.py` выглядит примерно так:

```python
from app.mcp.workflows.server import create_workflow_mcp
```

Заменить на:

```python
from app.mcp.tools.server import create_tools_mcp
```

И в `create_dj_mcp()`:

```python
def create_dj_mcp() -> FastMCP:
    """Create the main DJ MCP gateway."""
    gateway = FastMCP("DJ Techno Set Builder")

    # Mount DJ workflow tools (Phase 2 — new architecture)
    tools_mcp = create_tools_mcp()
    gateway.mount("dj", tools_mcp)

    # Mount Yandex Music tools (unchanged)
    ym_mcp = create_yandex_music_mcp()
    gateway.mount("ym", ym_mcp)

    return gateway
```

**Важно:** Убедиться, что `create_tools_mcp()` регистрирует:
- Visibility tools (`activate_heavy_mode`)
- Prompts и Resources из `app/mcp/prompts/` и `app/mcp/resources/`
- Skills из `app/mcp/skills/`

Если `create_tools_mcp()` не регистрирует prompts/resources/skills, добавить их вызов:

```python
# В app/mcp/tools/server.py — в create_tools_mcp():
from app.mcp.prompts import register_prompts
from app.mcp.resources import register_resources

def create_tools_mcp() -> FastMCP:
    mcp = FastMCP("DJ Workflows")
    # ... tool registrations ...
    register_prompts(mcp)
    register_resources(mcp)
    _register_visibility_tools(mcp)
    mcp.disable(tags={"heavy"})
    return mcp
```

**Step 4: Запустить тест — должен пройти**

```bash
uv run pytest tests/mcp/test_gateway_switch.py -v --tb=short
```

Expected: PASS.

**Step 5: Запустить ВСЕ MCP тесты**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: Часть старых тестов может упасть (они тестируют `create_workflow_mcp()`). Это нормально — мы исправим их в Task 4.

**Step 6: Commit**

```bash
git add app/mcp/gateway.py app/mcp/tools/server.py tests/mcp/test_gateway_switch.py
git commit -m "refactor(mcp): switch gateway from workflows/ to tools/

Gateway now mounts create_tools_mcp() instead of create_workflow_mcp().
All Phase 2 CRUD + Phase 3 sync tools are now live.
Legacy tools (stubs, duplicates, analysis) are no longer registered."
```

---

## Task 3: Собрать полный список внешних ссылок на workflows/

**Files:**
- No changes — audit only

Перед удалением нужно точно знать ВСЕ ссылки на `workflows/`, `types.py`, `types_curation.py`.

**Step 1: Найти все импорты workflows**

```bash
rg "from app\.mcp\.workflows" app/ tests/ --type py -l
```

**Step 2: Найти все импорты types.py**

```bash
rg "from app\.mcp\.types import" app/ tests/ --type py -l
```

**Step 3: Найти все импорты types_curation.py**

```bash
rg "from app\.mcp\.types_curation" app/ tests/ --type py -l
```

**Step 4: Найти ссылки в skill файлах**

```bash
rg "get_playlist_status|get_track_details|import_playlist|import_tracks|search_by_criteria" app/mcp/skills/ --type md
```

**Step 5: Найти ссылки в тестах**

```bash
rg "create_workflow_mcp|register_analysis_tools|register_sync_tools|register_import_tools" tests/ --type py -l
```

**Step 6: Записать результат**

Создать чеклист всех файлов, которые нужно обновить/удалить. Использовать этот чеклист в Tasks 4–6.

Не коммитим — переходим к Task 4.

---

## Task 4: Обновить интеграционные тесты

**Files:**
- Modify: `tests/mcp/test_client_integration.py`
- Modify: `tests/mcp/test_progress.py`
- Modify: `tests/mcp/test_visibility.py`
- Modify: `tests/mcp/test_skills.py`
- Modify: `tests/mcp/conftest.py` (если fixture ссылается на workflows)

Это самый критичный task — без обновления тестов удаление workflows/ сломает CI.

**Step 1: Обновить conftest.py**

Если `tests/mcp/conftest.py` содержит fixture `workflow_mcp` или аналогичный, создающий `create_workflow_mcp()`:

```python
# Было:
from app.mcp.workflows.server import create_workflow_mcp

@pytest.fixture
def workflow_mcp():
    return create_workflow_mcp()

# Стало:
from app.mcp.tools.server import create_tools_mcp

@pytest.fixture
def workflow_mcp():
    """MCP server with all DJ tools (Phase 2+ architecture)."""
    return create_tools_mcp()
```

**Важно:** Оставляем имя fixture `workflow_mcp` для минимизации diff. Внутри он теперь вызывает `create_tools_mcp()`.

**Step 2: Обновить test_client_integration.py**

Этот файл содержит hardcoded список инструментов. Обновить его:

```python
# Убрать из ожидаемого списка:
REMOVED_TOOLS = {
    "get_playlist_status",
    "get_track_details",
    "import_playlist",
    "import_tracks",
    "search_by_criteria",
}

# Добавить в ожидаемый список:
ADDED_TOOLS = {
    "list_tracks",
    "get_track",
    "create_track",
    "update_track",
    "delete_track",
    "list_playlists",
    "get_playlist",
    "create_playlist",
    "update_playlist",
    "delete_playlist",
    "list_sets",
    "get_set",
    "create_set",
    "update_set",
    "list_features",
    "get_features",
    "analyze_track",
    "export_set",         # unified, replaces export_set_m3u + export_set_json in setbuilder
    "link_playlist",      # Phase 3
    "set_source_of_truth", # Phase 3
}
```

Конкретное обновление зависит от текущего содержимого файла. Паттерн:

```python
async def test_all_expected_tools_registered():
    """All expected DJ tools should be registered."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        # Проверяем наличие ключевых Phase 2 CRUD tools
        for expected in [
            "dj_list_tracks", "dj_get_track",
            "dj_list_playlists", "dj_get_playlist",
            "dj_list_sets", "dj_get_set",
            "dj_build_set", "dj_rebuild_set",
            "dj_score_transitions", "dj_export_set",
            "dj_download_tracks", "dj_find_similar_tracks",
            "dj_classify_tracks", "dj_analyze_library_gaps",
            "dj_review_set",
            # Phase 3
            "dj_sync_playlist", "dj_link_playlist",
            # Visibility
            "dj_activate_heavy_mode",
        ]:
            assert expected in tool_names, f"Missing expected tool: {expected}"

        # Проверяем отсутствие legacy tools
        for removed in [
            "dj_get_playlist_status", "dj_get_track_details",
            "dj_import_playlist", "dj_import_tracks",
            "dj_search_by_criteria",
        ]:
            assert removed not in tool_names, f"Legacy tool still present: {removed}"
```

**Step 3: Обновить test_progress.py**

Убрать ассерты на `import_playlist` и `import_tracks`:

```python
# Было:
assert "import_playlist" in tool_names
assert "import_tracks" in tool_names

# Стало: удалить эти строки, или заменить на:
assert "download_tracks" in tool_names
```

**Step 4: Обновить test_visibility.py**

Заменить spot-check tool names:

```python
# Было:
assert "dj_get_playlist_status" in tool_names
assert "dj_export_set_m3u" in tool_names

# Стало:
assert "dj_get_playlist" in tool_names
assert "dj_export_set" in tool_names
```

**Step 5: Обновить test_skills.py**

Если тест проверяет текст skill файлов:

```python
# Было:
assert "dj_get_playlist_status" in skill_text

# Стало:
assert "dj_get_playlist" in skill_text
# (или обновить SKILL.md — это Task 6)
```

**Step 6: Запустить обновлённые тесты**

```bash
uv run pytest tests/mcp/test_client_integration.py tests/mcp/test_progress.py tests/mcp/test_visibility.py tests/mcp/test_skills.py -v --tb=short
```

Expected: PASS.

**Step 7: Commit**

```bash
git add tests/mcp/
git commit -m "test(mcp): update integration tests for Phase 4 tool migration

- conftest: workflow_mcp now uses create_tools_mcp()
- test_client_integration: updated expected tool list (add Phase 2-3, remove legacy)
- test_progress: removed import_playlist/import_tracks assertions
- test_visibility: updated tool names (get_playlist_status → get_playlist)
- test_skills: updated skill text references"
```

---

## Task 5: Удалить workflows/ directory

**Files:**
- Delete: `app/mcp/workflows/` (entire directory)
- Delete: `tests/mcp/test_workflow_*.py` (all legacy test files)
- Delete: `tests/mcp/test_import_playlist.py`

**Prerequisite:** Task 4 пройден, все обновлённые тесты проходят.

**Step 1: Проверить, что gateway НЕ импортирует из workflows/**

```bash
rg "from app\.mcp\.workflows" app/mcp/gateway.py
```

Expected: Нет результатов (gateway уже переключен в Task 2).

**Step 2: Проверить, что ни один модуль в app/ не импортирует из workflows/**

```bash
rg "from app\.mcp\.workflows" app/ --type py
```

Expected: Нет результатов. Если есть — исправить импорт перед удалением.

Типичные остатки:
- `app/mcp/gateway.py` — уже исправлен в Task 2
- `app/main.py` — может импортировать `create_workflow_mcp()` для REST mount

Если `app/main.py` ссылается на workflows:

```python
# Было:
from app.mcp.workflows.server import create_workflow_mcp

# Стало:
from app.mcp.tools.server import create_tools_mcp
```

**Step 3: Удалить workflow тесты**

```bash
rm -f tests/mcp/test_workflow_analysis.py
rm -f tests/mcp/test_workflow_sync.py
rm -f tests/mcp/test_workflow_import.py
rm -f tests/mcp/test_workflow_discovery.py
rm -f tests/mcp/test_workflow_setbuilder.py
rm -f tests/mcp/test_workflow_export.py
rm -f tests/mcp/test_workflow_curation.py
rm -f tests/mcp/test_import_playlist.py
```

**Step 4: Удалить workflows/ directory**

```bash
rm -rf app/mcp/workflows/
```

**Step 5: Запустить тесты**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: PASS. Если что-то падает с `ModuleNotFoundError: app.mcp.workflows` — значит остались ссылки. Найти и исправить:

```bash
rg "app\.mcp\.workflows" tests/ --type py
```

**Step 6: Запустить lint**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run ruff format --check app/mcp/ tests/mcp/
```

Expected: Clean.

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor(mcp): delete workflows/ directory (replaced by tools/)

All workflow tools migrated to app/mcp/tools/ in Phases 2-3.
Deleted 8 tool files, 8 test files. Gateway uses create_tools_mcp()."
```

---

## Task 6: Удалить types.py и types_curation.py

**Files:**
- Delete: `app/mcp/types.py`
- Delete: `app/mcp/types_curation.py`

**Prerequisite:** Task 5 пройден (workflows/ удалён). Эти файлы могли импортироваться из workflows/.

**Step 1: Проверить оставшиеся импорты**

```bash
rg "from app\.mcp\.types import" app/ tests/ --type py
rg "from app\.mcp\.types_curation" app/ tests/ --type py
```

Expected: Нет результатов. Если есть:
- `app/mcp/tools/` файлы используют `app.mcp.schemas` (Phase 0+1), НЕ `app.mcp.types`
- Phase 2 tools уже написаны с правильными импортами

Если остались ссылки (например, в `app/mcp/dependencies.py` или каком-то другом модуле):

**Маппинг замен:**

| Старый импорт | Новый импорт |
|--------------|-------------|
| `from app.mcp.types import PlaylistStatus` | Удалён — Phase 2 `get_playlist` возвращает `PlaylistDetail` |
| `from app.mcp.types import TrackDetails` | Удалён — Phase 2 `get_track` возвращает `TrackDetail` |
| `from app.mcp.types import SetBuildResult` | `from app.mcp.schemas import SetBuildResult` |
| `from app.mcp.types import TransitionScoreResult` | `from app.mcp.schemas import TransitionScoreResult` |
| `from app.mcp.types import ExportResult` | `from app.mcp.schemas import ExportResult` |
| `from app.mcp.types import SimilarTracksResult` | `from app.mcp.schemas import SimilarTracksResult` |
| `from app.mcp.types_curation import ClassifyResult` | `from app.mcp.schemas import ClassifyResult` |
| `from app.mcp.types_curation import SetReviewResult` | `from app.mcp.schemas import SetReviewResult` |
| `from app.mcp.types_curation import LibraryGapResult` | `from app.mcp.schemas import LibraryGapResult` |
| `from app.mcp.types_curation import MoodDistribution` | `from app.mcp.schemas import MoodDistribution` |

**Step 2: Исправить все оставшиеся импорты**

Заменить каждый найденный `from app.mcp.types import X` на `from app.mcp.schemas import X`.

**Step 3: Удалить файлы**

```bash
rm app/mcp/types.py
rm app/mcp/types_curation.py
```

**Step 4: Запустить тесты**

```bash
uv run pytest tests/mcp/ -v --tb=short
```

Expected: PASS. Нет `ModuleNotFoundError` для `app.mcp.types`.

**Step 5: Lint**

```bash
uv run ruff check app/mcp/ tests/mcp/
```

Expected: Clean.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(mcp): delete types.py + types_curation.py

All surviving types migrated to app/mcp/schemas.py in Phase 0+1.
Dead-code types removed: SwapSuggestion, ReorderSuggestion,
AdjustmentPlan, CurateCandidate, CurateSetResult."
```

---

## Task 7: Обновить skill файлы

**Files:**
- Modify: `app/mcp/skills/build-set-from-scratch/SKILL.md`
- Modify: `app/mcp/skills/expand-playlist/SKILL.md`
- Modify: `app/mcp/skills/improve-set/SKILL.md`

Skills содержат markdown-инструкции с ссылками на конкретные tool names. После Phase 4 эти имена изменились.

**Step 1: Найти устаревшие ссылки**

```bash
rg "get_playlist_status|get_track_details|import_playlist|import_tracks|search_by_criteria|export_set_m3u|export_set_json" app/mcp/skills/ --type md
```

**Step 2: Обновить ссылки**

Маппинг замен в SKILL.md:

| Старое | Новое |
|--------|-------|
| `dj_get_playlist_status` | `dj_get_playlist` |
| `dj_get_track_details` | `dj_get_track` |
| `dj_import_playlist` | `dj_create_playlist` + `dj_download_tracks` |
| `dj_import_tracks` | `dj_download_tracks` |
| `dj_search_by_criteria` | `dj_filter_tracks` |
| `dj_export_set_m3u` (из setbuilder) | `dj_export_set` (с `format="m3u"`) |
| `dj_export_set_json` (из setbuilder) | `dj_export_set` (с `format="json"`) |

Пример замены в SKILL.md:

```markdown
<!-- Было: -->
1. Используй `dj_get_playlist_status` чтобы проверить плейлист
2. Затем `dj_export_set_m3u` для экспорта

<!-- Стало: -->
1. Используй `dj_get_playlist` чтобы проверить плейлист
2. Затем `dj_export_set` с `format="m3u"` для экспорта
```

**Step 3: Запустить тест skills (если есть)**

```bash
uv run pytest tests/mcp/test_skills.py -v --tb=short
```

Expected: PASS.

**Step 4: Commit**

```bash
git add app/mcp/skills/
git commit -m "docs(mcp): update skill files for Phase 4 tool names

Replace legacy tool references (get_playlist_status, import_playlist,
search_by_criteria, export_set_m3u/json) with Phase 2-3 equivalents."
```

---

## Task 8: Проверить __all__ exports и пакетные __init__.py

**Files:**
- Modify: `app/mcp/__init__.py` (если есть)
- Modify: `app/mcp/tools/__init__.py`

**Step 1: Проверить app/mcp/__init__.py**

```bash
cat app/mcp/__init__.py 2>/dev/null || echo "File does not exist"
```

Если файл содержит re-exports из `workflows/` или `types.py`:

```python
# Удалить:
from app.mcp.workflows.server import create_workflow_mcp
from app.mcp.types import *

# Оставить/добавить:
from app.mcp.gateway import create_dj_mcp
from app.mcp.tools.server import create_tools_mcp
```

**Step 2: Проверить tools/__init__.py**

```bash
cat app/mcp/tools/__init__.py 2>/dev/null || echo "File does not exist"
```

Должен re-exportить `create_tools_mcp`:

```python
"""DJ workflow tools — new MCP architecture (Phases 1-3)."""

from app.mcp.tools.server import create_tools_mcp

__all__ = ["create_tools_mcp"]
```

**Step 3: Lint**

```bash
uv run ruff check app/mcp/ --select RUF022
```

Expected: `__all__` отсортированы правильно.

**Step 4: Commit**

```bash
git add app/mcp/__init__.py app/mcp/tools/__init__.py
git commit -m "refactor(mcp): clean up __init__.py exports after Phase 4"
```

---

## Task 9: Полная верификация — тесты + lint + mcp-list

**Files:**
- No new files — verification only

**Step 1: Полный тест suite**

```bash
uv run pytest -v --tb=short
```

Expected: Все тесты проходят. Ни одного `ModuleNotFoundError`.

**Step 2: Lint chain**

```bash
make lint
```

Expected: ruff check + format + mypy — всё чисто.

**Step 3: Проверить MCP tool list**

```bash
make mcp-list
```

Expected: Нет стабов, нет дубликатов. Список инструментов:

**dj namespace (Phase 2 CRUD):**
- `dj_list_tracks`, `dj_get_track`, `dj_create_track`, `dj_update_track`, `dj_delete_track`
- `dj_list_playlists`, `dj_get_playlist`, `dj_create_playlist`, `dj_update_playlist`, `dj_delete_playlist`
- `dj_list_sets`, `dj_get_set`, `dj_create_set`, `dj_update_set`
- `dj_list_features`, `dj_get_features`, `dj_analyze_track`

**dj namespace (Phase 1 search):**
- `dj_search`, `dj_filter_tracks`

**dj namespace (Phase 2 orchestrators):**
- `dj_build_set`, `dj_rebuild_set`, `dj_score_transitions`
- `dj_export_set`, `dj_download_tracks`
- `dj_find_similar_tracks`
- `dj_classify_tracks`, `dj_analyze_library_gaps`, `dj_review_set`

**dj namespace (Phase 3 sync):**
- `dj_sync_playlist`, `dj_link_playlist`, `dj_set_source_of_truth`

**dj namespace (visibility):**
- `dj_activate_heavy_mode`

**ym namespace (hidden):**
- ~30 OpenAPI-generated tools

**Step 4: Проверить отсутствие stale references**

```bash
rg "from app\.mcp\.workflows" app/ tests/ --type py
rg "from app\.mcp\.types import" app/ tests/ --type py
rg "from app\.mcp\.types_curation" app/ tests/ --type py
rg "create_workflow_mcp" app/ tests/ --type py
rg "register_analysis_tools|register_sync_tools" app/ tests/ --type py
```

Expected: Все — 0 результатов.

**Step 5: Проверить структуру файлов**

```bash
ls app/mcp/workflows/ 2>/dev/null && echo "ERROR: workflows/ still exists!" || echo "OK: workflows/ deleted"
ls app/mcp/types.py 2>/dev/null && echo "ERROR: types.py still exists!" || echo "OK: types.py deleted"
ls app/mcp/types_curation.py 2>/dev/null && echo "ERROR: types_curation.py still exists!" || echo "OK: types_curation.py deleted"
```

Expected: Все OK.

**Step 6: Commit**

```bash
git add -A
git commit -m "chore(mcp): Phase 4 complete — full verification passed

All tests pass, lint clean, no legacy references.
Workflows/ deleted, types.py deleted, types_curation.py deleted.
Gateway uses tools/ architecture from Phases 1-3."
```

---

## Summary: Before vs After Phase 4

| Metric | Before Phase 4 | After Phase 4 |
|--------|----------------|---------------|
| Tool source directory | `workflows/` (7 files) + `tools/` (12 files) | `tools/` only (12 files) |
| Type model files | `types.py` + `types_curation.py` + `schemas.py` | `schemas.py` only |
| Gateway factory | `create_workflow_mcp()` | `create_tools_mcp()` |
| Stub tools | 5 (2 import + 3 sync) | 0 |
| Duplicate tools | 2 (export_m3u, export_json in setbuilder) | 0 |
| Dead-code types | 5 (Swap, Reorder, Adjustment, CurateCandidate, CurateSetResult) | 0 |
| Legacy analysis tools | 2 (get_playlist_status, get_track_details) | 0 |
| Legacy search tool | 1 (search_by_criteria) | 0 |
| All tools use URN refs | Only Phase 2-3 tools | Yes — all tools |
| Test files for workflows | 8 (test_workflow_*.py) | 0 (replaced by tests/mcp/tools/) |

### Удалённые файлы
- `app/mcp/workflows/` — entire directory (8 files)
- `app/mcp/types.py` — 13 legacy models
- `app/mcp/types_curation.py` — 8 models (2 dead)
- `tests/mcp/test_workflow_*.py` — 7 test files
- `tests/mcp/test_import_playlist.py` — 1 test file

### Итоговая структура app/mcp/ после Phase 4

```text
app/mcp/
├── __init__.py
├── gateway.py              # create_dj_mcp() — mounts tools + ym
├── schemas.py              # Phase 0+1: все Pydantic models
├── refs.py                 # Phase 0+1: parse_ref, ParsedRef
├── resolvers.py            # Phase 0+1: TrackResolver, PlaylistResolver, SetResolver
├── converters.py           # Phase 0+1: ORM → Schema converters
├── pagination.py           # Phase 0+1: cursor-based pagination
├── stats.py                # Phase 0+1: get_library_stats
├── envelope.py             # Phase 2: wrap_list, wrap_detail, wrap_action
├── dependencies.py         # DI: get_session, get_*_service
├── observability.py        # Middleware stack
│
├── tools/
│   ├── __init__.py
│   ├── server.py           # create_tools_mcp() factory
│   ├── search.py           # Phase 1: search, filter_tracks
│   ├── tracks.py           # Phase 2: CRUD tracks
│   ├── playlists.py        # Phase 2: CRUD playlists
│   ├── sets.py             # Phase 2: CRUD sets + build_set + rebuild_set
│   ├── features.py         # Phase 2: list/get features + analyze_track
│   ├── scoring.py          # Phase 2: score_transitions
│   ├── export.py           # Phase 2: unified export_set(format=...)
│   ├── download.py         # Phase 2: download_tracks
│   ├── discovery.py        # Phase 2: find_similar_tracks
│   ├── curation.py         # Phase 2: classify, analyze_gaps, review
│   └── sync.py             # Phase 3: sync_playlist, link, source_of_truth
│
├── platforms/
│   ├── __init__.py
│   ├── keys.py             # Phase 0: PlatformKey enum
│   ├── protocol.py         # Phase 3: MusicPlatform Protocol
│   ├── registry.py         # Phase 3: PlatformRegistry
│   ├── sync_engine.py      # Phase 3: SyncEngine
│   ├── sync_diff.py        # Phase 3: compute_sync_diff
│   └── track_mapper.py     # Phase 3: DbTrackMapper
│
├── yandex_music/
│   ├── __init__.py
│   ├── server.py           # OpenAPI → MCP factory
│   ├── config.py           # Route filtering + naming
│   ├── response_filters.py # Response cleaning
│   └── adapter.py          # Phase 3: YandexMusicAdapter
│
├── prompts/
│   └── workflows.py
├── resources/
│   └── status.py
└── skills/
    ├── build-set-from-scratch/SKILL.md
    ├── expand-playlist/SKILL.md
    └── improve-set/SKILL.md
```
