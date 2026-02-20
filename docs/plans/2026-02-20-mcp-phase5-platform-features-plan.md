# Phase 5: FastMCP Platform Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add observability (OTEL), response safety (limiting, caching), tool timeouts,
elicitation helpers, and session state — leveraging FastMCP 3.0 platform capabilities.

**Architecture:** All features hook into the existing `observability.py` middleware stack
and `lifespan.py` lifecycle. New helpers are standalone modules (`elicitation.py`,
`session_state.py`) imported only by tools that need them.

**Tech Stack:** Python 3.12, FastMCP 3.0.0rc2+, opentelemetry-api, Pydantic v2

**Prerequisite:** Phase 4 must be complete (tool names stabilized, `types.py` deleted).

---

## Decision Log (resolving review blockers)

| Blocker | Decision |
|---------|----------|
| Background tasks (`docket` missing) | **EXCLUDED** from Phase 5 entirely |
| ResponseLimiting drops structured output | **Scope to YM tools only** (raw API, no Pydantic return) |
| ResponseCaching unsafe for session-specific visibility | **Disable `list_tools` caching**, cache only `read_resource` |
| `get_tools()` non-existent | **Use `await mcp.list_tools()`** (async) |
| Elicitation fails open | **Fail-closed** for destructive ops, explicit type checks |
| Session state `default=` not supported | **Use `await ctx.get_state(key)`, handle `None` explicitly** |
| OTEL vs Sentry TracerProvider | **Check existing provider before setting** |
| Hardcoded tool names in policies | **Tag-based policies** (`readOnlyHint`, `sync`, `download`) |
| ToolResult wrong imports | **Verify actual FastMCP API before writing code** |

---

### Task 1: Verify FastMCP 3.0 API surface

**Rationale:** The original plan assumed FastMCP APIs that don't exist in rc2.
Before writing code, verify every API we plan to use.

**Files:**
- None (research only)

**Step 1: Check available middleware**

```bash
uv run python -c "
from fastmcp.server.middleware import error_handling, logging, timing, ping
print('ErrorHandling:', hasattr(error_handling, 'ErrorHandlingMiddleware'))
print('ResponseLimiting:', hasattr(error_handling, 'ResponseLimitingMiddleware'))
print('ResponseCaching:', hasattr(error_handling, 'ResponseCachingMiddleware'))
"
```

**Step 2: Check elicitation API**

```bash
uv run python -c "
from fastmcp.server.context import Context
import inspect
sig = inspect.signature(Context.elicit)
print('elicit params:', list(sig.parameters.keys()))
"
```

**Step 3: Check session state API**

```bash
uv run python -c "
from fastmcp.server.context import Context
print('set_state:', hasattr(Context, 'set_state'))
print('get_state:', hasattr(Context, 'get_state'))
"
```

**Step 4: Document findings**

Create `docs/plans/2026-02-20-fastmcp-api-verification.md` with actual APIs.

**Step 5: Commit**

```bash
git add -A && git commit -m "docs: verify FastMCP 3.0 API surface for Phase 5"
```

---

### Task 2: Wire OpenTelemetry OTLP exporter

**Rationale:** Add OTEL tracing to MCP operations. Must be Sentry-safe.

**Files:**
- Modify: `app/config.py` (add `otel_endpoint`, `otel_insecure` settings)
- Modify: `app/mcp/lifespan.py` (add `_init_otel()`, `_shutdown_otel()`)
- Create: `tests/mcp/test_otel.py`

**Step 1: Write failing test**

```python
"""Tests for OTEL initialization."""
from __future__ import annotations

from unittest.mock import patch

import pytest

async def test_otel_not_initialized_without_endpoint(tmp_path):
    """OTEL should be no-op when otel_endpoint is not set."""
    from app.mcp.lifespan import _init_otel

    with patch("app.config.settings") as mock_settings:
        mock_settings.otel_endpoint = None
        result = _init_otel()
        assert result is None

async def test_otel_respects_existing_tracer_provider():
    """OTEL init should not override existing TracerProvider (e.g. Sentry)."""
    from opentelemetry import trace

    from app.mcp.lifespan import _init_otel

    existing = trace.get_tracer_provider()
    # If Sentry already set a provider, _init_otel should detect it
    # and not replace it (or add to it via composite)
    with patch("app.config.settings") as mock_settings:
        mock_settings.otel_endpoint = None  # disabled
        _init_otel()
        assert trace.get_tracer_provider() is existing
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_otel.py -v
```

Expected: FAIL — `_init_otel` does not exist.

**Step 3: Implement `_init_otel()` in `lifespan.py`**

```python
def _init_otel() -> object | None:
    """Initialize OTEL tracing if configured. Returns TracerProvider or None."""
    from app.config import settings

    if not settings.otel_endpoint:
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    # Don't override existing provider (Sentry may have set one)
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        logger.info("OTEL: existing TracerProvider found, adding processor")
        provider = current
    else:
        provider = TracerProvider()
        trace.set_tracer_provider(provider)

    exporter = OTLPSpanExporter(
        endpoint=settings.otel_endpoint,
        insecure=settings.otel_insecure,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    logger.info("OTEL tracing initialized", extra={"endpoint": settings.otel_endpoint})
    return provider

def _shutdown_otel(provider: object | None) -> None:
    """Shutdown OTEL provider if initialized."""
    if provider is not None and hasattr(provider, "shutdown"):
        provider.shutdown()
```

**Step 4: Add settings to `config.py`**

```python
otel_endpoint: str | None = None
otel_insecure: bool = True  # for local dev
```

**Step 5: Wire into lifespan**

Add to the existing lifespan context manager:
- Call `_init_otel()` in startup
- Call `_shutdown_otel(provider)` in shutdown

**Step 6: Run tests**

```bash
uv run pytest tests/mcp/test_otel.py -v
```

Expected: PASS

**Step 7: Commit**

```bash
git add -A && git commit -m "feat(mcp): wire OpenTelemetry OTLP exporter (Sentry-safe)"
```

---

### Task 3: Add ResponseLimiting (YM tools only)

**Rationale:** YM raw API tools can return huge responses. Limit only those,
not DJ namespace tools (which return structured Pydantic output).

**Files:**
- Modify: `app/config.py` (add `mcp_max_response_size`)
- Modify: `app/mcp/observability.py`
- Create: `tests/mcp/test_response_limiting.py`

**Step 1: Write failing test**

Test that ResponseLimitingMiddleware is applied (if available in FastMCP).

**Step 2: Implement**

Add to `apply_observability()` — but ONLY if FastMCP provides the middleware.
If not available, skip gracefully.

**NOTE:** This task depends on Task 1 API verification. If ResponseLimitingMiddleware
is not available in FastMCP rc2, skip this task and document in the API verification doc.

**Step 3: Run tests**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(mcp): add ResponseLimiting for YM raw tools (safe for structured output)"
```

---

### Task 4: Re-enable ResponseCaching (safe settings)

**Rationale:** Caching was disabled because `list_tools` cache hid newly registered tools.
Re-enable with safe settings: no `list_tools` caching, only `read_resource`.

**Files:**
- Modify: `app/mcp/observability.py`
- Modify: `tests/mcp/test_observability.py`

**Step 1: Write test**

```python
async def test_response_caching_does_not_cache_list_tools():
    """ResponseCaching must not cache list_tools (session-specific visibility)."""
    # Verify caching config excludes list_tools
    ...
```

**Step 2: Implement**

Uncomment and fix the ResponseCaching section in `observability.py`:
- `list_tools_settings={"enabled": False}` (or equivalent API)
- `call_tool_settings={"enabled": False}` (non-idempotent tools)
- `read_resource_settings={"ttl": settings.mcp_cache_ttl_resources}`

**NOTE:** Depends on Task 1 API verification.

**Step 3: Run tests**

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(mcp): re-enable ResponseCaching (read_resource only, safe settings)"
```

---

### Task 5: Tool timeouts + versioning (tag-based)

**Rationale:** Add timeout tiers based on tool tags, not hardcoded names.
After Phase 4, tool names are stable.

**Files:**
- Modify: `app/mcp/workflows/server.py` (or individual tool files)
- Create: `tests/mcp/test_tool_timeouts.py`

**Step 1: Define timeout tiers**

```python
# In server.py or a constants module
TIMEOUT_TIERS = {
    "read": 30,      # readOnlyHint tools
    "compute": 120,  # scoring, analysis
    "io": 600,       # download, sync
}
```

**Step 2: Write test**

```python
async def test_download_tracks_has_io_timeout(workflow_mcp: FastMCP):
    """I/O tools should have 600s timeout."""
    tools = await workflow_mcp.list_tools()
    tool = next(t for t in tools if t.name == "download_tracks")
    # Check timeout metadata (depends on FastMCP API)
    ...
```

**Step 3: Apply timeouts to tools**

If FastMCP supports `timeout` parameter in `@mcp.tool()`:
```python
@mcp.tool(tags={"download"}, timeout=600)
```

If not, implement a wrapper/middleware approach.

**Step 4: Add version tags**

All tools get `version="1.0.0"` tag (or metadata annotation).

**Step 5: Run tests**

**Step 6: Commit**

```bash
git add -A && git commit -m "feat(mcp): add tool timeouts (3 tiers) and version tags"
```

---

### Task 6: Elicitation helpers (fail-closed)

**Rationale:** Destructive operations (sync, delete) should ask for confirmation.
Must fail-closed on decline/cancel.

**Files:**
- Create: `app/mcp/elicitation.py`
- Create: `tests/mcp/test_elicitation.py`

**Step 1: Write failing test**

```python
"""Tests for elicitation helpers."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

async def test_confirm_action_returns_false_on_decline():
    """confirm_action must return False when user declines."""
    from app.mcp.elicitation import confirm_action

    ctx = AsyncMock()
    # Simulate decline
    ctx.elicit.return_value = MagicMock(accepted=False)
    result = await confirm_action(ctx, "Delete all tracks?")
    assert result is False

async def test_confirm_action_returns_true_on_accept():
    """confirm_action must return True when user accepts."""
    from app.mcp.elicitation import confirm_action

    ctx = AsyncMock()
    ctx.elicit.return_value = MagicMock(accepted=True, data={"confirmed": True})
    result = await confirm_action(ctx, "Delete all tracks?")
    assert result is True

async def test_confirm_action_graceful_degradation():
    """confirm_action returns False when elicitation not supported."""
    from app.mcp.elicitation import confirm_action

    ctx = AsyncMock()
    ctx.elicit.side_effect = NotImplementedError
    result = await confirm_action(ctx, "Delete?")
    assert result is False  # fail-closed
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/test_elicitation.py -v
```

**Step 3: Implement `elicitation.py`**

```python
"""Elicitation helpers for destructive MCP operations.

Fail-closed: if elicitation fails or user declines, return False.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

async def confirm_action(ctx: Context, message: str) -> bool:
    """Ask user to confirm a destructive action. Fail-closed on error/decline."""
    try:
        result = await ctx.elicit(message=message)

        # Check for accepted vs declined/cancelled
        if hasattr(result, "accepted") and result.accepted:
            return True

        logger.info("User declined action: %s", message)
        return False

    except (NotImplementedError, AttributeError, TypeError) as exc:
        logger.warning("Elicitation not supported: %s", exc)
        return False  # fail-closed

async def resolve_conflict(
    ctx: Context,
    description: str,
    options: list[str],
) -> str | None:
    """Ask user to resolve a conflict. Returns chosen option or None."""
    try:
        result = await ctx.elicit(
            message=f"{description}\nOptions: {', '.join(options)}",
        )
        if hasattr(result, "accepted") and result.accepted:
            return getattr(result, "data", {}).get("choice")
        return None
    except (NotImplementedError, AttributeError, TypeError):
        return None
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_elicitation.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat(mcp): add elicitation helpers (fail-closed for destructive ops)"
```

---

### Task 7: Session state helpers

**Rationale:** Workflow continuity — save build results, playlist context, export config
so agents can reference previous operations.

**Files:**
- Create: `app/mcp/session_state.py`
- Create: `tests/mcp/test_session_state.py`

**Step 1: Write failing test**

```python
"""Tests for session state helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

async def test_save_and_get_build_result():
    """Can save and retrieve build result from session state."""
    from app.mcp.session_state import get_last_build, save_build_result

    ctx = AsyncMock()
    state = {}
    ctx.set_state = AsyncMock(side_effect=lambda k, v: state.update({k: v}))
    ctx.get_state = AsyncMock(side_effect=lambda k: state.get(k))

    await save_build_result(ctx, set_id=1, version_id=2, quality=0.85)
    result = await get_last_build(ctx)
    assert result is not None
    assert result["set_id"] == 1
    assert result["quality"] == 0.85

async def test_get_last_build_returns_none_when_empty():
    """get_last_build returns None when no build has been saved."""
    from app.mcp.session_state import get_last_build

    ctx = AsyncMock()
    ctx.get_state = AsyncMock(return_value=None)
    result = await get_last_build(ctx)
    assert result is None
```

**Step 2: Run test to verify it fails**

**Step 3: Implement `session_state.py`**

```python
"""Session state helpers for MCP workflow continuity.

Provides typed save/get for common workflow artifacts.
Handles None return from ctx.get_state() (no default= parameter).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

_KEY_LAST_BUILD = "last_build"
_KEY_LAST_PLAYLIST = "last_playlist"
_KEY_LAST_EXPORT = "last_export"

async def save_build_result(
    ctx: Context,
    *,
    set_id: int,
    version_id: int,
    quality: float,
) -> None:
    """Save build result to session state."""
    await ctx.set_state(_KEY_LAST_BUILD, {
        "set_id": set_id,
        "version_id": version_id,
        "quality": quality,
    })

async def get_last_build(ctx: Context) -> dict[str, Any] | None:
    """Get last build result from session state. Returns None if not set."""
    result = await ctx.get_state(_KEY_LAST_BUILD)
    return result if isinstance(result, dict) else None

async def save_playlist_context(
    ctx: Context,
    *,
    playlist_id: int,
    name: str,
    track_count: int,
) -> None:
    """Save playlist context for workflow continuity."""
    await ctx.set_state(_KEY_LAST_PLAYLIST, {
        "playlist_id": playlist_id,
        "name": name,
        "track_count": track_count,
    })

async def get_last_playlist(ctx: Context) -> dict[str, Any] | None:
    """Get last playlist context. Returns None if not set."""
    result = await ctx.get_state(_KEY_LAST_PLAYLIST)
    return result if isinstance(result, dict) else None

async def save_export_config(
    ctx: Context,
    *,
    set_id: int,
    format: str,
    track_count: int,
) -> None:
    """Save export config for repeat exports."""
    await ctx.set_state(_KEY_LAST_EXPORT, {
        "set_id": set_id,
        "format": format,
        "track_count": track_count,
    })

async def get_last_export(ctx: Context) -> dict[str, Any] | None:
    """Get last export config. Returns None if not set."""
    result = await ctx.get_state(_KEY_LAST_EXPORT)
    return result if isinstance(result, dict) else None
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/test_session_state.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat(mcp): add session state helpers for workflow continuity"
```

---

### Task 8: Wire helpers into existing tools

**Rationale:** Connect elicitation and session state to tools that need them.

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py` (save build result to session)
- Modify: `app/mcp/workflows/sync_tools.py` (confirm before destructive sync)
- Modify: `app/mcp/workflows/export_tools.py` (save export config)

**Step 1: Wire `build_set` to save session state**

In `setbuilder_tools.py`, after a successful build:
```python
from app.mcp.session_state import save_build_result

# At end of build_set:
await save_build_result(ctx, set_id=..., version_id=..., quality=...)
```

**Step 2: Wire `sync_playlist` to confirm before prune**

In `sync_tools.py`, before deleting remote tracks:
```python
from app.mcp.elicitation import confirm_action

# Before pruning tracks that exist remotely but not locally:
if diff.to_remove:
    confirmed = await confirm_action(
        ctx, f"Remove {len(diff.to_remove)} tracks from remote playlist?"
    )
    if not confirmed:
        return {"status": "cancelled", "reason": "user declined prune"}
```

**Step 3: Run affected tests**

```bash
uv run pytest tests/mcp/test_workflow_setbuilder.py tests/mcp/test_workflow_sync.py -v
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat(mcp): wire elicitation + session state into tools"
```

---

### Task 9: Lint + type-check + full verification

**Files:** None (verification only)

**Step 1: Lint**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run ruff format --check app/mcp/ tests/mcp/
```

**Step 2: Type-check**

```bash
uv run mypy app/mcp/
```

**Step 3: Full test suite**

```bash
uv run pytest -v --tb=short
```

Expected: ALL PASS

**Step 4: Middleware stack verification**

```bash
uv run python -c "
from app.mcp.gateway import create_dj_mcp
mcp = create_dj_mcp()
print(f'Middleware count: {len(mcp._middleware_stack) if hasattr(mcp, \"_middleware_stack\") else \"N/A\"}')
"
```

**Step 5: Commit**

```bash
git add -A && git commit -m "chore(mcp): Phase 5 complete — OTEL, caching, elicitation, session state"
```

---

## Summary

| Task | Feature | New files |
|------|---------|-----------|
| 1 | API verification | `docs/plans/2026-02-20-fastmcp-api-verification.md` |
| 2 | OTEL tracing | `tests/mcp/test_otel.py` |
| 3 | Response limiting | `tests/mcp/test_response_limiting.py` |
| 4 | Response caching | (modify existing) |
| 5 | Tool timeouts | `tests/mcp/test_tool_timeouts.py` |
| 6 | Elicitation | `app/mcp/elicitation.py`, `tests/mcp/test_elicitation.py` |
| 7 | Session state | `app/mcp/session_state.py`, `tests/mcp/test_session_state.py` |
| 8 | Integration wiring | (modify existing tools) |
| 9 | Verification | (none) |

**EXCLUDED:** Background tasks (Task 5 from original plan — blocked by missing `docket` dep)

**Estimated time:** 3-4 hours
**Risk:** Medium — FastMCP API may differ from assumptions, Task 1 resolves this
**Dependencies:** Phase 4 must be complete first (stable tool names)
