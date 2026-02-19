# MCP Platform Features — Phase 5 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Leverage FastMCP v3 platform features (OpenTelemetry, background tasks, elicitation, session state, structured output, tool timeouts, response limiting) to harden the MCP server infrastructure.

**Architecture:** All changes are additive — middleware in `app/mcp/observability.py`, lifespan in `app/mcp/lifespan.py`, tool decorators across `app/mcp/workflows/`. No new architectural layers. Existing Sentry MCPIntegration (`app/main.py:30-35`) already works. ResponseCaching (`observability.py:76-90`) is already coded but disabled — we re-enable with selective invalidation.

**Tech Stack:** Python 3.12+, FastMCP 3.0, OpenTelemetry, sentry-sdk >= 2.50, Pydantic v2

**Design doc:** `docs/plans/2026-02-19-mcp-tools-redesign-design.md`

**Dependencies:** This phase is independent of Phases 1-4. Tasks can run in parallel with or after the redesign phases. Dependencies on specific phases are noted per task.

---

## Current State Audit

| Feature | Status | Location |
|---------|--------|----------|
| Sentry MCPIntegration | ✅ Done | `app/main.py:30-35` |
| Sentry error callback | ✅ Done | `app/mcp/observability.py:32-44` |
| ErrorHandlingMiddleware | ✅ Done | `observability.py:59-64` |
| StructuredLoggingMiddleware | ✅ Done | `observability.py:67-70` |
| DetailedTimingMiddleware | ✅ Done | `observability.py:74` |
| RetryMiddleware | ✅ Done | `observability.py:93-104` |
| PingMiddleware | ✅ Done | `observability.py:107` |
| ResponseCachingMiddleware | ⚠️ Disabled | `observability.py:76-90` (stale list_tools cache) |
| OpenTelemetry dep | ⚠️ Installed | `pyproject.toml:31` — exporter NOT wired |
| OpenTelemetry config | ⚠️ Exists | `config.py:33-34` — `otel_endpoint`, `otel_service_name` |
| Background tasks | ❌ Missing | No `task=True` on any tool |
| Tool timeouts | ❌ Missing | No `timeout=` on any tool |
| Elicitation | ❌ Missing | No `ctx.elicit()` calls |
| Session state | ❌ Missing | No `ctx.set_state()`/`ctx.get_state()` |
| ResponseLimiting | ❌ Missing | Not in middleware stack |
| RateLimiting (MCP-level) | ❌ Missing | Rate limiting only in YM client |
| Structured output | ❌ Missing | No `output_schema` or `ToolResult` |
| Tool versioning | ❌ Missing | No `version=` on any tool |

---

## Task 1: Wire OpenTelemetry OTLP Exporter

**Files:**
- Modify: `app/mcp/lifespan.py`
- Modify: `app/config.py` (add `otel_insecure` setting)
- Test: `tests/mcp/test_otel.py`

OpenTelemetry config (`otel_endpoint`, `otel_service_name`) and the dependency (`opentelemetry-exporter-otlp`) are already in place. FastMCP auto-creates spans for every tool/resource/prompt call via its built-in tracer. We just need to wire the OTLP exporter so those spans actually go somewhere (Jaeger, Grafana Tempo, etc.).

**Step 1: Write the failing tests**

```python
# tests/mcp/test_otel.py
"""Tests for OpenTelemetry OTLP exporter wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

def test_otel_not_initialized_without_endpoint():
    """TracerProvider should NOT be set when otel_endpoint is empty."""
    from app.mcp.lifespan import _init_otel

    provider = _init_otel(otel_endpoint="", service_name="test")
    assert provider is None

def test_otel_initialized_with_endpoint():
    """TracerProvider should be created when otel_endpoint is set."""
    with patch("app.mcp.lifespan.OTLPSpanExporter") as mock_exporter:
        mock_exporter.return_value = MagicMock()
        from app.mcp.lifespan import _init_otel

        provider = _init_otel(
            otel_endpoint="http://localhost:4317",
            service_name="test-svc",
        )
        assert provider is not None
        mock_exporter.assert_called_once()

def test_otel_shutdown_called_on_cleanup():
    """TracerProvider.shutdown() should be called during lifespan cleanup."""
    mock_provider = MagicMock()

    from app.mcp.lifespan import _shutdown_otel

    _shutdown_otel(mock_provider)
    mock_provider.shutdown.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_otel.py -v`
Expected: FAIL with `ImportError` or `AttributeError` (functions don't exist yet)

**Step 3: Implement OTLP exporter wiring**

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

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=otel_endpoint,
            insecure=insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info(
            "OpenTelemetry initialized",
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
    )
    logger.info(
        "MCP server starting",
        extra={"server": getattr(server, "name", "unknown"), "started_at": started_at},
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

Add to config:

```python
# app/config.py — add after otel_service_name
otel_insecure: bool = True
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_otel.py -v`
Expected: 3 PASS

**Step 5: Run lint**

Run: `make lint`
Expected: PASS

**Step 6: Commit**

```bash
git add app/mcp/lifespan.py app/config.py tests/mcp/test_otel.py
git commit -m "feat(mcp): wire OpenTelemetry OTLP exporter in lifespan

TracerProvider + BatchSpanProcessor initialized when otel_endpoint is set.
FastMCP auto-instruments all tools — spans now flow to OTLP collector."
```

---

## Task 2: ResponseLimitingMiddleware

**Files:**
- Modify: `app/mcp/observability.py`
- Modify: `app/config.py` (add `mcp_max_response_size`)
- Modify: `tests/mcp/test_observability.py`

Prevents tools from returning responses that overflow the agent's context window. FastMCP's `ResponseLimitingMiddleware` truncates responses exceeding `max_size` bytes.

**Step 1: Write the failing test**

```python
# Add to tests/mcp/test_observability.py

async def test_apply_observability_includes_response_limiting():
    """ResponseLimitingMiddleware should be in the stack."""
    from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings())

    # Find ResponseLimiting in the stack
    types = [type(mw).__name__ for mw in mcp.middleware[offset:]]
    assert "ResponseLimitingMiddleware" in types

async def test_response_limiting_respects_config():
    """ResponseLimitingMiddleware should use configured max_size."""
    from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings(mcp_max_response_size=100_000))

    # Find the middleware
    limiting = [
        mw for mw in mcp.middleware[offset:] if isinstance(mw, ResponseLimitingMiddleware)
    ]
    assert len(limiting) == 1
    assert limiting[0].max_size == 100_000
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_observability.py::test_apply_observability_includes_response_limiting -v`
Expected: FAIL (middleware not in stack yet)

**Step 3: Add ResponseLimitingMiddleware to stack**

```python
# app/config.py — add to Settings class
mcp_max_response_size: int = 500_000  # 500KB max response

# app/mcp/observability.py — add import
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware

# In apply_observability(), add AFTER DetailedTimingMiddleware (before caching comment):
    # 4. Response limiting (prevent context overflow)
    mcp.add_middleware(
        ResponseLimitingMiddleware(max_size=settings.mcp_max_response_size)
    )
```

Update the middleware count in existing tests (5 → 6) and reorder indices.

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_observability.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/mcp/observability.py app/config.py tests/mcp/test_observability.py
git commit -m "feat(mcp): add ResponseLimitingMiddleware to prevent context overflow

Configurable via MCP_MAX_RESPONSE_SIZE (default 500KB).
Truncates oversized tool responses before they reach the agent."
```

---

## Task 3: Re-enable ResponseCaching with Selective Settings

**Files:**
- Modify: `app/mcp/observability.py`
- Modify: `app/config.py` (ensure cache settings exist)
- Modify: `tests/mcp/test_observability.py`

The caching middleware is already coded (`observability.py:76-90`) but disabled because it cached `list_tools` responses, hiding newly registered tools. FastMCP's `ResponseCachingMiddleware` supports per-operation TTL settings. Solution: set `list_tools` TTL to 0 (no cache), cache only `call_tool` and `read_resource`.

**Step 1: Write the failing test**

```python
# Add to tests/mcp/test_observability.py

async def test_apply_observability_caching_enabled():
    """ResponseCachingMiddleware should be in the stack."""
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    offset = len(mcp.middleware)
    apply_observability(mcp, _make_settings())

    types = [type(mw).__name__ for mw in mcp.middleware[offset:]]
    assert "ResponseCachingMiddleware" in types
```

**Step 2: Run test — should fail (caching still commented out)**

Run: `uv run pytest tests/mcp/test_observability.py::test_apply_observability_caching_enabled -v`
Expected: FAIL

**Step 3: Uncomment and fix caching middleware**

```python
# app/mcp/observability.py — replace the commented caching block

from fastmcp.server.middleware.caching import (
    CallToolSettings,
    ListToolsSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
from fastmcp.utilities.cache import DiskStore

# Inside apply_observability():

    # 5. Response caching — selective TTLs (list_tools NOT cached)
    cache_store = DiskStore(directory=settings.mcp_cache_dir)
    mcp.add_middleware(
        ResponseCachingMiddleware(
            cache_storage=cache_store,
            call_tool_settings=CallToolSettings(
                ttl=settings.mcp_cache_ttl_tools,
            ),
            read_resource_settings=ReadResourceSettings(
                ttl=settings.mcp_cache_ttl_resources,
            ),
            list_tools_settings=ListToolsSettings(ttl=0),  # NEVER cache tool list
        )
    )
```

**Note:** Verify FastMCP's actual API for `ListToolsSettings`. If it doesn't exist, use a `before_list_tools` hook to bypass caching. Adjust code accordingly based on what FastMCP 3.0 actually provides.

Update middleware count in existing tests (6 → 7).

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_observability.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/mcp/observability.py tests/mcp/test_observability.py
git commit -m "feat(mcp): re-enable ResponseCaching with selective TTLs

list_tools TTL=0 prevents stale tool lists.
call_tool and read_resource cached with configurable TTL."
```

---

## Task 4: Tool Timeouts

**Files:**
- Modify: All `app/mcp/workflows/*_tools.py` files
- Test: `tests/mcp/test_tool_timeouts.py`

Add `timeout=` to every tool decorator. Three tiers:
- **Read tools** (get/list/search): 30s
- **Compute tools** (score, classify, analyze, build, export): 120s
- **I/O tools** (download, sync): 600s (10 min)

**Step 1: Write the failing test**

```python
# tests/mcp/test_tool_timeouts.py
"""Verify all DJ workflow tools have timeout configured."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

@pytest.fixture
def workflow_mcp() -> FastMCP:
    from app.mcp.workflows import create_workflow_mcp

    return create_workflow_mcp()

def test_all_tools_have_timeout(workflow_mcp: FastMCP):
    """Every registered tool must have a non-None timeout."""
    tools = workflow_mcp.get_tools()
    missing = []
    for tool in tools:
        if tool.timeout is None:
            missing.append(tool.name)
    assert not missing, f"Tools without timeout: {missing}"

def test_read_tools_timeout_30s(workflow_mcp: FastMCP):
    """Read-only tools should have 30s timeout."""
    read_tools = {"get_playlist_status", "get_track_details", "classify_tracks",
                  "analyze_library_gaps", "find_similar_tracks", "search_by_criteria"}
    tools = {t.name: t for t in workflow_mcp.get_tools()}
    for name in read_tools:
        if name in tools:
            assert tools[name].timeout == 30.0, f"{name} timeout should be 30s"

def test_compute_tools_timeout_120s(workflow_mcp: FastMCP):
    """Compute tools should have 120s timeout."""
    compute_tools = {"build_set", "rebuild_set", "score_transitions", "review_set",
                     "export_set_m3u", "export_set_json", "export_set_rekordbox"}
    tools = {t.name: t for t in workflow_mcp.get_tools()}
    for name in compute_tools:
        if name in tools:
            assert tools[name].timeout == 120.0, f"{name} timeout should be 120s"

def test_io_tools_timeout_600s(workflow_mcp: FastMCP):
    """I/O-heavy tools should have 600s timeout."""
    io_tools = {"download_tracks", "sync_set_to_ym", "sync_set_from_ym", "sync_playlist",
                "import_playlist", "import_tracks"}
    tools = {t.name: t for t in workflow_mcp.get_tools()}
    for name in io_tools:
        if name in tools:
            assert tools[name].timeout == 600.0, f"{name} timeout should be 600s"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_tool_timeouts.py -v`
Expected: FAIL — all tools have `timeout=None`

**Step 3: Add timeout to every tool decorator**

For each file, add `timeout=N` to the `@mcp.tool()` decorator:

```python
# Read tools (30s):
@mcp.tool(timeout=30.0, annotations={"readOnlyHint": True}, tags={...})

# Compute tools (120s):
@mcp.tool(timeout=120.0, tags={...})

# I/O tools (600s):
@mcp.tool(timeout=600.0, tags={...})
```

Files to modify:
- `app/mcp/workflows/analysis_tools.py` — `get_playlist_status` (30s), `get_track_details` (30s)
- `app/mcp/workflows/discovery_tools.py` — `find_similar_tracks` (120s, uses sampling), `search_by_criteria` (30s)
- `app/mcp/workflows/import_tools.py` — `import_playlist` (600s), `import_tracks` (600s), `download_tracks` (600s)
- `app/mcp/workflows/setbuilder_tools.py` — `build_set` (120s), `rebuild_set` (120s), `score_transitions` (120s), `export_set_m3u` (120s), `export_set_json` (120s)
- `app/mcp/workflows/export_tools.py` — `export_set_m3u` (120s), `export_set_json` (120s), `export_set_rekordbox` (120s)
- `app/mcp/workflows/curation_tools.py` — `classify_tracks` (30s), `analyze_library_gaps` (30s), `review_set` (120s)
- `app/mcp/workflows/sync_tools.py` — all 3 tools (600s)
- `app/mcp/workflows/server.py` — `activate_heavy_mode` (30s)

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_tool_timeouts.py -v`
Expected: ALL PASS

**Step 5: Run full test suite + lint**

Run: `make check`
Expected: PASS

**Step 6: Commit**

```bash
git add app/mcp/workflows/ tests/mcp/test_tool_timeouts.py
git commit -m "feat(mcp): add timeout to all DJ workflow tools

Three tiers: read=30s, compute=120s, I/O=600s.
Prevents runaway tool executions from blocking the agent."
```

---

## Task 5: Background Tasks for Long-Running Operations

**Files:**
- Modify: `app/mcp/workflows/import_tools.py` (download_tracks)
- Modify: `app/mcp/workflows/setbuilder_tools.py` (build_set)
- Test: `tests/mcp/test_background_tasks.py`

**Depends on:** None (can be done before Phases 1-4)

FastMCP's `task=True` decorator makes a tool return a task ID immediately. The client polls for progress via built-in task management. This is ideal for `download_tracks` (minutes) and `build_set` (seconds to minutes).

**Note:** Background tasks require a task backend. FastMCP defaults to in-memory. For production, configure Redis backend via `FastMCP("...", task_backend=RedisTaskBackend(url))`. We use in-memory for now.

**Step 1: Write the failing tests**

```python
# tests/mcp/test_background_tasks.py
"""Tests for background task configuration on long-running tools."""

from __future__ import annotations

from fastmcp import FastMCP

def _get_workflow_mcp() -> FastMCP:
    from app.mcp.workflows import create_workflow_mcp
    return create_workflow_mcp()

def test_download_tracks_is_background_task():
    """download_tracks should be configured as a background task."""
    mcp = _get_workflow_mcp()
    tools = {t.name: t for t in mcp.get_tools()}
    assert "download_tracks" in tools
    # FastMCP stores task config in tool metadata
    tool = tools["download_tracks"]
    assert getattr(tool, "task", None) is not None or hasattr(tool, "_task_config"), (
        "download_tracks must be a background task (task=True)"
    )

def test_build_set_is_background_task():
    """build_set should be configured as a background task."""
    mcp = _get_workflow_mcp()
    tools = {t.name: t for t in mcp.get_tools()}
    assert "build_set" in tools
    tool = tools["build_set"]
    assert getattr(tool, "task", None) is not None or hasattr(tool, "_task_config"), (
        "build_set must be a background task (task=True)"
    )
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_background_tasks.py -v`
Expected: FAIL

**Step 3: Add `task=True` to long-running tools**

Consult FastMCP docs for exact decorator syntax. Expected:

```python
# app/mcp/workflows/import_tools.py — download_tracks
@mcp.tool(task=True, timeout=600.0, tags={"import", "heavy"})
async def download_tracks(
    track_refs: list[str],
    ctx: Context,
    progress: Progress,  # FastMCP injects Progress when task=True
    ...
) -> dict[str, object]:
    # Report progress via progress.set(current, total)
    for i, ref in enumerate(track_refs):
        await progress.set(i, len(track_refs))
        ...
    await progress.set(len(track_refs), len(track_refs))
    return result
```

```python
# app/mcp/workflows/setbuilder_tools.py — build_set
@mcp.tool(task=True, timeout=120.0, tags={"setbuilder"})
async def build_set(
    playlist_id: int,
    set_name: str,
    ctx: Context,
    progress: Progress,
    ...
) -> SetBuildResult:
    await progress.set(0, 100)
    ...
    await progress.set(100, 100)
    return result
```

**Important:** If FastMCP's `task=True` API uses a different pattern (e.g. `Progress` is a `Depends()` dependency), adapt accordingly. Check FastMCP docs: `https://gofastmcp.com/servers/tasks`.

**Step 4: Run tests + full suite**

Run: `uv run pytest tests/mcp/test_background_tasks.py -v && make check`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/mcp/workflows/import_tools.py app/mcp/workflows/setbuilder_tools.py \
       tests/mcp/test_background_tasks.py
git commit -m "feat(mcp): convert download_tracks and build_set to background tasks

task=True enables async execution — client gets task ID immediately,
polls for progress. Prevents timeout on large downloads and GA builds."
```

---

## Task 6: Elicitation for Destructive Operations

**Files:**
- Create: `app/mcp/elicitation.py`
- Modify: `app/mcp/workflows/sync_tools.py` (add confirmation before sync)
- Test: `tests/mcp/test_elicitation.py`

**Depends on:** Phase 3 (sync tools) for full value. Can be implemented now with current stubs.

`ctx.elicit()` prompts the user for confirmation during tool execution. Ideal for:
- Destructive operations (delete track/playlist/set)
- Sync conflict resolution (which version wins?)
- Large batch operations (confirm before downloading 100 tracks)

**Step 1: Write the failing tests**

```python
# tests/mcp/test_elicitation.py
"""Tests for elicitation helper and sync tool confirmation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.elicitation import confirm_action, resolve_conflict

async def test_confirm_action_accepted():
    """confirm_action returns True when user accepts."""
    ctx = MagicMock()
    response = MagicMock()
    response.data = True
    ctx.elicit = AsyncMock(return_value=response)

    result = await confirm_action(
        ctx, message="Delete 5 tracks?", action_description="delete tracks"
    )
    assert result is True
    ctx.elicit.assert_called_once()

async def test_confirm_action_rejected():
    """confirm_action returns False when user declines."""
    ctx = MagicMock()
    response = MagicMock()
    response.data = False
    ctx.elicit = AsyncMock(return_value=response)

    result = await confirm_action(ctx, message="Delete?", action_description="delete")
    assert result is False

async def test_confirm_action_elicitation_not_supported():
    """confirm_action returns True (proceed) when elicitation not supported."""
    ctx = MagicMock()
    ctx.elicit = AsyncMock(side_effect=NotImplementedError)

    result = await confirm_action(ctx, message="Delete?", action_description="delete")
    assert result is True  # default: proceed if client doesn't support elicitation

async def test_resolve_conflict_returns_choice():
    """resolve_conflict returns user's chosen strategy."""
    from enum import Enum

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
        message="Track 'X' differs between local and YM. Which version to keep?",
        options=Strategy,
    )
    assert result == Strategy.LOCAL_WINS
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_elicitation.py -v`
Expected: FAIL (module doesn't exist)

**Step 3: Create elicitation helpers**

```python
# app/mcp/elicitation.py
"""Reusable elicitation helpers for DJ workflow tools.

Uses FastMCP's ctx.elicit() to prompt users for confirmation
or conflict resolution during tool execution.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

async def confirm_action(
    ctx: Context,
    *,
    message: str,
    action_description: str,
) -> bool:
    """Ask user to confirm a destructive or significant action.

    Returns True if user confirms or if elicitation is not supported
    by the client (fail-open for non-interactive clients).
    """
    try:
        response = await ctx.elicit(message=message, response_type=bool)
        confirmed = bool(response.data)
        if not confirmed:
            await ctx.info(f"Action cancelled by user: {action_description}")
        return confirmed
    except (NotImplementedError, AttributeError, Exception):
        logger.debug("Elicitation not supported, proceeding with action: %s", action_description)
        return True

async def resolve_conflict[T: Enum](
    ctx: Context,
    *,
    message: str,
    options: type[T],
) -> T:
    """Ask user to choose between conflict resolution strategies.

    Falls back to first enum value if elicitation is not supported.
    """
    try:
        response = await ctx.elicit(message=message, response_type=options)
        return response.data
    except (NotImplementedError, AttributeError, Exception):
        default = list(options)[0]
        logger.debug("Elicitation not supported, using default: %s", default)
        return default
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_elicitation.py -v`
Expected: ALL PASS

**Step 5: Integrate into sync_set_from_ym (example)**

```python
# app/mcp/workflows/sync_tools.py — in sync_set_from_ym, before applying changes:

from app.mcp.elicitation import confirm_action

# After computing what would change:
confirmed = await confirm_action(
    ctx,
    message=f"Sync will pin {pinned_count} and exclude {excluded_count} tracks. Proceed?",
    action_description=f"sync feedback for set {set_id}",
)
if not confirmed:
    return {"set_id": set_id, "status": "cancelled"}
```

**Step 6: Run full suite + lint**

Run: `make check`
Expected: PASS

**Step 7: Commit**

```bash
git add app/mcp/elicitation.py tests/mcp/test_elicitation.py app/mcp/workflows/sync_tools.py
git commit -m "feat(mcp): add elicitation helpers for confirmation and conflict resolution

confirm_action() for destructive ops, resolve_conflict() for sync.
Fails open for non-interactive clients (no elicitation support)."
```

---

## Task 7: Session State for Workflow Continuity

**Files:**
- Create: `app/mcp/session_state.py`
- Test: `tests/mcp/test_session_state.py`

**Depends on:** Phase 2 (CRUD tools benefit most from state)

`ctx.set_state()`/`ctx.get_state()` persist data across MCP requests within a session. Use cases:
- Remember last built set ID → agent can `score_transitions` without re-specifying
- Remember last export format → agent can repeat with same settings
- Track workflow progress → "you analyzed 50/100 tracks, continue?"

**Step 1: Write the failing tests**

```python
# tests/mcp/test_session_state.py
"""Tests for session state helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.mcp.session_state import (
    get_last_build,
    get_last_playlist,
    save_build_result,
    save_playlist_context,
)

async def test_save_and_get_build_result():
    """save_build_result stores data retrievable by get_last_build."""
    ctx = MagicMock()
    state: dict[str, object] = {}
    ctx.set_state = AsyncMock(side_effect=lambda k, v: state.update({k: v}))
    ctx.get_state = AsyncMock(side_effect=lambda k, default=None: state.get(k, default))

    await save_build_result(ctx, set_id=42, version_id=7, track_count=15)
    result = await get_last_build(ctx)

    assert result is not None
    assert result["set_id"] == 42
    assert result["version_id"] == 7
    assert result["track_count"] == 15

async def test_get_last_build_returns_none_initially():
    """get_last_build returns None when no build has been saved."""
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=None)

    result = await get_last_build(ctx)
    assert result is None

async def test_save_and_get_playlist_context():
    """Playlist context persists across calls."""
    ctx = MagicMock()
    state: dict[str, object] = {}
    ctx.set_state = AsyncMock(side_effect=lambda k, v: state.update({k: v}))
    ctx.get_state = AsyncMock(side_effect=lambda k, default=None: state.get(k, default))

    await save_playlist_context(ctx, playlist_id=10, playlist_name="Techno develop")
    result = await get_last_playlist(ctx)

    assert result is not None
    assert result["playlist_id"] == 10
    assert result["playlist_name"] == "Techno develop"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_session_state.py -v`
Expected: FAIL (module doesn't exist)

**Step 3: Create session state helpers**

```python
# app/mcp/session_state.py
"""Session state helpers for DJ workflow continuity.

Uses FastMCP's ctx.set_state()/ctx.get_state() to persist data
across MCP requests within a single session. Enables "continue
where I left off" patterns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

# State keys
_LAST_BUILD = "dj:last_build"
_LAST_PLAYLIST = "dj:last_playlist"
_LAST_EXPORT = "dj:last_export"
_WORKFLOW_PROGRESS = "dj:workflow_progress"

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
    """Retrieve the last build result from session state."""
    return await ctx.get_state(_LAST_BUILD, default=None)

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
    return await ctx.get_state(_LAST_PLAYLIST, default=None)

async def save_export_config(
    ctx: Context,
    *,
    format: str,
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
    return await ctx.get_state(_LAST_EXPORT, default=None)
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_session_state.py -v`
Expected: ALL PASS

**Step 5: Wire into build_set tool (example)**

```python
# app/mcp/workflows/setbuilder_tools.py — at end of build_set:

from app.mcp.session_state import save_build_result

# After creating result:
await save_build_result(
    ctx, set_id=dj_set.set_id, version_id=gen_result.set_version_id,
    track_count=len(gen_result.track_ids),
)
```

**Step 6: Run full suite + lint**

Run: `make check`
Expected: PASS

**Step 7: Commit**

```bash
git add app/mcp/session_state.py tests/mcp/test_session_state.py \
       app/mcp/workflows/setbuilder_tools.py
git commit -m "feat(mcp): add session state helpers for workflow continuity

Persist last build/playlist/export across MCP requests.
Enables 'continue where I left off' patterns for the agent."
```

---

## Task 8: Structured Output (ToolResult)

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py` (score_transitions)
- Modify: `app/mcp/workflows/export_tools.py` (export tools)
- Test: `tests/mcp/test_structured_output.py`

**Depends on:** Phase 1 types_v2 for full benefit. Can prototype with existing types.

FastMCP's `ToolResult` returns both human-readable content and machine-readable structured data. Perfect for tools where the agent needs parsed data AND the user needs a readable summary.

**Step 1: Write the failing test**

```python
# tests/mcp/test_structured_output.py
"""Tests for structured output in DJ workflow tools."""

from __future__ import annotations

from fastmcp.server.tool import ToolResult

def test_tool_result_has_both_content_types():
    """ToolResult should contain both text content and structured data."""
    result = ToolResult(
        content="Score: 0.85 (15 transitions, 2 weak)",
        structured_content={"avg_score": 0.85, "total": 15, "weak_count": 2},
    )
    assert result.content == "Score: 0.85 (15 transitions, 2 weak)"
    assert result.structured_content["avg_score"] == 0.85

def test_tool_result_meta():
    """ToolResult can carry metadata."""
    result = ToolResult(
        content="Exported",
        structured_content={"format": "m3u8", "path": "/tmp/set.m3u8"},
        meta={"execution_ms": 150},
    )
    assert result.meta["execution_ms"] == 150
```

**Step 2: Run tests to verify they pass (ToolResult is FastMCP built-in)**

Run: `uv run pytest tests/mcp/test_structured_output.py -v`
Expected: PASS (ToolResult exists in FastMCP)

**Step 3: Convert score_transitions to use ToolResult**

```python
# app/mcp/workflows/setbuilder_tools.py — score_transitions return

from fastmcp.server.tool import ToolResult

# At end of score_transitions, replace `return results` with:
    # Build human-readable summary
    avg = sum(r.total for r in results) / len(results) if results else 0.0
    weak = [r for r in results if r.total < 0.4]
    summary_lines = [f"## Transitions: {len(results)} pairs, avg {avg:.3f}"]
    if weak:
        summary_lines.append(f"### ⚠ {len(weak)} weak (< 0.4):")
        for w in weak:
            summary_lines.append(f"- {w.from_title} → {w.to_title}: {w.total:.3f}")

    return ToolResult(
        content="\n".join(summary_lines),
        structured_content=[r.model_dump() for r in results],
    )
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_structured_output.py tests/mcp/test_workflow_setbuilder.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py tests/mcp/test_structured_output.py
git commit -m "feat(mcp): use ToolResult structured output for score_transitions

Returns human-readable summary + machine-readable structured data.
Agent gets parsed scores, user sees formatted transition report."
```

---

## Task 9: Tool Versioning

**Files:**
- Modify: All `app/mcp/workflows/*_tools.py`
- Test: `tests/mcp/test_tool_versions.py`

Add `version="1.0.0"` to all stable tools, `version="0.1.0"` to experimental/stub tools. Enables future API evolution without breaking existing agent behavior.

**Step 1: Write the failing test**

```python
# tests/mcp/test_tool_versions.py
"""Verify all DJ workflow tools have version set."""

from __future__ import annotations

from packaging.version import Version

from fastmcp import FastMCP

def test_all_tools_have_version():
    """Every registered tool must have a version string."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = mcp.get_tools()
    missing = [t.name for t in tools if not getattr(t, "version", None)]
    assert not missing, f"Tools without version: {missing}"

def test_stable_tools_are_v1():
    """Stable tools should be version 1.x."""
    from app.mcp.workflows import create_workflow_mcp

    stable_tools = {
        "build_set", "rebuild_set", "score_transitions",
        "export_set_m3u", "export_set_json", "export_set_rekordbox",
        "classify_tracks", "analyze_library_gaps", "review_set",
        "download_tracks", "find_similar_tracks",
    }
    mcp = create_workflow_mcp()
    tools = {t.name: t for t in mcp.get_tools()}
    for name in stable_tools:
        if name in tools:
            v = Version(tools[name].version)
            assert v.major >= 1, f"{name} should be v1.x, got {v}"

def test_stub_tools_are_v0():
    """Stub/experimental tools should be version 0.x."""
    from app.mcp.workflows import create_workflow_mcp

    stub_tools = {
        "sync_set_to_ym", "sync_set_from_ym", "sync_playlist",
        "import_playlist", "import_tracks",
    }
    mcp = create_workflow_mcp()
    tools = {t.name: t for t in mcp.get_tools()}
    for name in stub_tools:
        if name in tools:
            v = Version(tools[name].version)
            assert v.major == 0, f"{name} should be v0.x (stub), got {v}"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_tool_versions.py -v`
Expected: FAIL (no version on any tool)

**Step 3: Add version to every tool decorator**

```python
# Stable tools:
@mcp.tool(version="1.0.0", ...)

# Stub/experimental tools:
@mcp.tool(version="0.1.0", ...)
```

Same files as Task 4 (timeouts). Can be done in the same pass.

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_tool_versions.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/mcp/workflows/ tests/mcp/test_tool_versions.py
git commit -m "feat(mcp): add version tags to all DJ workflow tools

Stable tools v1.0.0, stubs v0.1.0. Enables future API evolution
with backward-compatible filtering via VersionFilter."
```

---

## Task 10: Integration Smoke Test

**Files:**
- Create: `tests/mcp/test_platform_features_smoke.py`

End-to-end verification that all Phase 5 features work together.

**Step 1: Write the integration test**

```python
# tests/mcp/test_platform_features_smoke.py
"""Smoke test — all Phase 5 platform features work together."""

from __future__ import annotations

from fastmcp import FastMCP

from app.config import Settings

def _make_settings(**overrides: object) -> Settings:
    defaults = {
        "_env_file": None,
        "yandex_music_token": "t",
        "yandex_music_user_id": "u",
    }
    return Settings(**(defaults | overrides))  # type: ignore[arg-type]

async def test_middleware_stack_complete():
    """Full middleware stack should have 7 components."""
    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    before = len(mcp.middleware)
    apply_observability(mcp, _make_settings())
    added = len(mcp.middleware) - before
    # ErrorHandling + StructuredLogging + DetailedTiming + ResponseLimiting
    # + ResponseCaching + Retry + Ping = 7
    assert added == 7, f"Expected 7 middleware, got {added}"

async def test_all_tools_have_timeout_and_version():
    """Every tool should have both timeout and version."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()
    tools = mcp.get_tools()
    issues = []
    for tool in tools:
        if tool.timeout is None:
            issues.append(f"{tool.name}: missing timeout")
        if not getattr(tool, "version", None):
            issues.append(f"{tool.name}: missing version")
    assert not issues, f"Tool configuration issues:\n" + "\n".join(issues)

async def test_otel_init_smoke():
    """OTLP init should not crash with empty endpoint."""
    from app.mcp.lifespan import _init_otel

    result = _init_otel(otel_endpoint="", service_name="test")
    assert result is None

async def test_elicitation_helpers_importable():
    """Elicitation module should be importable."""
    from app.mcp.elicitation import confirm_action, resolve_conflict

    assert callable(confirm_action)
    assert callable(resolve_conflict)

async def test_session_state_helpers_importable():
    """Session state module should be importable."""
    from app.mcp.session_state import (
        get_last_build,
        get_last_playlist,
        save_build_result,
        save_playlist_context,
    )

    assert callable(save_build_result)
    assert callable(get_last_build)
    assert callable(save_playlist_context)
    assert callable(get_last_playlist)
```

**Step 2: Run the smoke test**

Run: `uv run pytest tests/mcp/test_platform_features_smoke.py -v`
Expected: ALL PASS

**Step 3: Run full test suite**

Run: `make check`
Expected: ALL PASS — 750+ tests, lint clean, mypy clean

**Step 4: Commit**

```bash
git add tests/mcp/test_platform_features_smoke.py
git commit -m "test(mcp): add Phase 5 platform features smoke test

Verifies middleware stack, tool config, OTEL, elicitation,
and session state all work together."
```

---

## Summary

| Task | Feature | New/Modify | Lines est. |
|------|---------|-----------|------------|
| 1 | OpenTelemetry OTLP exporter | Modify lifespan.py + config.py | ~80 |
| 2 | ResponseLimitingMiddleware | Modify observability.py + config.py | ~20 |
| 3 | ResponseCaching re-enable | Modify observability.py | ~20 |
| 4 | Tool timeouts (all tools) | Modify 7 tool files | ~30 (1 line × 25 tools) |
| 5 | Background tasks | Modify import + setbuilder tools | ~40 |
| 6 | Elicitation helpers | Create elicitation.py | ~60 |
| 7 | Session state helpers | Create session_state.py | ~70 |
| 8 | Structured output (ToolResult) | Modify setbuilder_tools.py | ~30 |
| 9 | Tool versioning (all tools) | Modify 7 tool files | ~25 (1 line × 25 tools) |
| 10 | Integration smoke test | Create test file | ~60 |

**Total estimated:** ~435 lines of code, ~200 lines of tests

**Execution order:** Tasks 1-3 (infrastructure), then 4+9 together (decorator sweep), then 5-8 (features), then 10 (smoke test).

**Amendments to Phases 1-4:**
- **Phase 1:** When creating `types_v2.py`, consider `ToolResult` structured output format
- **Phase 2:** Add `save_build_result()` / `save_playlist_context()` calls in new CRUD tools
- **Phase 3:** Use `confirm_action()` / `resolve_conflict()` in SyncEngine tools
- **Phase 4:** During legacy cleanup, ensure all surviving tools have timeout + version + session state wiring
