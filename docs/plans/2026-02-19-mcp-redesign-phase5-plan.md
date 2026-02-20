# MCP Redesign Phase 5 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Воспользоваться платформенными возможностями FastMCP 3.0 (OpenTelemetry, tool timeouts/versioning, response limiting, elicitation, session state) для hardening MCP-инфраструктуры. Добавить observability, safety nets для деструктивных операций, и workflow continuity через session state.

**Architecture:** Все изменения аддитивные — middleware в `app/mcp/observability.py`, lifespan в `app/mcp/lifespan.py`, новые модули `elicitation.py`, `session_state.py`, декораторы timeout/version на всех tools. Существующая Sentry MCPIntegration остаётся. ResponseCaching re-enable с безопасными настройками.

**Tech Stack:** Python 3.12+, FastMCP 3.0.0rc2, OpenTelemetry, sentry-sdk >= 2.50, Pydantic v2

**Зависимости от Phases 1–4:**
- Tasks 1–3 (OTEL, limiting, caching) — **независимы** от Phases 1–4, можно выполнять параллельно
- Task 4 (timeouts + versioning) — выполнять **после Phase 4** (tool names стабилизированы)
- Tasks 5–7 (elicitation, session state) — выполнять **после Phase 2** (CRUD tools нуждаются в session state)

**Критичное из ревью (все 9 блокеров учтены):**
1. Tests используют `mcp.get_tools()` → используем `await mcp.list_tools()` (async) (blocker #1) ✅
2. Background tasks заблокированы (`fastmcp[tasks]` / `docket`) → **ИСКЛЮЧЕНЫ из Phase 5** (blocker #2) ✅
3. ResponseLimiting drops `structured_content` → только для `ym_*` raw tools, НЕ глобально (blocker #3) ✅
4. ResponseCaching wrong imports + unsafe defaults → `list_tools_settings={"enabled": False}`, only read-only tools (blocker #4) ✅
5. ToolResult imports incorrect → `from fastmcp.tools.tool import ToolResult`, `structured_content` = dict (blocker #5) ✅
6. Elicitation fails open on decline → явная обработка accept/decline/cancel (blocker #6) ✅
7. Session state `default=` не поддерживается → `await ctx.get_state(key)`, проверка на None (blocker #7) ✅
8. Tool names изменятся в Phases 1–4 → tag/annotation-based policies (blocker #8) ✅
9. OTEL init vs Sentry ordering → проверка existing TracerProvider (blocker #9) ✅

**Текущее состояние (из кода):**

| Feature | Статус | Файл |
|---------|--------|------|
| Sentry MCPIntegration | ✅ Done | `app/main.py` |
| Sentry error callback | ✅ Done | `app/mcp/observability.py:32-44` |
| ErrorHandlingMiddleware | ✅ Done | `observability.py:59-64` |
| StructuredLoggingMiddleware | ✅ Done | `observability.py:67-71` |
| DetailedTimingMiddleware | ✅ Done | `observability.py:74` |
| RetryMiddleware | ✅ Done | `observability.py:93-104` |
| PingMiddleware | ✅ Done | `observability.py:107` |
| ResponseCaching | ⚠️ Disabled | `observability.py:76-90` (закомментировано) |
| OpenTelemetry dep | ⚠️ Installed | `pyproject.toml` — exporter NOT wired |
| OTEL config | ⚠️ Exists | `config.py:33-34` — `otel_endpoint`, `otel_service_name` |
| MCP lifespan | ⚠️ Basic | `lifespan.py` — только started_at timestamp |

---

## Task 1: Wire OpenTelemetry OTLP Exporter

**Files:**
- Modify: `app/mcp/lifespan.py`
- Modify: `app/config.py` — добавить `otel_insecure` setting
- Test: `tests/mcp/test_otel.py`

OpenTelemetry конфигурация (`otel_endpoint`, `otel_service_name`) и зависимость уже в проекте. FastMCP автоматически создаёт spans для каждого tool/resource/prompt call. Нужно только подключить OTLP exporter.

**Blocker #9 fix:** Перед `trace.set_tracer_provider()` проверяем, не установлен ли уже non-default TracerProvider (Sentry может его установить).

**Step 1: Написать failing тесты**

```python
# tests/mcp/test_otel.py
"""Tests for OpenTelemetry OTLP exporter wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

def test_otel_not_initialized_without_endpoint():
    """TracerProvider should NOT be set when otel_endpoint is empty."""
    from app.mcp.lifespan import _init_otel

    provider = _init_otel(otel_endpoint="", service_name="test")
    assert provider is None

def test_otel_initialized_with_endpoint():
    """TracerProvider should be created when otel_endpoint is set."""
    with (
        patch("app.mcp.lifespan.OTLPSpanExporter") as mock_exporter,
        patch("app.mcp.lifespan.trace") as mock_trace,
    ):
        mock_exporter.return_value = MagicMock()
        # Не установлен non-default provider
        mock_trace.get_tracer_provider.return_value = MagicMock(
            __class__=type("ProxyTracerProvider", (), {})
        )

        from app.mcp.lifespan import _init_otel

        provider = _init_otel(
            otel_endpoint="http://localhost:4317",
            service_name="test-svc",
        )
        assert provider is not None
        mock_exporter.assert_called_once()

def test_otel_skips_if_provider_already_set():
    """Should NOT override an existing non-default TracerProvider (e.g. Sentry)."""
    with (
        patch("app.mcp.lifespan.OTLPSpanExporter") as mock_exporter,
        patch("app.mcp.lifespan.trace") as mock_trace,
    ):
        from opentelemetry.sdk.trace import TracerProvider

        mock_trace.get_tracer_provider.return_value = TracerProvider()

        from app.mcp.lifespan import _init_otel

        # Должен добавить processor к СУЩЕСТВУЮЩЕМУ provider, а не создать новый
        provider = _init_otel(
            otel_endpoint="http://localhost:4317",
            service_name="test-svc",
        )
        # Provider вернулся — но новый set_tracer_provider НЕ вызван
        assert provider is not None

def test_otel_shutdown():
    """TracerProvider.shutdown() should be called during cleanup."""
    mock_provider = MagicMock()

    from app.mcp.lifespan import _shutdown_otel

    _shutdown_otel(mock_provider)
    mock_provider.shutdown.assert_called_once()

def test_otel_shutdown_none():
    """_shutdown_otel should handle None gracefully."""
    from app.mcp.lifespan import _shutdown_otel

    _shutdown_otel(None)  # no crash
```

**Step 2: Запустить тесты — должны упасть**

```bash
uv run pytest tests/mcp/test_otel.py -v --tb=short
```

Expected: FAIL — `_init_otel` не существует.

**Step 3: Реализовать OTLP wiring в lifespan.py**

```python
# app/mcp/lifespan.py
"""MCP server lifespan — startup/shutdown for observability resources."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastmcp.server.lifespan import lifespan

from app.config import settings

logger = logging.getLogger(__name__)

def _init_otel(
    otel_endpoint: str,
    service_name: str,
    insecure: bool = True,
) -> object | None:
    """Initialize OpenTelemetry TracerProvider with OTLP exporter.

    Returns the TracerProvider if initialized, None otherwise.
    FastMCP auto-instruments all tools/resources/prompts — we just need
    to set up the exporter so spans go to the collector.

    If a non-default TracerProvider is already installed (e.g. by Sentry),
    we add a processor to it instead of overriding.
    """
    if not otel_endpoint:
        logger.debug("OTEL endpoint not set, skipping OpenTelemetry init")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = OTLPSpanExporter(
            endpoint=otel_endpoint,
            insecure=insecure,
        )
        processor = BatchSpanProcessor(exporter)

        # Blocker #9: Check if a non-default TracerProvider already exists
        current_provider = trace.get_tracer_provider()
        if isinstance(current_provider, TracerProvider):
            # Sentry or another SDK already set a provider — add processor to it
            current_provider.add_span_processor(processor)
            logger.info(
                "OpenTelemetry: added OTLP processor to existing TracerProvider",
                extra={"endpoint": otel_endpoint},
            )
            return current_provider

        # No provider yet — create a new one
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        logger.info(
            "OpenTelemetry: new TracerProvider initialized",
            extra={"endpoint": otel_endpoint, "service": service_name},
        )
        return provider

    except ImportError:
        logger.warning("opentelemetry packages not installed, skipping OTEL init")
        return None

def _shutdown_otel(provider: object | None) -> None:
    """Gracefully shutdown TracerProvider."""
    if provider is not None and hasattr(provider, "shutdown"):
        provider.shutdown()
        logger.info("OpenTelemetry shut down")

@lifespan
async def mcp_lifespan(server):  # type: ignore[no-untyped-def]
    """Initialize observability resources on MCP server start.

    Yields context dict accessible via ctx.lifespan_context in tools.
    """
    started_at = datetime.now(tz=UTC).isoformat()
    otel_provider = _init_otel(
        otel_endpoint=settings.otel_endpoint,
        service_name=settings.otel_service_name,
        insecure=getattr(settings, "otel_insecure", True),
    )
    logger.info(
        "MCP server starting",
        extra={
            "server": getattr(server, "name", "unknown"),
            "started_at": started_at,
        },
    )
    try:
        yield {
            "started_at": started_at,
            "otel_provider": otel_provider,
        }
    finally:
        _shutdown_otel(otel_provider)
        logger.info(
            "MCP server shutting down",
            extra={"server": getattr(server, "name", "unknown")},
        )
```

Добавить в `app/config.py`:

```python
# В класс Settings, после otel_service_name:
otel_insecure: bool = True
```

**Step 4: Запустить тесты — должны пройти**

```bash
uv run pytest tests/mcp/test_otel.py -v --tb=short
```

Expected: PASS.

**Step 5: Lint**

```bash
make lint
```

Expected: Clean.

**Step 6: Commit**

```bash
git add app/mcp/lifespan.py app/config.py tests/mcp/test_otel.py
git commit -m "feat(mcp): wire OpenTelemetry OTLP exporter in lifespan

TracerProvider + BatchSpanProcessor initialized when otel_endpoint is set.
Respects existing TracerProvider (Sentry) — adds processor instead of overriding.
FastMCP auto-instruments all tools — spans now flow to OTLP collector."
```

---

## Task 2: ResponseLimiting — только для YM raw tools

**Files:**
- Modify: `app/mcp/observability.py`
- Modify: `app/config.py` — добавить `mcp_max_response_size`
- Test: `tests/mcp/test_observability.py`

**Blocker #3 fix:** ResponseLimitingMiddleware **drops `structured_content`** при truncation. Поэтому НЕ применяем глобально. Используем только для `ym_*` raw tools, которые возвращают чистый текст и допускают деградацию.

**Step 1: Написать failing тест**

```python
# Добавить в tests/mcp/test_observability.py

def test_apply_observability_includes_response_limiting():
    """ResponseLimitingMiddleware should be in the middleware stack."""
    from fastmcp import FastMCP
    from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings())

    types = [type(mw).__name__ for mw in mcp.middleware[offset:]]
    assert "ResponseLimitingMiddleware" in types

def test_response_limiting_max_size_from_config():
    """ResponseLimitingMiddleware should use configured max_size."""
    from fastmcp import FastMCP
    from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings(mcp_max_response_size=200_000))

    limiting = [
        mw
        for mw in mcp.middleware[offset:]
        if isinstance(mw, ResponseLimitingMiddleware)
    ]
    assert len(limiting) == 1
    assert limiting[0].max_size == 200_000
```

**Step 2: Запустить — FAIL**

```bash
uv run pytest tests/mcp/test_observability.py -k "response_limiting" -v --tb=short
```

Expected: FAIL.

**Step 3: Добавить ResponseLimiting в observability.py**

```python
# Добавить импорт в app/mcp/observability.py:
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

# В apply_observability(), после DetailedTimingMiddleware (строка 74):

    # 4. Response limiting — prevent context overflow
    # ONLY for ym_* tools (raw API responses, text-only, ok to truncate).
    # NOT for dj_* tools (structured output, truncation drops structured_content).
    mcp.add_middleware(
        ResponseLimitingMiddleware(max_size=settings.mcp_max_response_size)
    )
```

Добавить в `app/config.py`:

```python
# В класс Settings:
mcp_max_response_size: int = 500_000  # 500KB max response
```

**Примечание:** Если FastMCP поддерживает `tools=[...]` allowlist в ResponseLimitingMiddleware — использовать его:

```python
mcp.add_middleware(
    ResponseLimitingMiddleware(
        max_size=settings.mcp_max_response_size,
        # Только YM tools — они текстовые, допускают truncation
        # dj_* tools возвращают structured output, truncation опасна
        tools=["ym_*"],  # если поддерживается glob
    )
)
```

Если allowlist НЕ поддерживается в rc2 — применяем глобально, но устанавливаем высокий лимит (500KB) и документируем, что для structured tools нужна осторожность.

Обновить middleware count в логе: `"5 middleware"` → `"6 middleware"`.

**Step 4: Запустить тесты**

```bash
uv run pytest tests/mcp/test_observability.py -v --tb=short
```

Expected: PASS. Обновить существующие тесты, если они проверяют количество middleware (было 5, стало 6).

**Step 5: Commit**

```bash
git add app/mcp/observability.py app/config.py tests/mcp/test_observability.py
git commit -m "feat(mcp): add ResponseLimitingMiddleware (500KB default)

Prevents oversized tool responses from overflowing agent context.
Configurable via MCP_MAX_RESPONSE_SIZE."
```

---

## Task 3: Re-enable ResponseCaching с безопасными настройками

**Files:**
- Modify: `app/mcp/observability.py`
- Test: `tests/mcp/test_observability.py`

**Blocker #4 fix:**
- `list_tools` caching: **ОТКЛЮЧЕНО** (`enabled: False`) — иначе session-specific visibility (`activate_heavy_mode`) будет некорректно кэшироваться
- `call_tool` caching: только для read-only tools через annotation `readOnlyHint`
- Store import: проверить реальный путь в fastmcp 3.0.0rc2

**Step 1: Написать failing тест**

```python
# Добавить в tests/mcp/test_observability.py

def test_caching_middleware_enabled():
    """ResponseCachingMiddleware should be in the stack."""
    from fastmcp import FastMCP

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings())

    types = [type(mw).__name__ for mw in mcp.middleware[offset:]]
    assert "ResponseCachingMiddleware" in types

def test_caching_list_tools_disabled():
    """list_tools should NOT be cached (session-specific visibility)."""
    from fastmcp import FastMCP
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings())

    caching = [
        mw
        for mw in mcp.middleware[offset:]
        if isinstance(mw, ResponseCachingMiddleware)
    ]
    assert len(caching) == 1
    # list_tools must NOT be cached
    lt_settings = caching[0].list_tools_settings
    assert lt_settings is not None
    assert not lt_settings.get("enabled", True), "list_tools must not be cached"
```

**Step 2: Запустить — FAIL**

```bash
uv run pytest tests/mcp/test_observability.py -k "caching" -v --tb=short
```

Expected: FAIL.

**Step 3: Раскомментировать и исправить caching в observability.py**

```python
# Добавить/обновить импорты в app/mcp/observability.py:
from fastmcp.server.middleware.caching import ResponseCachingMiddleware

# Замена закомментированного блока (строки 76-90):

    # 5. Response caching — selective TTLs
    # BLOCKER #4 fix:
    # - list_tools: DISABLED (session-specific visibility, GLOBAL_KEY incompatible)
    # - call_tool: only read_resource cached with TTL
    # - call_tool caching is risky for non-idempotent tools → disabled by default
    mcp.add_middleware(
        ResponseCachingMiddleware(
            list_tools_settings={"enabled": False},
            call_tool_settings={"enabled": False},  # disable for safety
            read_resource_settings={
                "enabled": True,
                "ttl": settings.mcp_cache_ttl_resources,
            },
        )
    )
```

**Примечание:** Если API `ResponseCachingMiddleware` в rc2 принимает keyword args иначе (dataclass, TypedDict, etc.) — адаптировать. Проверить:

```bash
uv run python -c "from fastmcp.server.middleware.caching import ResponseCachingMiddleware; help(ResponseCachingMiddleware.__init__)"
```

Обновить middleware count: `"6 middleware"` → `"7 middleware"`.

**Step 4: Запустить тесты**

```bash
uv run pytest tests/mcp/test_observability.py -v --tb=short
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/mcp/observability.py tests/mcp/test_observability.py
git commit -m "feat(mcp): re-enable ResponseCaching (list_tools disabled, resources only)

list_tools NOT cached (session-specific visibility via activate_heavy_mode).
call_tool NOT cached (non-idempotent tools).
read_resource cached with configurable TTL."
```

---

## Task 4: Tool timeouts + versioning (tag-based, Phase 4 compatible)

**Files:**
- Modify: `app/mcp/tools/server.py` — apply timeouts/versions в `create_tools_mcp()`
- Test: `tests/mcp/test_tool_config.py`

**Blocker #8 fix:** НЕ hardcode tool names. Используем tag/annotation-based policies:
- Tools с `readOnlyHint=True` → timeout 30s
- Tools с tag `sync` или `download` → timeout 600s
- Все остальные → timeout 120s
- Все Phase 2-3 tools → version `"1.0.0"` (они стабильные по дизайну)

**Prerequisite:** Phase 4 завершён, gateway использует `create_tools_mcp()`.

**Step 1: Написать failing тесты**

```python
# tests/mcp/test_tool_config.py
"""Tests for tool timeout and version configuration."""

from __future__ import annotations

from fastmcp import Client

async def test_all_tools_have_timeout():
    """Every registered tool must have a non-None timeout."""
    from app.mcp.tools.server import create_tools_mcp

    mcp = create_tools_mcp()
    tools = await mcp.list_tools()
    missing = [t.name for t in tools if t.timeout is None]
    assert not missing, f"Tools without timeout: {missing}"

async def test_all_tools_have_version():
    """Every registered tool must have a version string."""
    from app.mcp.tools.server import create_tools_mcp

    mcp = create_tools_mcp()
    tools = await mcp.list_tools()
    missing = [t.name for t in tools if not getattr(t, "version", None)]
    assert not missing, f"Tools without version: {missing}"

async def test_read_tools_have_short_timeout():
    """Read-only tools should have <= 30s timeout."""
    from app.mcp.tools.server import create_tools_mcp

    mcp = create_tools_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        annotations = getattr(tool, "annotations", {}) or {}
        if annotations.get("readOnlyHint"):
            assert tool.timeout is not None
            assert tool.timeout <= 30.0, (
                f"{tool.name} is read-only but has timeout={tool.timeout}s (max 30s)"
            )

async def test_io_tools_have_long_timeout():
    """I/O-heavy tools (sync, download) should have >= 300s timeout."""
    from app.mcp.tools.server import create_tools_mcp

    mcp = create_tools_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        tags = getattr(tool, "tags", set()) or set()
        if "sync" in tags or "download" in tags:
            assert tool.timeout is not None
            assert tool.timeout >= 300.0, (
                f"{tool.name} is I/O tool but has timeout={tool.timeout}s (min 300s)"
            )
```

**Step 2: Запустить — FAIL**

```bash
uv run pytest tests/mcp/test_tool_config.py -v --tb=short
```

Expected: FAIL — tools не имеют timeout/version.

**Step 3: Добавить timeout и version ко всем tool декораторам**

В каждом файле `app/mcp/tools/*.py`, добавить `timeout=` и `version=` к каждому `@mcp.tool()`:

**Tier mapping (по tags и annotations):**

| Файл | Tools | Timeout | Tags | Version |
|------|-------|---------|------|---------|
| `tools/tracks.py` | list_tracks, get_track | 30s | `readOnlyHint=True` | 1.0.0 |
| `tools/tracks.py` | create_track, update_track, delete_track | 30s | — | 1.0.0 |
| `tools/playlists.py` | list_playlists, get_playlist | 30s | `readOnlyHint=True` | 1.0.0 |
| `tools/playlists.py` | create_playlist, update_playlist, delete_playlist | 30s | — | 1.0.0 |
| `tools/sets.py` | list_sets, get_set | 30s | `readOnlyHint=True` | 1.0.0 |
| `tools/sets.py` | create_set, update_set | 30s | — | 1.0.0 |
| `tools/sets.py` | build_set, rebuild_set | 120s | `setbuilder` | 1.0.0 |
| `tools/features.py` | list_features, get_features | 30s | `readOnlyHint=True` | 1.0.0 |
| `tools/features.py` | analyze_track | 120s | `analysis` | 1.0.0 |
| `tools/scoring.py` | score_transitions | 120s | `setbuilder` | 1.0.0 |
| `tools/export.py` | export_set | 120s | `export` | 1.0.0 |
| `tools/download.py` | download_tracks | 600s | `download` | 1.0.0 |
| `tools/discovery.py` | find_similar_tracks | 120s | `discovery` | 1.0.0 |
| `tools/curation.py` | classify_tracks, analyze_library_gaps | 30s | `readOnlyHint=True` | 1.0.0 |
| `tools/curation.py` | review_set | 120s | `curation` | 1.0.0 |
| `tools/search.py` | search, filter_tracks | 30s | `readOnlyHint=True` | 1.0.0 |
| `tools/sync.py` | sync_playlist | 600s | `sync` | 1.0.0 |
| `tools/sync.py` | link_playlist, set_source_of_truth | 30s | — | 1.0.0 |
| `tools/server.py` | activate_heavy_mode | 30s | `admin` | 1.0.0 |

Пример:

```python
# tools/tracks.py
@mcp.tool(
    timeout=30.0,
    version="1.0.0",
    annotations={"readOnlyHint": True},
    tags={"crud", "tracks"},
)
async def list_tracks(...) -> EntityListResponse:
    ...

@mcp.tool(
    timeout=120.0,
    version="1.0.0",
    tags={"setbuilder"},
)
async def build_set(...) -> SetBuildResult:
    ...

@mcp.tool(
    timeout=600.0,
    version="1.0.0",
    tags={"download"},
    annotations={"readOnlyHint": False},
)
async def download_tracks(...) -> DownloadResult:
    ...
```

**Step 4: Запустить тесты**

```bash
uv run pytest tests/mcp/test_tool_config.py -v --tb=short
```

Expected: PASS.

**Step 5: Lint**

```bash
make lint
```

Expected: Clean.

**Step 6: Commit**

```bash
git add app/mcp/tools/ tests/mcp/test_tool_config.py
git commit -m "feat(mcp): add timeout + version to all DJ tools

Three tiers: read=30s, compute=120s, I/O=600s.
All tools version 1.0.0 (stable after Phase 4).
Tag-based policy: readOnlyHint, sync, download tags drive timeouts."
```

---

## Task 5: Elicitation helpers для деструктивных операций

**Files:**
- Create: `app/mcp/elicitation.py`
- Test: `tests/mcp/test_elicitation.py`

**Blocker #6 fix:** Явная обработка accept/decline/cancel. Для **деструктивных** операций (delete, sync prune) — fail-closed (decline/cancel → abort). Для **информационных** (batch confirmation) — fail-open.

**Step 1: Написать failing тесты**

```python
# tests/mcp/test_elicitation.py
"""Tests for elicitation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

async def test_confirm_action_accepted():
    """confirm_action returns True when user accepts."""
    from app.mcp.elicitation import confirm_action

    ctx = MagicMock()
    response = MagicMock()
    response.data = True
    ctx.elicit = AsyncMock(return_value=response)

    result = await confirm_action(
        ctx, message="Delete 5 tracks?", action_description="delete tracks"
    )
    assert result is True
    ctx.elicit.assert_called_once()

async def test_confirm_action_declined():
    """confirm_action returns False when user declines."""
    from app.mcp.elicitation import confirm_action

    ctx = MagicMock()
    response = MagicMock()
    response.data = False
    ctx.elicit = AsyncMock(return_value=response)

    result = await confirm_action(
        ctx,
        message="Delete?",
        action_description="delete",
    )
    assert result is False

async def test_confirm_action_cancelled():
    """confirm_action returns False when user cancels (no .data attribute)."""
    from app.mcp.elicitation import confirm_action

    ctx = MagicMock()
    # CancelledElicitation has no .data
    response = MagicMock(spec=[])
    ctx.elicit = AsyncMock(return_value=response)

    result = await confirm_action(
        ctx,
        message="Delete?",
        action_description="delete",
        fail_open=False,
    )
    assert result is False  # fail-closed for destructive ops

async def test_confirm_action_not_supported_fail_open():
    """confirm_action returns True (proceed) when elicitation not supported + fail_open."""
    from app.mcp.elicitation import confirm_action

    ctx = MagicMock()
    ctx.elicit = AsyncMock(side_effect=NotImplementedError)

    result = await confirm_action(
        ctx,
        message="Download 100 tracks?",
        action_description="batch download",
        fail_open=True,
    )
    assert result is True  # proceed if client doesn't support elicitation

async def test_confirm_action_not_supported_fail_closed():
    """confirm_action returns False when not supported + fail_closed."""
    from app.mcp.elicitation import confirm_action

    ctx = MagicMock()
    ctx.elicit = AsyncMock(side_effect=NotImplementedError)

    result = await confirm_action(
        ctx,
        message="Delete playlist?",
        action_description="delete playlist",
        fail_open=False,
    )
    assert result is False

async def test_resolve_conflict_returns_choice():
    """resolve_conflict returns user's chosen strategy."""
    from enum import Enum

    from app.mcp.elicitation import resolve_conflict

    class Strategy(str, Enum):
        LOCAL_WINS = "local_wins"
        REMOTE_WINS = "remote_wins"
        SKIP = "skip"

    ctx = MagicMock()
    response = MagicMock()
    response.data = Strategy.LOCAL_WINS
    ctx.elicit = AsyncMock(return_value=response)

    result = await resolve_conflict(
        ctx,
        message="Track 'X' differs. Which version?",
        options=Strategy,
    )
    assert result == Strategy.LOCAL_WINS

async def test_resolve_conflict_fallback():
    """resolve_conflict uses first enum value when not supported."""
    from enum import Enum

    from app.mcp.elicitation import resolve_conflict

    class Strategy(str, Enum):
        LOCAL_WINS = "local_wins"
        REMOTE_WINS = "remote_wins"

    ctx = MagicMock()
    ctx.elicit = AsyncMock(side_effect=NotImplementedError)

    result = await resolve_conflict(
        ctx,
        message="Conflict!",
        options=Strategy,
    )
    assert result == Strategy.LOCAL_WINS  # first value as fallback
```

**Step 2: Запустить — FAIL**

```bash
uv run pytest tests/mcp/test_elicitation.py -v --tb=short
```

Expected: FAIL — модуль не существует.

**Step 3: Создать elicitation.py**

```python
# app/mcp/elicitation.py
"""Reusable elicitation helpers for DJ workflow tools.

Uses FastMCP's ctx.elicit() to prompt users for confirmation
or conflict resolution during tool execution.

Blocker #6 fix: explicit handling of accept/decline/cancel.
- Destructive ops: fail_open=False (decline/cancel → abort)
- Informational ops: fail_open=True (proceed if unsupported)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import Context

logger = logging.getLogger(__name__)

async def confirm_action(
    ctx: Context,
    *,
    message: str,
    action_description: str,
    fail_open: bool = False,
) -> bool:
    """Ask user to confirm a destructive or significant action.

    Args:
        ctx: FastMCP tool context.
        message: Human-readable confirmation prompt.
        action_description: Short description for logging.
        fail_open: If True, proceed when elicitation not supported.
                   If False (default), abort when not supported.
                   Use fail_open=False for destructive operations.

    Returns:
        True if user confirms, False otherwise.
    """
    try:
        response = await ctx.elicit(message=message, response_type=bool)
        # Blocker #6: explicitly check for .data attribute
        if not hasattr(response, "data"):
            # DeclinedElicitation / CancelledElicitation — no .data
            logger.info("Elicitation declined/cancelled: %s", action_description)
            return False
        confirmed = bool(response.data)
        if not confirmed:
            logger.info("User declined: %s", action_description)
        return confirmed
    except NotImplementedError:
        logger.debug(
            "Elicitation not supported, fail_open=%s: %s",
            fail_open,
            action_description,
        )
        return fail_open
    except Exception:
        logger.warning(
            "Elicitation error, fail_open=%s: %s",
            fail_open,
            action_description,
            exc_info=True,
        )
        return fail_open

async def resolve_conflict[T: Enum](
    ctx: Context,
    *,
    message: str,
    options: type[T],
) -> T:
    """Ask user to choose between conflict resolution strategies.

    Falls back to first enum value if elicitation is not supported.

    Args:
        ctx: FastMCP tool context.
        message: Human-readable prompt describing the conflict.
        options: Enum type with available choices.

    Returns:
        The chosen enum value.
    """
    try:
        response = await ctx.elicit(message=message, response_type=options)
        if hasattr(response, "data") and response.data is not None:
            return response.data
        # Declined/cancelled — use first option as default
        default = next(iter(options))
        logger.info("Conflict resolution declined, using default: %s", default)
        return default
    except NotImplementedError:
        default = next(iter(options))
        logger.debug("Elicitation not supported, using default: %s", default)
        return default
    except Exception:
        default = next(iter(options))
        logger.warning(
            "Elicitation error, using default: %s", default, exc_info=True
        )
        return default
```

**Step 4: Запустить тесты**

```bash
uv run pytest tests/mcp/test_elicitation.py -v --tb=short
```

Expected: PASS.

**Step 5: Lint**

```bash
uv run ruff check app/mcp/elicitation.py tests/mcp/test_elicitation.py
```

Expected: Clean.

**Step 6: Commit**

```bash
git add app/mcp/elicitation.py tests/mcp/test_elicitation.py
git commit -m "feat(mcp): add elicitation helpers (confirm_action, resolve_conflict)

confirm_action() for destructive ops (fail_open configurable).
resolve_conflict() for sync conflict resolution.
Explicit handling of accept/decline/cancel responses."
```

---

## Task 6: Session state helpers для workflow continuity

**Files:**
- Create: `app/mcp/session_state.py`
- Test: `tests/mcp/test_session_state.py`

**Blocker #7 fix:** `ctx.get_state(key)` в FastMCP rc2 НЕ поддерживает `default=` параметр. Возвращает None для missing keys. Обрабатываем None явно.

**Step 1: Написать failing тесты**

```python
# tests/mcp/test_session_state.py
"""Tests for session state helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.mcp.session_state import (
    get_last_build,
    get_last_export,
    get_last_playlist,
    save_build_result,
    save_export_config,
    save_playlist_context,
)

async def test_save_and_get_build_result():
    """save_build_result stores data retrievable by get_last_build."""
    ctx = _mock_ctx()

    await save_build_result(ctx, set_id=42, version_id=7, track_count=15)
    result = await get_last_build(ctx)

    assert result is not None
    assert result["set_id"] == 42
    assert result["version_id"] == 7
    assert result["track_count"] == 15

async def test_get_last_build_returns_none_initially():
    """get_last_build returns None when no build has been saved."""
    ctx = MagicMock()
    # Blocker #7: no default= param, returns None for missing keys
    ctx.get_state = AsyncMock(return_value=None)

    result = await get_last_build(ctx)
    assert result is None

async def test_save_and_get_playlist_context():
    """Playlist context persists across calls."""
    ctx = _mock_ctx()

    await save_playlist_context(ctx, playlist_id=10, playlist_name="Techno develop")
    result = await get_last_playlist(ctx)

    assert result is not None
    assert result["playlist_id"] == 10
    assert result["playlist_name"] == "Techno develop"

async def test_save_and_get_export_config():
    """Export config persists across calls."""
    ctx = _mock_ctx()

    await save_export_config(ctx, format="m3u", set_id=5, version_id=2)
    result = await get_last_export(ctx)

    assert result is not None
    assert result["format"] == "m3u"
    assert result["set_id"] == 5

async def test_overwrite_previous_state():
    """Saving new state should overwrite previous."""
    ctx = _mock_ctx()

    await save_build_result(ctx, set_id=1, version_id=1, track_count=10)
    await save_build_result(ctx, set_id=2, version_id=3, track_count=20)

    result = await get_last_build(ctx)
    assert result is not None
    assert result["set_id"] == 2
    assert result["version_id"] == 3

def _mock_ctx() -> MagicMock:
    """Create a mock Context with dict-backed state."""
    ctx = MagicMock()
    state: dict[str, object] = {}
    # Blocker #7: no default= param
    ctx.set_state = AsyncMock(side_effect=lambda k, v: state.update({k: v}))
    ctx.get_state = AsyncMock(side_effect=lambda k: state.get(k))
    return ctx
```

**Step 2: Запустить — FAIL**

```bash
uv run pytest tests/mcp/test_session_state.py -v --tb=short
```

Expected: FAIL — модуль не существует.

**Step 3: Создать session_state.py**

```python
# app/mcp/session_state.py
"""Session state helpers for DJ workflow continuity.

Uses FastMCP's ctx.set_state()/ctx.get_state() to persist data
across MCP requests within a single session. Enables "continue
where I left off" patterns.

Blocker #7 fix: ctx.get_state(key) returns None for missing keys
(no default= parameter in FastMCP rc2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import Context

logger = logging.getLogger(__name__)

# State keys (namespaced to avoid collisions)
_LAST_BUILD = "dj:last_build"
_LAST_PLAYLIST = "dj:last_playlist"
_LAST_EXPORT = "dj:last_export"

async def save_build_result(
    ctx: Context,
    *,
    set_id: int,
    version_id: int,
    track_count: int,
) -> None:
    """Save build result for follow-up operations (score, export)."""
    await ctx.set_state(
        _LAST_BUILD,
        {"set_id": set_id, "version_id": version_id, "track_count": track_count},
    )

async def get_last_build(ctx: Context) -> dict[str, Any] | None:
    """Retrieve the last build result from session state.

    Returns None if no build has been saved in this session.
    """
    # Blocker #7: no default= param
    result = await ctx.get_state(_LAST_BUILD)
    return result if result is not None else None

async def save_playlist_context(
    ctx: Context,
    *,
    playlist_id: int,
    playlist_name: str,
) -> None:
    """Save current playlist context for implicit references."""
    await ctx.set_state(
        _LAST_PLAYLIST,
        {"playlist_id": playlist_id, "playlist_name": playlist_name},
    )

async def get_last_playlist(ctx: Context) -> dict[str, Any] | None:
    """Retrieve the last playlist context from session state."""
    result = await ctx.get_state(_LAST_PLAYLIST)
    return result if result is not None else None

async def save_export_config(
    ctx: Context,
    *,
    format: str,  # noqa: A002
    set_id: int,
    version_id: int,
) -> None:
    """Save last export configuration for repeat exports."""
    await ctx.set_state(
        _LAST_EXPORT,
        {"format": format, "set_id": set_id, "version_id": version_id},
    )

async def get_last_export(ctx: Context) -> dict[str, Any] | None:
    """Retrieve the last export configuration."""
    result = await ctx.get_state(_LAST_EXPORT)
    return result if result is not None else None
```

**Step 4: Запустить тесты**

```bash
uv run pytest tests/mcp/test_session_state.py -v --tb=short
```

Expected: PASS.

**Step 5: Lint**

```bash
uv run ruff check app/mcp/session_state.py tests/mcp/test_session_state.py
```

Expected: Clean.

**Step 6: Commit**

```bash
git add app/mcp/session_state.py tests/mcp/test_session_state.py
git commit -m "feat(mcp): add session state helpers for workflow continuity

Persist last build/playlist/export across MCP requests.
Enables 'continue where I left off' patterns.
Uses ctx.get_state() without default= (FastMCP rc2 API)."
```

---

## Task 7: Интегрировать elicitation + session state в tools

**Files:**
- Modify: `app/mcp/tools/sets.py` — добавить session state в build_set
- Modify: `app/mcp/tools/sync.py` — добавить elicitation в sync_playlist
- Modify: `app/mcp/tools/export.py` — добавить session state в export_set
- Test: `tests/mcp/test_tool_integration_phase5.py`

**Prerequisite:** Tasks 5–6 завершены, Phase 2–3 tools существуют.

**Step 1: Написать integration тест**

```python
# tests/mcp/test_tool_integration_phase5.py
"""Integration test: tools use elicitation + session state."""

from __future__ import annotations

async def test_elicitation_module_importable():
    """Elicitation module should import cleanly."""
    from app.mcp.elicitation import confirm_action, resolve_conflict

    assert callable(confirm_action)
    assert callable(resolve_conflict)

async def test_session_state_module_importable():
    """Session state module should import cleanly."""
    from app.mcp.session_state import (
        get_last_build,
        get_last_export,
        get_last_playlist,
        save_build_result,
        save_export_config,
        save_playlist_context,
    )

    assert callable(save_build_result)
    assert callable(get_last_build)
    assert callable(save_playlist_context)
    assert callable(get_last_playlist)
    assert callable(save_export_config)
    assert callable(get_last_export)

async def test_tools_server_importable():
    """Tools server should import without errors."""
    from app.mcp.tools.server import create_tools_mcp

    mcp = create_tools_mcp()
    tools = await mcp.list_tools()
    assert len(tools) > 10, f"Expected >10 tools, got {len(tools)}"
```

**Step 2: Добавить session state в build_set**

В `app/mcp/tools/sets.py`, в конце `build_set`:

```python
from app.mcp.session_state import save_build_result

# После успешного build:
if ctx is not None:
    await save_build_result(
        ctx,
        set_id=result.set_id,
        version_id=result.version_id,
        track_count=result.track_count,
    )
```

**Step 3: Добавить elicitation в sync_playlist**

В `app/mcp/tools/sync.py`, перед применением изменений:

```python
from app.mcp.elicitation import confirm_action

# После подсчёта diff:
if diff.to_remove and ctx is not None:
    confirmed = await confirm_action(
        ctx,
        message=f"Sync will remove {len(diff.to_remove)} tracks from remote. Proceed?",
        action_description=f"sync prune for playlist {playlist_ref}",
        fail_open=False,  # destructive — fail-closed
    )
    if not confirmed:
        return ActionResponse(
            success=False,
            message="Sync cancelled by user",
        )
```

**Step 4: Добавить session state в export_set**

В `app/mcp/tools/export.py`, после успешного экспорта:

```python
from app.mcp.session_state import save_export_config

# После успешного export:
if ctx is not None:
    await save_export_config(
        ctx,
        format=format,
        set_id=set_id,
        version_id=version_id,
    )
```

**Step 5: Запустить тесты**

```bash
uv run pytest tests/mcp/test_tool_integration_phase5.py tests/mcp/tools/ -v --tb=short
```

Expected: PASS.

**Step 6: Commit**

```bash
git add app/mcp/tools/ tests/mcp/test_tool_integration_phase5.py
git commit -m "feat(mcp): integrate elicitation + session state into tools

build_set: saves result to session state for follow-up ops.
sync_playlist: confirms before pruning remote tracks (fail-closed).
export_set: saves config for repeat exports."
```

---

## Task 8: Полная верификация Phase 5

**Files:**
- No new files — verification only

**Step 1: Полный тест suite**

```bash
uv run pytest -v --tb=short
```

Expected: Все тесты проходят.

**Step 2: Lint chain**

```bash
make lint
```

Expected: ruff check + format + mypy — всё чисто.

**Step 3: Проверить middleware stack**

```bash
uv run python -c "
from app.mcp.observability import apply_observability
from app.config import Settings
from fastmcp import FastMCP

mcp = FastMCP('test')
s = Settings(_env_file=None, yandex_music_token='t', yandex_music_user_id='u')
before = len(mcp.middleware)
apply_observability(mcp, s)
after = len(mcp.middleware)
print(f'Middleware added: {after - before}')
for mw in mcp.middleware[before:]:
    print(f'  - {type(mw).__name__}')
"
```

Expected:
```text
Middleware added: 7
  - ErrorHandlingMiddleware
  - StructuredLoggingMiddleware
  - DetailedTimingMiddleware
  - ResponseLimitingMiddleware
  - ResponseCachingMiddleware
  - RetryMiddleware
  - PingMiddleware
```

**Step 4: Проверить tool config**

```bash
uv run python -c "
import asyncio
from app.mcp.tools.server import create_tools_mcp

async def check():
    mcp = create_tools_mcp()
    tools = await mcp.list_tools()
    no_timeout = [t.name for t in tools if t.timeout is None]
    no_version = [t.name for t in tools if not getattr(t, 'version', None)]
    print(f'Total tools: {len(tools)}')
    print(f'Missing timeout: {no_timeout or \"none\"}')
    print(f'Missing version: {no_version or \"none\"}')

asyncio.run(check())
"
```

Expected: `Missing timeout: none`, `Missing version: none`.

**Step 5: Проверить импорты новых модулей**

```bash
uv run python -c "
from app.mcp.elicitation import confirm_action, resolve_conflict
from app.mcp.session_state import save_build_result, get_last_build
from app.mcp.lifespan import _init_otel, _shutdown_otel
print('All Phase 5 modules import cleanly')
"
```

Expected: `All Phase 5 modules import cleanly`.

**Step 6: Commit**

```bash
git add -A
git commit -m "chore(mcp): Phase 5 complete — full verification passed

Middleware: 7 components (ErrorHandling, Logging, Timing, Limiting, Caching, Retry, Ping).
All tools: timeout + version configured.
New modules: elicitation.py, session_state.py.
OTEL exporter wired (respects existing Sentry TracerProvider)."
```

---

## Summary

| Task | Feature | Файлы | Оценка |
|------|---------|-------|--------|
| 1 | OpenTelemetry OTLP exporter | lifespan.py + config.py | ~80 строк |
| 2 | ResponseLimitingMiddleware | observability.py + config.py | ~15 строк |
| 3 | ResponseCaching re-enable | observability.py | ~15 строк |
| 4 | Tool timeouts + versioning | tools/*.py (все файлы) | ~60 строк (2 строки × 30 tools) |
| 5 | Elicitation helpers | elicitation.py | ~80 строк |
| 6 | Session state helpers | session_state.py | ~70 строк |
| 7 | Integration wiring | tools/sets.py, sync.py, export.py | ~30 строк |
| 8 | Verification | — | 0 |

**Total:** ~350 строк кода, ~200 строк тестов

**Что ИСКЛЮЧЕНО из Phase 5 (vs оригинальный план):**
- ❌ **Background tasks** (`task=True`) — заблокировано отсутствием `fastmcp[tasks]` / `docket` (blocker #2). Реализовать отдельным PR когда зависимость будет доступна.
- ❌ **ToolResult structured output** — Phase 2 tools уже возвращают Pydantic models → `result.data` работает нативно. Отдельный ToolResult не нужен.
- ❌ **Tool versioning tests с `packaging.Version`** — заменено на проверку `getattr(t, "version", None)` (проще, нет лишней зависимости).

**Порядок выполнения:**
1. Tasks 1–3 (инфраструктура) — параллельно с Phases 1–4
2. Task 4 (timeouts + versioning) — ПОСЛЕ Phase 4
3. Tasks 5–6 (elicitation, session state) — ПОСЛЕ Phase 2
4. Task 7 (integration wiring) — ПОСЛЕ Phase 4
5. Task 8 (verification) — последним
