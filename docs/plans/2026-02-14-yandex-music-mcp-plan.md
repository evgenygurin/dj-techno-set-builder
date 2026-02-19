# Yandex Music MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a FastMCP server from the Yandex Music OpenAPI spec and mount it into the existing FastAPI app at `/mcp`.

**Architecture:** `FastMCP.from_openapi()` loads YAML spec from `data/yandex-music.yaml`, creates MCP tools filtered via `RouteMap` (exclude non-DJ endpoints), with httpx client authenticated via OAuth token from Settings. MCP app mounted into FastAPI via `combine_lifespans` + `app.mount("/mcp", ...)`.

**Tech Stack:** FastMCP 3.0.0rc1, httpx, PyYAML (transitive dep of fastmcp)

**Design correction:** `app/clients/yandex_music.py` is NOT deleted — it's actively used by `YandexMusicEnrichmentService`, `yandex_music` router, and `imports` router. `app/config.py` already has `yandex_music_token`, `yandex_music_base_url` fields — no changes needed.

---

### Task 1: Setup — download spec, create package structure, cleanup

**Files:**
- Create: `data/yandex-music.yaml`
- Create: `app/mcp/__init__.py`
- Create: `app/mcp/yandex_music/__init__.py`
- Create: `tests/mcp/__init__.py`
- Delete: `app/mcp/__pycache__/` (stale bytecode from deleted source files)

**Step 1: Download the OpenAPI YAML spec**

```bash
curl -sf https://raw.githubusercontent.com/acherkashin/yandex-music-open-api/main/src/yandex-music.yaml \
  -o data/yandex-music.yaml
```

Verify: `head -5 data/yandex-music.yaml` should show `openapi: "3.0.0"` and `title: Yandex Music Api`.

**Step 2: Clean up stale pycache**

```bash
rm -rf app/mcp/__pycache__ app/mcp/prompts app/mcp/resources app/mcp/servers
```

**Step 3: Create package init files**

`app/mcp/__init__.py`:
```python
"""MCP server integrations."""
```

`app/mcp/yandex_music/__init__.py`:
```python
"""Yandex Music MCP server — generated from OpenAPI spec."""

from app.mcp.yandex_music.server import create_yandex_music_mcp

__all__ = ["create_yandex_music_mcp"]
```

`tests/mcp/__init__.py`:
```python
```

**Step 4: Commit**

```bash
git add data/yandex-music.yaml app/mcp/__init__.py app/mcp/yandex_music/__init__.py tests/mcp/__init__.py
git commit -m "chore: scaffold Yandex Music MCP package and download OpenAPI spec"
```

---

### Task 2: Create RouteMap configuration

**Files:**
- Create: `app/mcp/yandex_music/config.py`

**Step 1: Write config module**

`app/mcp/yandex_music/config.py`:
```python
"""RouteMap configuration for Yandex Music MCP server."""

from __future__ import annotations

import re

from fastmcp.server.providers.openapi import MCPType, RouteMap

# Patterns for endpoints to EXCLUDE (non-DJ-relevant)
EXCLUDE_ROUTE_MAPS: list[RouteMap] = [
    RouteMap(pattern=r"^/account", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/feed", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/landing3", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/rotor", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/queues", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/settings$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/permission-alerts$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/token$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/play-audio$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/non-music", mcp_type=MCPType.EXCLUDE),
]

def _camel_to_snake(name: str) -> str:
    """Convert camelCase operationId to snake_case tool name."""
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return s.lower()

def build_mcp_names(spec: dict) -> dict[str, str]:
    """Build operationId → snake_case mapping from OpenAPI spec.

    Special case: 'search' → 'search_yandex_music' to avoid name collisions.
    """
    names: dict[str, str] = {}
    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                op_id = operation["operationId"]
                snake = _camel_to_snake(op_id)
                names[op_id] = snake
    # Explicit override for generic names
    if "search" in names:
        names["search"] = "search_yandex_music"
    return names
```

**Step 2: Commit**

```bash
git add app/mcp/yandex_music/config.py
git commit -m "feat: add RouteMap config for Yandex Music MCP endpoint filtering"
```

---

### Task 3: Write failing tests for MCP server factory

**Files:**
- Create: `tests/mcp/test_yandex_music.py`

**Step 1: Write the tests**

`tests/mcp/test_yandex_music.py`:
```python
"""Tests for Yandex Music MCP server creation and configuration."""

from __future__ import annotations

from fastmcp import FastMCP

async def test_create_yandex_music_mcp_returns_fastmcp():
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    assert isinstance(mcp, FastMCP)

async def test_mcp_server_has_tools():
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    async with mcp:
        tools = await mcp.get_tools()
    assert len(tools) > 0, "MCP server should have at least one tool"

async def test_excluded_endpoints_are_absent():
    """Endpoints like /account, /feed, /rotor should be excluded."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    async with mcp:
        tools = await mcp.get_tools()
    tool_names = {t.name for t in tools.values()}
    excluded_prefixes = {"get_account", "get_feed", "get_rotor", "get_station"}
    for prefix in excluded_prefixes:
        matching = {n for n in tool_names if n.startswith(prefix)}
        assert not matching, f"Excluded tools found: {matching}"

async def test_dj_relevant_tools_present():
    """Core DJ tools should be present: search, tracks, albums, artists."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    async with mcp:
        tools = await mcp.get_tools()
    tool_names = {t.name for t in tools.values()}
    expected = {"search_yandex_music", "get_tracks", "get_genres"}
    missing = expected - tool_names
    assert not missing, f"Expected DJ tools missing: {missing}. Available: {tool_names}"

async def test_tool_names_are_snake_case():
    """All tool names should be snake_case, not camelCase."""
    from app.mcp.yandex_music import create_yandex_music_mcp

    mcp = create_yandex_music_mcp()
    async with mcp:
        tools = await mcp.get_tools()
    for tool in tools.values():
        assert tool.name == tool.name.lower(), f"Tool name not lowercase: {tool.name}"
        assert " " not in tool.name, f"Tool name has spaces: {tool.name}"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/mcp/test_yandex_music.py -v
```

Expected: FAIL — `ImportError: cannot import name 'create_yandex_music_mcp'` (server.py doesn't exist yet).

**Step 3: Commit**

```bash
git add tests/mcp/test_yandex_music.py
git commit -m "test: add failing tests for Yandex Music MCP server factory"
```

---

### Task 4: Implement MCP server factory

**Files:**
- Create: `app/mcp/yandex_music/server.py`

**Step 1: Write the server module**

`app/mcp/yandex_music/server.py`:
```python
"""Yandex Music MCP server factory — generated from OpenAPI spec."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml
from fastmcp import FastMCP

from app.config import settings
from app.mcp.yandex_music.config import EXCLUDE_ROUTE_MAPS, build_mcp_names

_SPEC_PATH = Path(__file__).resolve().parents[3] / "data" / "yandex-music.yaml"

def _load_spec() -> dict[str, Any]:
    """Load and parse the OpenAPI YAML spec."""
    with _SPEC_PATH.open() as f:
        return yaml.safe_load(f)

def create_yandex_music_mcp() -> FastMCP:
    """Create a FastMCP server from the Yandex Music OpenAPI spec.

    Filters endpoints via RouteMap to expose only DJ-relevant tools.
    Authenticates via OAuth token from app settings.
    """
    spec = _load_spec()

    client = httpx.AsyncClient(
        base_url=settings.yandex_music_base_url,
        headers={
            "Authorization": f"OAuth {settings.yandex_music_token}",
            "Accept": "application/json",
        },
        timeout=30.0,
    )

    return FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="Yandex Music",
        route_maps=EXCLUDE_ROUTE_MAPS,
        mcp_names=build_mcp_names(spec),
    )
```

**Step 2: Run tests to verify they pass**

```bash
uv run pytest tests/mcp/test_yandex_music.py -v
```

Expected: All 5 tests PASS.

**Step 3: Run linting**

```bash
uv run ruff check app/mcp/ tests/mcp/ && uv run mypy app/mcp/
```

Fix any issues.

**Step 4: Commit**

```bash
git add app/mcp/yandex_music/server.py
git commit -m "feat: implement Yandex Music MCP server factory with OpenAPI integration"
```

---

### Task 5: Mount MCP into FastAPI

**Files:**
- Modify: `app/main.py`

**Step 1: Update main.py**

Replace the current `create_app()` to mount MCP:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp.utilities.lifespan import combine_lifespans

from app.config import settings
from app.database import close_db, init_db
from app.errors import register_error_handlers
from app.mcp.yandex_music import create_yandex_music_mcp
from app.middleware import apply_middleware
from app.routers import register_routers

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()

def create_app() -> FastAPI:
    mcp = create_yandex_music_mcp()
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

**Step 2: Run full test suite**

```bash
uv run pytest -v
```

Expected: All existing tests still pass + MCP tests pass.

**Step 3: Run linting**

```bash
uv run ruff check app/main.py && uv run mypy app/main.py
```

**Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: mount Yandex Music MCP server into FastAPI at /mcp"
```

---

### Task 6: Cleanup and final verification

**Files:**
- Delete: `app/clients/yandex_music.py` — **DO NOT DELETE** (used by services and routers)
- Delete: stale `app/mcp/__pycache__/` dirs (already done in Task 1)

**Step 1: Run full CI check**

```bash
make check
```

This runs: `ruff check` + `ruff format --check` + `mypy app/` + `pytest -v`

Expected: All checks pass.

**Step 2: Verify MCP endpoint manually (optional)**

```bash
uv run uvicorn app.main:app --port 8000 &
sleep 2
curl -sf http://localhost:8000/mcp | head -20
kill %1
```

**Step 3: Final commit (if any fixups needed)**

```bash
git add -A && git commit -m "chore: final cleanup for Yandex Music MCP integration"
```

---

## Summary of all files

| Action | File | Purpose |
|--------|------|---------|
| Create | `data/yandex-music.yaml` | OpenAPI spec (downloaded) |
| Create | `app/mcp/__init__.py` | Package init |
| Create | `app/mcp/yandex_music/__init__.py` | Re-export factory |
| Create | `app/mcp/yandex_music/config.py` | RouteMap + mcp_names |
| Create | `app/mcp/yandex_music/server.py` | FastMCP.from_openapi() factory |
| Create | `tests/mcp/__init__.py` | Test package init |
| Create | `tests/mcp/test_yandex_music.py` | Unit tests |
| Modify | `app/main.py` | Mount MCP + combine_lifespans |
| Delete | `app/mcp/__pycache__/` | Stale bytecode |
| Keep | `app/clients/yandex_music.py` | Still used by REST API services |
| Keep | `app/config.py` | Already has yandex_music_token |
