# MCP Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add full observability to the FastMCP server: middleware stack, Sentry error tracking, OpenTelemetry tracing, structured logging, response caching, and lifespan management.

**Architecture:** Centralized `app/mcp/observability.py` module applies all middleware to the gateway. Sentry init in `app/main.py` before FastMCP import. DiskStore for response caching. Settings in `app/config.py` control all features via env vars.

**Tech Stack:** FastMCP 3.0.0rc1, sentry-sdk[fastapi] >=2.50, opentelemetry-exporter-otlp, py-key-value-aio (DiskStore)

**Design doc:** `docs/plans/2026-02-15-mcp-observability-design.md`

---

### Task 1: Add dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:6-15` (dependencies list)
- Modify: `pyproject.toml:73-74` (mypy overrides)

**Step 1: Add new dependencies**

Add to `[project.optional-dependencies]` a new group `observability`:

```toml
observability = [
    "sentry-sdk[fastapi]>=2.50",
    "opentelemetry-exporter-otlp>=1.29",
]
```

Note: `opentelemetry-api`, `opentelemetry-sdk`, `py-key-value-aio` (DiskStore) are already transitive deps of `fastmcp>=3.0.0rc1`. Only `sentry-sdk` and the OTLP exporter need explicit addition.

**Step 2: Add mypy override for sentry_sdk**

Append to the mypy overrides section:

```toml
[[tool.mypy.overrides]]
module = ["sentry_sdk.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["opentelemetry.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["key_value.*"]
ignore_missing_imports = true
```

**Step 3: Install and verify**

Run: `uv sync --extra observability`
Expected: All deps install without errors.

Run: `python3 -c "from sentry_sdk.integrations.mcp import MCPIntegration; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add observability dependencies (sentry, otel, disk cache)"
```

---

### Task 2: Add observability settings to config

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py` (create if not exists)

**Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Tests for observability settings defaults and env override."""

from app.config import Settings

def test_sentry_defaults():
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.sentry_dsn == ""
    assert s.sentry_traces_sample_rate == 1.0
    assert s.sentry_send_pii is True
    assert s.environment == "development"

def test_otel_defaults():
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.otel_endpoint == ""
    assert s.otel_service_name == "dj-set-builder-mcp"

def test_mcp_observability_defaults():
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    assert s.mcp_cache_dir == "./cache/mcp"
    assert s.mcp_cache_ttl_tools == 60
    assert s.mcp_cache_ttl_resources == 300
    assert s.mcp_retry_max == 3
    assert s.mcp_retry_backoff == 1.0
    assert s.mcp_ping_interval == 30
    assert s.mcp_log_payloads is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — fields don't exist yet.

**Step 3: Add settings to app/config.py**

Add these fields to `Settings` class after existing fields:

```python
    # Sentry
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 1.0
    sentry_send_pii: bool = True
    environment: str = "development"

    # OpenTelemetry
    otel_endpoint: str = ""
    otel_service_name: str = "dj-set-builder-mcp"

    # MCP Observability
    mcp_cache_dir: str = "./cache/mcp"
    mcp_cache_ttl_tools: int = 60
    mcp_cache_ttl_resources: int = 300
    mcp_retry_max: int = 3
    mcp_retry_backoff: float = 1.0
    mcp_ping_interval: int = 30
    mcp_log_payloads: bool = False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 tests PASS.

**Step 5: Run full lint**

Run: `make lint`
Expected: Clean.

**Step 6: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add observability settings (sentry, otel, cache, middleware)"
```

---

### Task 3: Add cache/mcp to .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: Add cache directory to .gitignore**

Append before `# In-Memoria` section:

```gitignore
# MCP response cache (DiskStore)
cache/
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore MCP cache directory"
```

---

### Task 4: Create app/mcp/observability.py — middleware stack

This is the core module. It applies all 6 middleware to a FastMCP server.

**Files:**
- Create: `app/mcp/observability.py`
- Test: `tests/mcp/test_observability.py`

**Step 1: Write the failing test**

Create `tests/mcp/test_observability.py`:

```python
"""Tests for MCP observability middleware stack."""

from __future__ import annotations

import logging
from unittest.mock import patch

from fastmcp import FastMCP

from app.config import Settings

async def test_apply_observability_adds_middleware():
    """apply_observability should add 6 middleware to gateway."""
    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    apply_observability(mcp, s)
    # FastMCP stores middleware in _middleware list
    assert len(mcp._middleware) == 6

async def test_apply_observability_correct_order():
    """Middleware order: ErrorHandling, StructuredLogging, DetailedTiming,
    ResponseCaching, Retry, Ping."""
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware
    from fastmcp.server.middleware.error_handling import (
        ErrorHandlingMiddleware,
        RetryMiddleware,
    )
    from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
    from fastmcp.server.middleware.ping import PingMiddleware
    from fastmcp.server.middleware.timing import DetailedTimingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    s = Settings(
        _env_file=None,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    apply_observability(mcp, s)

    expected_order = [
        ErrorHandlingMiddleware,
        StructuredLoggingMiddleware,
        DetailedTimingMiddleware,
        ResponseCachingMiddleware,
        RetryMiddleware,
        PingMiddleware,
    ]
    for i, (mw, expected_cls) in enumerate(zip(mcp._middleware, expected_order)):
        assert isinstance(mw, expected_cls), (
            f"Middleware #{i}: expected {expected_cls.__name__}, "
            f"got {type(mw).__name__}"
        )

async def test_apply_observability_respects_debug_settings():
    """Debug mode enables tracebacks and payload logging."""
    from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
    from fastmcp.server.middleware.logging import StructuredLoggingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    s = Settings(
        _env_file=None,
        debug=True,
        mcp_log_payloads=True,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    apply_observability(mcp, s)

    err_mw = mcp._middleware[0]
    assert isinstance(err_mw, ErrorHandlingMiddleware)
    assert err_mw.include_traceback is True

    log_mw = mcp._middleware[1]
    assert isinstance(log_mw, StructuredLoggingMiddleware)
    assert log_mw.include_payloads is True

async def test_apply_observability_retry_config():
    """Retry middleware respects settings."""
    from fastmcp.server.middleware.error_handling import RetryMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    s = Settings(
        _env_file=None,
        mcp_retry_max=5,
        mcp_retry_backoff=2.0,
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    apply_observability(mcp, s)

    retry_mw = mcp._middleware[4]
    assert isinstance(retry_mw, RetryMiddleware)
    assert retry_mw.max_retries == 5
    assert retry_mw.base_delay == 2.0

async def test_apply_observability_caching_uses_disk_store():
    """ResponseCachingMiddleware should use DiskStore."""
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    from app.mcp.observability import apply_observability

    mcp = FastMCP("test")
    s = Settings(
        _env_file=None,
        mcp_cache_dir="/tmp/test-mcp-cache",
        yandex_music_token="t",
        yandex_music_user_id="u",
    )
    apply_observability(mcp, s)

    cache_mw = mcp._middleware[3]
    assert isinstance(cache_mw, ResponseCachingMiddleware)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_observability.py -v`
Expected: FAIL — `app.mcp.observability` doesn't exist.

**Step 3: Create app/mcp/observability.py**

```python
"""Centralized MCP observability: middleware, logging, telemetry.

This module applies all middleware to the FastMCP gateway in the correct order.
The order matters: ErrorHandling → StructuredLogging → DetailedTiming →
ResponseCaching → Retry → Ping.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
import sentry_sdk
from fastmcp.server.middleware.caching import (
    CallToolSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
from fastmcp.server.middleware.error_handling import (
    ErrorHandlingMiddleware,
    RetryMiddleware,
)
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.ping import PingMiddleware
from fastmcp.server.middleware.timing import DetailedTimingMiddleware
from key_value.aio.stores.disk import DiskStore

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.server.middleware import MiddlewareContext

    from app.config import Settings

logger = logging.getLogger(__name__)

def _sentry_error_callback(
    error: Exception,
    context: MiddlewareContext,
) -> None:
    """Forward unhandled MCP errors to Sentry."""
    sentry_sdk.capture_exception(error)
    logger.error(
        "MCP tool error captured by Sentry",
        extra={
            "method": context.method,
            "error_type": type(error).__name__,
        },
    )

def apply_observability(mcp: FastMCP, settings: Settings) -> None:
    """Apply the full middleware stack to a FastMCP server.

    Middleware order (first added = outermost):
    1. ErrorHandling — catches all errors, forwards to Sentry
    2. StructuredLogging — JSON logs for each request/response
    3. DetailedTiming — per-operation timing breakdown
    4. ResponseCaching — DiskStore-backed cache with TTL
    5. Retry — exponential backoff for transient errors
    6. Ping — keepalive for HTTP/SSE connections
    """
    # 1. Error handling (outermost — catches errors from all inner middleware)
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=settings.debug,
            error_callback=_sentry_error_callback if settings.sentry_dsn else None,
        )
    )

    # 2. Structured logging (JSON)
    mcp.add_middleware(
        StructuredLoggingMiddleware(
            include_payloads=settings.mcp_log_payloads,
        )
    )

    # 3. Detailed timing
    mcp.add_middleware(DetailedTimingMiddleware())

    # 4. Response caching (DiskStore)
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
        )
    )

    # 5. Retry (transient errors only)
    mcp.add_middleware(
        RetryMiddleware(
            max_retries=settings.mcp_retry_max,
            base_delay=settings.mcp_retry_backoff,
            retry_exceptions=(
                ConnectionError,
                TimeoutError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ),
        )
    )

    # 6. Ping (keepalive for SSE/streamable HTTP)
    mcp.add_middleware(
        PingMiddleware(interval_ms=settings.mcp_ping_interval * 1000)
    )

    logger.info(
        "MCP observability applied: 6 middleware",
        extra={"server": mcp.name, "debug": settings.debug},
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_observability.py -v`
Expected: 5 tests PASS.

**Step 5: Run lint**

Run: `make lint`
Expected: Clean. Fix any issues.

**Step 6: Commit**

```bash
git add app/mcp/observability.py tests/mcp/test_observability.py
git commit -m "feat: add MCP observability module with 6 middleware"
```

---

### Task 5: Create app/mcp/lifespan.py

**Files:**
- Create: `app/mcp/lifespan.py`
- Test: `tests/mcp/test_lifespan.py`

**Step 1: Write the failing test**

Create `tests/mcp/test_lifespan.py`:

```python
"""Tests for MCP lifespan management."""

from __future__ import annotations

from fastmcp import FastMCP

async def test_mcp_lifespan_yields_context():
    """Lifespan should yield a dict that tools can access via ctx.lifespan_context."""
    from app.mcp.lifespan import mcp_lifespan

    mcp = FastMCP("test", lifespan=mcp_lifespan)

    @mcp.tool()
    def echo(ctx) -> str:
        started = ctx.lifespan_context.get("started_at")
        return f"started: {started is not None}"

    result = await mcp.call_tool("echo", {})
    # If lifespan ran, started_at should be present
    assert "started: True" in str(result)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_lifespan.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Create app/mcp/lifespan.py**

```python
"""MCP server lifespan — startup/shutdown for observability resources."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastmcp.server.lifespan import lifespan

logger = logging.getLogger(__name__)

@lifespan
async def mcp_lifespan(server):  # noqa: ANN001
    """Initialize observability resources on MCP server start.

    Yields context dict accessible via ctx.lifespan_context in tools.
    """
    started_at = datetime.now(tz=timezone.utc).isoformat()
    logger.info(
        "MCP server starting",
        extra={"server": getattr(server, "name", "unknown"), "started_at": started_at},
    )
    try:
        yield {"started_at": started_at}
    finally:
        logger.info(
            "MCP server shutting down",
            extra={"server": getattr(server, "name", "unknown")},
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_lifespan.py -v`
Expected: PASS.

**Step 5: Run lint**

Run: `make lint`
Expected: Clean.

**Step 6: Commit**

```bash
git add app/mcp/lifespan.py tests/mcp/test_lifespan.py
git commit -m "feat: add MCP lifespan with startup/shutdown logging"
```

---

### Task 6: Integrate Sentry init in app/main.py

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_sentry_init.py`

**Step 1: Write the failing test**

Create `tests/test_sentry_init.py`:

```python
"""Tests for Sentry initialization in app startup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

def test_sentry_init_called_when_dsn_set():
    """Sentry should initialize when DSN is provided."""
    with patch("app.main.sentry_sdk") as mock_sentry:
        with patch("app.main.settings") as mock_settings:
            mock_settings.sentry_dsn = "https://key@sentry.io/123"
            mock_settings.sentry_traces_sample_rate = 1.0
            mock_settings.sentry_send_pii = True
            mock_settings.environment = "test"
            mock_settings.debug = False

            from app.main import _init_sentry

            _init_sentry()

            mock_sentry.init.assert_called_once()
            call_kwargs = mock_sentry.init.call_args[1]
            assert call_kwargs["dsn"] == "https://key@sentry.io/123"
            assert call_kwargs["traces_sample_rate"] == 1.0

def test_sentry_not_called_when_dsn_empty():
    """Sentry should NOT initialize when DSN is empty."""
    with patch("app.main.sentry_sdk") as mock_sentry:
        with patch("app.main.settings") as mock_settings:
            mock_settings.sentry_dsn = ""

            from app.main import _init_sentry

            _init_sentry()

            mock_sentry.init.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sentry_init.py -v`
Expected: FAIL — `_init_sentry` doesn't exist.

**Step 3: Modify app/main.py**

Rewrite `app/main.py` to add Sentry init **before** FastMCP imports:

```python
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger(__name__)

def _init_sentry() -> None:
    """Initialize Sentry SDK if DSN is configured.

    MUST be called before importing FastMCP so that the OTEL TracerProvider
    is set up before FastMCP creates its tracer.
    """
    if not settings.sentry_dsn:
        logger.debug("Sentry DSN not set, skipping init")
        return

    from sentry_sdk.integrations.fastapi import FastApiIntegration

    integrations = [FastApiIntegration()]

    try:
        from sentry_sdk.integrations.mcp import MCPIntegration

        integrations.append(MCPIntegration())
    except ImportError:
        logger.warning("sentry_sdk.integrations.mcp not available, skipping MCPIntegration")

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=settings.sentry_send_pii,
        environment=settings.environment,
        integrations=integrations,
    )
    logger.info("Sentry initialized", extra={"environment": settings.environment})

# Initialize Sentry BEFORE importing FastMCP
_init_sentry()

from fastmcp.utilities.lifespan import combine_lifespans  # noqa: E402

from app.database import close_db, init_db  # noqa: E402
from app.errors import register_error_handlers  # noqa: E402
from app.mcp import create_dj_mcp  # noqa: E402
from app.middleware import apply_middleware  # noqa: E402
from app.routers import register_routers  # noqa: E402

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()

def create_app() -> FastAPI:
    mcp = create_dj_mcp()
    mcp_app = mcp.http_app(path="/mcp")

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
    )
    application.mount("/mcp", mcp_app)
    apply_middleware(application)
    register_error_handlers(application)
    register_routers(application)
    return application

app = create_app()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sentry_init.py -v`
Expected: 2 tests PASS.

**Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All ~363 tests pass (no regressions).

**Step 6: Run lint**

Run: `make lint`
Expected: Clean. The `# noqa: E402` comments handle the late imports.

**Step 7: Commit**

```bash
git add app/main.py tests/test_sentry_init.py
git commit -m "feat: add Sentry init before FastMCP import for OTEL integration"
```

---

### Task 7: Wire observability into gateway

**Files:**
- Modify: `app/mcp/gateway.py`
- Modify: `app/mcp/__init__.py`
- Test: `tests/mcp/test_gateway.py` (add tests)

**Step 1: Write the failing test**

Add to `tests/mcp/test_gateway.py`:

```python
async def test_gateway_has_middleware(gateway_mcp: FastMCP):
    """Gateway should have 6 observability middleware."""
    assert len(gateway_mcp._middleware) == 6

async def test_gateway_has_lifespan(gateway_mcp: FastMCP):
    """Gateway should have lifespan configured."""
    assert gateway_mcp._lifespan_manager is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_gateway.py::test_gateway_has_middleware -v`
Expected: FAIL — no middleware yet.

**Step 3: Modify app/mcp/gateway.py**

```python
"""MCP Gateway — combines all MCP sub-servers into one."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from app.config import settings
from app.mcp.lifespan import mcp_lifespan
from app.mcp.observability import apply_observability
from app.mcp.workflows import create_workflow_mcp
from app.mcp.yandex_music import create_yandex_music_mcp

logger = logging.getLogger(__name__)

def create_dj_mcp() -> FastMCP:
    """Create the gateway MCP server.

    Mounts Yandex Music (namespace "ym") and DJ Workflows (namespace "dj").
    Applies observability middleware and lifespan management.
    Adds PromptsAsTools and ResourcesAsTools transforms so that tool-only
    clients can still access prompts and resources.
    """
    gateway = FastMCP("DJ Set Builder", lifespan=mcp_lifespan)

    ym = create_yandex_music_mcp()
    gateway.mount(ym, namespace="ym")

    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    # Apply observability middleware stack
    apply_observability(gateway, settings)

    # Enable prompts/resources as tools for tool-only MCP clients
    try:
        from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools

        gateway.add_transform(PromptsAsTools(gateway))
        gateway.add_transform(ResourcesAsTools(gateway))
    except (ImportError, TypeError, AttributeError):
        logger.debug("PromptsAsTools/ResourcesAsTools not available; skipping transforms")

    return gateway
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_gateway.py -v`
Expected: All tests PASS (including existing 4 + 2 new).

**Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

**Step 6: Run lint**

Run: `make lint`
Expected: Clean.

**Step 7: Commit**

```bash
git add app/mcp/gateway.py app/mcp/__init__.py tests/mcp/test_gateway.py
git commit -m "feat: wire observability middleware and lifespan into MCP gateway"
```

---

### Task 8: Add .env.example entries

**Files:**
- Modify: `.env.example` (create if not exists)

**Step 1: Add observability env vars**

Create/update `.env.example`:

```bash
# Sentry (leave empty to disable)
SENTRY_DSN=
ENVIRONMENT=development

# OpenTelemetry (leave empty to disable OTLP exporter)
OTEL_ENDPOINT=
OTEL_SERVICE_NAME=dj-set-builder-mcp

# MCP Observability
MCP_CACHE_DIR=./cache/mcp
MCP_CACHE_TTL_TOOLS=60
MCP_CACHE_TTL_RESOURCES=300
MCP_RETRY_MAX=3
MCP_RETRY_BACKOFF=1.0
MCP_PING_INTERVAL=30
MCP_LOG_PAYLOADS=false
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add observability env vars to .env.example"
```

---

### Task 9: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (including ~8 new observability tests).

**Step 2: Run lint + type check**

Run: `make lint`
Expected: Clean.

**Step 3: Run MCP server manually to verify middleware**

Run: `make mcp-dev`
Expected: Server starts with log message "MCP observability applied: 6 middleware"

**Step 4: List tools to verify no regressions**

Run: `make mcp-list`
Expected: All ~46 tools listed (same as before).

**Step 5: Commit any remaining fixes**

```bash
git add -A
git commit -m "feat: complete MCP observability integration"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Dependencies | pyproject.toml | install check |
| 2 | Settings | app/config.py | 3 tests |
| 3 | .gitignore | .gitignore | — |
| 4 | Observability module | app/mcp/observability.py | 5 tests |
| 5 | Lifespan | app/mcp/lifespan.py | 1 test |
| 6 | Sentry init | app/main.py | 2 tests |
| 7 | Gateway wiring | app/mcp/gateway.py | 2 tests |
| 8 | Env example | .env.example | — |
| 9 | Final verification | — | full suite |

**Total new tests:** ~13
**Total new files:** 2 (`observability.py`, `lifespan.py`)
**Total modified files:** 5 (`config.py`, `main.py`, `gateway.py`, `pyproject.toml`, `.gitignore`)
