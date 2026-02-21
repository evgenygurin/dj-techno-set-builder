# Codegen Bridge Plugin — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a standalone Claude Code plugin with MCP server for Codegen AI agent platform, enabling plan execution via cloud agents.

**Architecture:** Thin MCP server (FastMCP 3.0 + httpx) wrapping Codegen REST API (7 tools). Orchestration via SKILL.md (`executing-via-codegen`). Plugin auto-discovered by Claude Code from `~/.claude/plugins/`.

**Tech Stack:** Python 3.12+, FastMCP 3.0, httpx, Pydantic v2, uv

**Design doc:** `docs/plans/2026-02-21-codegen-bridge-design.md`

---

## Task 1: Plugin Scaffold

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/.claude-plugin/plugin.json`
- Create: `~/.claude/plugins/codegen-bridge/.mcp.json`
- Create: `~/.claude/plugins/codegen-bridge/pyproject.toml`
- Create: `~/.claude/plugins/codegen-bridge/.python-version`
- Create: `~/.claude/plugins/codegen-bridge/.gitignore`

**Step 1: Create plugin directory structure**

```bash
mkdir -p ~/.claude/plugins/codegen-bridge/.claude-plugin
mkdir -p ~/.claude/plugins/codegen-bridge/mcp
mkdir -p ~/.claude/plugins/codegen-bridge/skills/executing-via-codegen
mkdir -p ~/.claude/plugins/codegen-bridge/commands
mkdir -p ~/.claude/plugins/codegen-bridge/tests
```

**Step 2: Create plugin.json**

```json
{
  "name": "codegen-bridge",
  "description": "Bridge to Codegen AI agent platform — execute implementation plans via cloud agents",
  "version": "0.1.0",
  "author": {
    "name": "DJ Techno Set Builder"
  },
  "license": "MIT",
  "keywords": ["codegen", "agent", "execution", "delegation"]
}
```

Write to: `~/.claude/plugins/codegen-bridge/.claude-plugin/plugin.json`

**Step 3: Create .mcp.json**

```json
{
  "mcpServers": {
    "codegen": {
      "command": "uv",
      "args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}", "mcp/server.py"],
      "env": {
        "CODEGEN_API_KEY": "${CODEGEN_API_KEY}",
        "CODEGEN_ORG_ID": "${CODEGEN_ORG_ID}"
      }
    }
  }
}
```

Write to: `~/.claude/plugins/codegen-bridge/.mcp.json`

**Step 4: Create pyproject.toml**

```toml
[project]
name = "codegen-bridge"
version = "0.1.0"
description = "MCP server for Codegen AI agent platform"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.22",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 99
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "RUF"]
```

Write to: `~/.claude/plugins/codegen-bridge/pyproject.toml`

**Step 5: Create .python-version and .gitignore**

`.python-version`: `3.12`

`.gitignore`:
```text
__pycache__/
*.pyc
.venv/
.ruff_cache/
.mypy_cache/
.pytest_cache/
uv.lock
```

**Step 6: Install dependencies**

Run: `cd ~/.claude/plugins/codegen-bridge && uv sync --dev`
Expected: Dependencies installed, `.venv/` created

**Step 7: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git init
git add .
git commit -m "feat: scaffold codegen-bridge plugin"
```

---

## Task 2: Pydantic Response Types

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/mcp/__init__.py`
- Create: `~/.claude/plugins/codegen-bridge/mcp/types.py`

**Step 1: Create empty __init__.py**

Write empty file to: `~/.claude/plugins/codegen-bridge/mcp/__init__.py`

**Step 2: Write Pydantic models**

```python
"""Pydantic models for Codegen API responses."""

from __future__ import annotations

from pydantic import BaseModel

class AgentRun(BaseModel):
    """Agent run summary."""

    id: int
    status: str | None = None
    web_url: str | None = None
    result: str | None = None
    summary: str | None = None
    created_at: str | None = None
    source_type: str | None = None
    github_pull_requests: list[PullRequest] | None = None
    metadata: dict | None = None

class PullRequest(BaseModel):
    """GitHub PR created by agent."""

    url: str | None = None
    number: int | None = None
    title: str | None = None
    state: str | None = None

class AgentLog(BaseModel):
    """Single agent log entry."""

    agent_run_id: int
    created_at: str | None = None
    tool_name: str | None = None
    message_type: str | None = None
    thought: str | None = None
    observation: str | dict | None = None
    tool_input: dict | None = None
    tool_output: str | dict | None = None

class AgentRunWithLogs(BaseModel):
    """Agent run with paginated logs."""

    id: int
    status: str | None = None
    logs: list[AgentLog]
    total_logs: int = 0

class Organization(BaseModel):
    """Codegen organization."""

    id: int
    name: str

class Repository(BaseModel):
    """GitHub repository in Codegen."""

    id: int
    name: str
    full_name: str
    language: str | None = None
    setup_status: str | None = None
    visibility: str | None = None

class Page[T](BaseModel):
    """Paginated response."""

    items: list[T]
    total: int = 0
    page: int = 1
    size: int = 100
    pages: int = 1
```

Write to: `~/.claude/plugins/codegen-bridge/mcp/types.py`

**Step 3: Run lint**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run ruff check mcp/types.py`
Expected: No errors

**Step 4: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add mcp/
git commit -m "feat: add Pydantic response models for Codegen API"
```

---

## Task 3: Codegen API Client

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/mcp/client.py`
- Create: `~/.claude/plugins/codegen-bridge/tests/__init__.py`
- Create: `~/.claude/plugins/codegen-bridge/tests/test_client.py`

**Step 1: Write failing test for client initialization**

```python
"""Tests for Codegen API client."""

from __future__ import annotations

import pytest

from mcp.client import CodegenClient

class TestClientInit:
    def test_creates_with_credentials(self):
        client = CodegenClient(api_key="test-key", org_id=42)
        assert client.org_id == 42

    def test_raises_without_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            CodegenClient(api_key="", org_id=42)

    def test_raises_without_org_id(self):
        with pytest.raises(ValueError, match="org_id"):
            CodegenClient(api_key="test-key", org_id=0)
```

Write to: `~/.claude/plugins/codegen-bridge/tests/test_client.py`

Write empty: `~/.claude/plugins/codegen-bridge/tests/__init__.py`

**Step 2: Run test to verify it fails**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run pytest tests/test_client.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'mcp.client'"

**Step 3: Write CodegenClient**

```python
"""Async HTTP client for Codegen REST API v1."""

from __future__ import annotations

from typing import Any

import httpx

from mcp.types import (
    AgentLog,
    AgentRun,
    AgentRunWithLogs,
    Organization,
    Page,
    Repository,
)

BASE_URL = "https://api.codegen.com/v1"

class CodegenClient:
    """Async client for Codegen API.

    Args:
        api_key: Bearer token for authentication.
        org_id: Organization ID for API calls.
        base_url: Override API base URL (for testing).
    """

    def __init__(
        self,
        api_key: str,
        org_id: int,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not org_id:
            raise ValueError("org_id is required")

        self.org_id = org_id
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> CodegenClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ── Agent Runs ──────────────────────────────────────────

    async def create_run(
        self,
        prompt: str,
        *,
        repo_id: int | None = None,
        model: str | None = None,
        agent_type: str = "claude_code",
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        """Create a new agent run."""
        body: dict[str, Any] = {"prompt": prompt}
        if repo_id is not None:
            body["repo_id"] = repo_id
        if model is not None:
            body["model"] = model
        if agent_type:
            body["agent_type"] = agent_type
        if metadata is not None:
            body["metadata"] = metadata

        resp = await self._post(f"/organizations/{self.org_id}/agent/run", json=body)
        return AgentRun.model_validate(resp)

    async def get_run(self, run_id: int) -> AgentRun:
        """Get agent run by ID."""
        resp = await self._get(f"/organizations/{self.org_id}/agent/run/{run_id}")
        return AgentRun.model_validate(resp)

    async def list_runs(
        self,
        *,
        skip: int = 0,
        limit: int = 10,
        source_type: str | None = None,
    ) -> Page[AgentRun]:
        """List agent runs with pagination."""
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if source_type:
            params["source_type"] = source_type

        resp = await self._get(f"/organizations/{self.org_id}/agent/runs", params=params)
        return Page[AgentRun].model_validate(resp)

    async def resume_run(
        self,
        run_id: int,
        prompt: str,
        *,
        model: str | None = None,
    ) -> AgentRun:
        """Resume a paused agent run."""
        body: dict[str, Any] = {"agent_run_id": run_id, "prompt": prompt}
        if model is not None:
            body["model"] = model

        resp = await self._post(f"/organizations/{self.org_id}/agent/run/resume", json=body)
        return AgentRun.model_validate(resp)

    async def get_logs(
        self,
        run_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        reverse: bool = True,
    ) -> AgentRunWithLogs:
        """Get agent run logs."""
        params: dict[str, Any] = {
            "skip": skip,
            "limit": limit,
            "reverse": reverse,
        }
        resp = await self._get(
            f"/alpha/organizations/{self.org_id}/agent/run/{run_id}/logs",
            params=params,
        )
        return AgentRunWithLogs.model_validate(resp)

    # ── Organizations & Repos ───────────────────────────────

    async def list_orgs(self) -> Page[Organization]:
        """List organizations."""
        resp = await self._get("/organizations")
        return Page[Organization].model_validate(resp)

    async def list_repos(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Page[Repository]:
        """List repositories in the organization."""
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        resp = await self._get(f"/organizations/{self.org_id}/repos", params=params)
        return Page[Repository].model_validate(resp)

    # ── HTTP Helpers ────────────────────────────────────────

    async def _get(self, path: str, *, params: dict | None = None) -> dict:
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, *, json: dict | None = None) -> dict:
        resp = await self._client.post(path, json=json)
        resp.raise_for_status()
        return resp.json()
```

Write to: `~/.claude/plugins/codegen-bridge/mcp/client.py`

**Step 4: Run tests to verify they pass**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run pytest tests/test_client.py -v`
Expected: 3 PASSED

**Step 5: Write tests for API methods (with respx mock)**

Add to `tests/test_client.py`:

```python
import respx
from httpx import Response

class TestCreateRun:
    @respx.mock
    async def test_creates_run_with_prompt(self):
        route = respx.post("https://api.codegen.com/v1/organizations/42/agent/run").mock(
            return_value=Response(200, json={"id": 1, "status": "queued", "web_url": "https://codegen.com/run/1"})
        )

        async with CodegenClient(api_key="test", org_id=42) as client:
            run = await client.create_run("Fix the bug")

        assert run.id == 1
        assert run.status == "queued"
        assert route.called

    @respx.mock
    async def test_creates_run_with_all_params(self):
        route = respx.post("https://api.codegen.com/v1/organizations/42/agent/run").mock(
            return_value=Response(200, json={"id": 2, "status": "queued"})
        )

        async with CodegenClient(api_key="test", org_id=42) as client:
            run = await client.create_run(
                "Refactor auth",
                repo_id=10,
                model="claude-sonnet-4-6",
                agent_type="claude_code",
                metadata={"plan_task": "Task 3"},
            )

        assert run.id == 2
        body = route.calls[0].request.content
        assert b"repo_id" in body

class TestGetRun:
    @respx.mock
    async def test_gets_run_by_id(self):
        respx.get("https://api.codegen.com/v1/organizations/42/agent/run/1").mock(
            return_value=Response(200, json={
                "id": 1, "status": "completed", "summary": "Fixed the bug",
                "github_pull_requests": [{"url": "https://github.com/org/repo/pull/5", "number": 5}],
            })
        )

        async with CodegenClient(api_key="test", org_id=42) as client:
            run = await client.get_run(1)

        assert run.status == "completed"
        assert run.github_pull_requests[0].number == 5

class TestGetLogs:
    @respx.mock
    async def test_gets_logs(self):
        respx.get("https://api.codegen.com/v1/alpha/organizations/42/agent/run/1/logs").mock(
            return_value=Response(200, json={
                "id": 1, "status": "running",
                "logs": [{"agent_run_id": 1, "thought": "Analyzing code", "tool_name": "read_file"}],
                "total_logs": 1,
            })
        )

        async with CodegenClient(api_key="test", org_id=42) as client:
            result = await client.get_logs(1)

        assert len(result.logs) == 1
        assert result.logs[0].thought == "Analyzing code"

class TestListRepos:
    @respx.mock
    async def test_lists_repos(self):
        respx.get("https://api.codegen.com/v1/organizations/42/repos").mock(
            return_value=Response(200, json={
                "items": [{"id": 10, "name": "myrepo", "full_name": "org/myrepo", "language": "Python"}],
                "total": 1,
            })
        )

        async with CodegenClient(api_key="test", org_id=42) as client:
            repos = await client.list_repos()

        assert repos.items[0].full_name == "org/myrepo"
```

**Step 6: Run tests**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run pytest tests/test_client.py -v`
Expected: All PASSED

**Step 7: Lint**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run ruff check mcp/ tests/`
Expected: No errors

**Step 8: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add mcp/client.py tests/
git commit -m "feat: add Codegen API client with tests"
```

---

## Task 4: MCP Server with 7 Tools

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/mcp/server.py`

**Step 1: Write MCP server with all 7 tools**

```python
"""FastMCP server for Codegen AI agent platform."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp.client import CodegenClient

mcp = FastMCP(
    "Codegen Bridge",
    instructions="Tools for delegating tasks to Codegen AI agents. "
    "Create agent runs, monitor progress, view logs, and resume blocked runs.",
)

# ── Config ──────────────────────────────────────────────────

_client: CodegenClient | None = None
_repo_cache: dict[str, int] = {}  # full_name -> repo_id

def _get_client() -> CodegenClient:
    """Get or create the Codegen API client."""
    global _client
    if _client is None:
        api_key = os.environ.get("CODEGEN_API_KEY", "")
        org_id_str = os.environ.get("CODEGEN_ORG_ID", "0")
        try:
            org_id = int(org_id_str)
        except ValueError:
            raise ToolError(
                "CODEGEN_ORG_ID must be a number. "
                "Set it in your environment or plugin .mcp.json."
            )
        if not api_key:
            raise ToolError(
                "CODEGEN_API_KEY not set. "
                "Set it in your environment or plugin .mcp.json."
            )
        if not org_id:
            raise ToolError(
                "CODEGEN_ORG_ID not set. "
                "Set it in your environment or plugin .mcp.json."
            )
        _client = CodegenClient(api_key=api_key, org_id=org_id)
    return _client

async def _detect_repo_id() -> int | None:
    """Auto-detect repo_id from git remote origin."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        url = result.stdout.strip()
        # Parse owner/repo from git URL
        # Handles: https://github.com/owner/repo.git, git@github.com:owner/repo.git
        full_name = ""
        if "github.com" in url:
            if url.startswith("git@"):
                full_name = url.split(":")[-1].removesuffix(".git")
            else:
                parts = url.rstrip("/").removesuffix(".git").split("/")
                if len(parts) >= 2:
                    full_name = f"{parts[-2]}/{parts[-1]}"

        if not full_name:
            return None

        # Check cache first
        if full_name in _repo_cache:
            return _repo_cache[full_name]

        # Lookup in Codegen repos
        client = _get_client()
        repos = await client.list_repos(limit=100)
        for repo in repos.items:
            _repo_cache[repo.full_name] = repo.id
            if repo.full_name == full_name:
                return repo.id

        return None

    except Exception:
        return None

# ── Tools ───────────────────────────────────────────────────

@mcp.tool(tags={"execution"})
async def codegen_create_run(
    prompt: str,
    repo_id: int | None = None,
    model: str | None = None,
    agent_type: Literal["codegen", "claude_code"] = "claude_code",
) -> str:
    """Create a new Codegen agent run.

    The agent will execute the task in a cloud sandbox and may create a PR.

    Args:
        prompt: Task description for the agent (natural language, full context).
        repo_id: Repository ID. If not provided, auto-detected from git remote.
        model: LLM model to use. None = organization default.
        agent_type: Agent type — "codegen" (Codegen's own) or "claude_code" (Claude Code).
    """
    client = _get_client()

    if repo_id is None:
        repo_id = await _detect_repo_id()
        if repo_id is None:
            raise ToolError(
                "Could not auto-detect repository. "
                "Provide repo_id explicitly or run from a git repository "
                "that is registered in your Codegen organization."
            )

    run = await client.create_run(
        prompt,
        repo_id=repo_id,
        model=model,
        agent_type=agent_type,
    )
    return json.dumps({
        "id": run.id,
        "status": run.status,
        "web_url": run.web_url,
    })

@mcp.tool(tags={"execution"})
async def codegen_get_run(run_id: int) -> str:
    """Get agent run status, result, summary, and created PRs.

    Use this to poll for completion (check status field).
    """
    client = _get_client()
    run = await client.get_run(run_id)

    result: dict = {
        "id": run.id,
        "status": run.status,
        "web_url": run.web_url,
    }
    if run.result:
        result["result"] = run.result
    if run.summary:
        result["summary"] = run.summary
    if run.github_pull_requests:
        result["pull_requests"] = [
            {"url": pr.url, "number": pr.number, "title": pr.title, "state": pr.state}
            for pr in run.github_pull_requests
        ]
    return json.dumps(result)

@mcp.tool(tags={"execution"})
async def codegen_list_runs(
    limit: int = 10,
    source_type: str | None = None,
) -> str:
    """List recent agent runs.

    Args:
        limit: Maximum number of runs to return (default 10).
        source_type: Filter by source — API, LOCAL, GITHUB, etc.
    """
    client = _get_client()
    page = await client.list_runs(limit=limit, source_type=source_type)
    return json.dumps({
        "total": page.total,
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "created_at": r.created_at,
                "web_url": r.web_url,
                "summary": r.summary,
            }
            for r in page.items
        ],
    })

@mcp.tool(tags={"execution"})
async def codegen_resume_run(
    run_id: int,
    prompt: str,
    model: str | None = None,
) -> str:
    """Resume a paused or blocked agent run with new instructions.

    Args:
        run_id: Agent run ID to resume.
        prompt: New instructions or clarification for the agent.
        model: Optionally switch model for the resumed run.
    """
    client = _get_client()
    run = await client.resume_run(run_id, prompt, model=model)
    return json.dumps({
        "id": run.id,
        "status": run.status,
        "web_url": run.web_url,
    })

@mcp.tool(tags={"execution"})
async def codegen_get_logs(
    run_id: int,
    limit: int = 50,
    reverse: bool = True,
) -> str:
    """Get step-by-step agent execution logs.

    Shows agent thoughts, tool calls, and outputs for debugging.

    Args:
        run_id: Agent run ID.
        limit: Max log entries (default 50).
        reverse: If true, newest entries first.
    """
    client = _get_client()
    result = await client.get_logs(run_id, limit=limit, reverse=reverse)
    return json.dumps({
        "run_id": result.id,
        "status": result.status,
        "total_logs": result.total_logs,
        "logs": [
            {
                k: v
                for k, v in {
                    "thought": log.thought,
                    "tool_name": log.tool_name,
                    "tool_input": log.tool_input,
                    "tool_output": (
                        str(log.tool_output)[:500]
                        if log.tool_output
                        else None
                    ),
                    "created_at": log.created_at,
                }.items()
                if v is not None
            }
            for log in result.logs
        ],
    })

@mcp.tool(tags={"setup"})
async def codegen_list_orgs() -> str:
    """List Codegen organizations the authenticated user belongs to."""
    client = _get_client()
    page = await client.list_orgs()
    return json.dumps({
        "organizations": [
            {"id": org.id, "name": org.name}
            for org in page.items
        ],
    })

@mcp.tool(tags={"setup"})
async def codegen_list_repos(limit: int = 50) -> str:
    """List repositories in the configured Codegen organization.

    Args:
        limit: Maximum repos to return (default 50).
    """
    client = _get_client()
    page = await client.list_repos(limit=limit)
    return json.dumps({
        "total": page.total,
        "repos": [
            {
                "id": r.id,
                "name": r.name,
                "full_name": r.full_name,
                "language": r.language,
                "setup_status": r.setup_status,
            }
            for r in page.items
        ],
    })

# ── Entry Point ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
```

Write to: `~/.claude/plugins/codegen-bridge/mcp/server.py`

**Step 2: Lint**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run ruff check mcp/server.py`
Expected: No errors

**Step 3: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add mcp/server.py
git commit -m "feat: add MCP server with 7 Codegen tools"
```

---

## Task 5: MCP Server Tests

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/tests/test_server.py`

**Step 1: Write tests for MCP tool registration**

```python
"""Tests for MCP server tools."""

from __future__ import annotations

import json

import pytest
import respx
from fastmcp import Client
from httpx import Response

# Set env before importing server
import os
os.environ.setdefault("CODEGEN_API_KEY", "test-key")
os.environ.setdefault("CODEGEN_ORG_ID", "42")

from mcp.server import mcp  # noqa: E402

@pytest.fixture
async def client():
    """Create in-memory MCP client."""
    async with Client(mcp) as c:
        yield c

class TestToolRegistration:
    async def test_all_tools_registered(self, client: Client):
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert names == {
            "codegen_create_run",
            "codegen_get_run",
            "codegen_list_runs",
            "codegen_resume_run",
            "codegen_get_logs",
            "codegen_list_orgs",
            "codegen_list_repos",
        }

    async def test_create_run_has_description(self, client: Client):
        tools = await client.list_tools()
        create_tool = next(t for t in tools if t.name == "codegen_create_run")
        assert "agent run" in create_tool.description.lower()

class TestCreateRun:
    @respx.mock
    async def test_creates_run_and_returns_json(self, client: Client):
        respx.post("https://api.codegen.com/v1/organizations/42/agent/run").mock(
            return_value=Response(200, json={
                "id": 99, "status": "queued", "web_url": "https://codegen.com/run/99",
            })
        )
        # Mock repo detection to avoid subprocess
        respx.get("https://api.codegen.com/v1/organizations/42/repos").mock(
            return_value=Response(200, json={"items": [], "total": 0})
        )

        result = await client.call_tool("codegen_create_run", {
            "prompt": "Fix the bug",
            "repo_id": 10,
        })
        data = json.loads(result.data)
        assert data["id"] == 99
        assert data["status"] == "queued"

class TestGetRun:
    @respx.mock
    async def test_returns_run_with_pr(self, client: Client):
        respx.get("https://api.codegen.com/v1/organizations/42/agent/run/99").mock(
            return_value=Response(200, json={
                "id": 99,
                "status": "completed",
                "summary": "Fixed the bug",
                "github_pull_requests": [
                    {"url": "https://github.com/o/r/pull/5", "number": 5, "title": "Fix bug", "state": "open"}
                ],
            })
        )

        result = await client.call_tool("codegen_get_run", {"run_id": 99})
        data = json.loads(result.data)
        assert data["status"] == "completed"
        assert data["pull_requests"][0]["number"] == 5

class TestGetLogs:
    @respx.mock
    async def test_returns_formatted_logs(self, client: Client):
        respx.get("https://api.codegen.com/v1/alpha/organizations/42/agent/run/99/logs").mock(
            return_value=Response(200, json={
                "id": 99, "status": "running",
                "logs": [
                    {"agent_run_id": 99, "thought": "Reading code", "tool_name": "read_file"},
                    {"agent_run_id": 99, "thought": "Found issue", "tool_name": None},
                ],
                "total_logs": 2,
            })
        )

        result = await client.call_tool("codegen_get_logs", {"run_id": 99})
        data = json.loads(result.data)
        assert data["total_logs"] == 2
        assert data["logs"][0]["thought"] == "Reading code"
```

Write to: `~/.claude/plugins/codegen-bridge/tests/test_server.py`

**Step 2: Run tests**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run pytest tests/test_server.py -v`
Expected: All PASSED

**Step 3: Run full test suite**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run pytest -v`
Expected: All PASSED

**Step 4: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add tests/test_server.py
git commit -m "test: add MCP server tool tests"
```

---

## Task 6: executing-via-codegen Skill

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/skills/executing-via-codegen/SKILL.md`

**Step 1: Write the skill**

```markdown
---
name: executing-via-codegen
description: Use when executing implementation plans via Codegen cloud agents instead of locally. Delegates each task as a separate Codegen agent run, monitors progress, and handles blockers. Choose this when writing-plans offers "Codegen Remote" as an execution option.
---

# Executing Plans via Codegen

## Overview

Load plan, delegate each task to a Codegen cloud agent, monitor until done, report results.

**Core principle:** One task = one agent run. You orchestrate, Codegen executes.

**Announce at start:** "I'm using the executing-via-codegen skill to execute this plan via Codegen cloud agents."

## Prerequisites

- `CODEGEN_API_KEY` and `CODEGEN_ORG_ID` environment variables set
- Repository registered in Codegen organization
- MCP tools available: `codegen_create_run`, `codegen_get_run`, `codegen_get_logs`, `codegen_resume_run`

## The Process

### Step 1: Load and Review Plan

1. Read the plan file
2. Review critically — same as executing-plans
3. If concerns: raise with user before starting
4. Parse all tasks from the plan (### Task N: ...)
5. Extract plan header (Goal, Architecture, Tech Stack)

### Step 2: Verify Codegen Access

1. Call `codegen_list_repos` to verify the repository is accessible
2. Note the `repo_id` for subsequent calls
3. If repo not found: ask user to check Codegen setup

### Step 3: Execute Each Task

For each task in the plan:

**a. Build the prompt:**

Compose the agent run prompt from three parts:

```
## Context
[Plan header: Goal, Architecture, Tech Stack]

Previously completed tasks:
- Task 1: [one-line summary of result]
- Task 2: [one-line summary of result]

## Your Task
[Full text of current task from plan — all steps verbatim]

## Constraints
- Create a branch from main (or the current default branch)
- Run tests after each step
- Commit with conventional commit messages
- Create a PR when done
```sql

**b. Create the agent run:**

```

codegen_create_run(
  prompt=<composed prompt>,
  repo_id=<detected or explicit>,
  agent_type="claude_code"
)
```text

**c. Monitor progress:**

Poll every 30 seconds:

```bash
sleep 30
```

Then call `codegen_get_run(run_id=<id>)`. Check the `status` field:

| Status | Action |
|--------|--------|
| `running` | Continue polling. Show: "Task N still running..." |
| `queued` | Continue polling. Show: "Task N queued..." |
| `completed` | Go to step d |
| `failed` | Go to step e |
| `paused` | Go to step f |

**Max polling:** 10 minutes per task. After 10 min, show status and ask user.

**d. On completion:**

1. Call `codegen_get_logs(run_id, limit=20)` to review what happened
2. Call `codegen_get_run(run_id)` to check for PRs
3. Report to user:
   - What the agent did (from logs summary)
   - PR link (if created)
   - Any warnings from logs
4. Mark task as completed in TodoWrite

**e. On failure:**

1. Call `codegen_get_logs(run_id, limit=30)` to see error details
2. Show error logs to user
3. Ask: "Resume with fix instructions, skip this task, or stop?"
4. If resume: `codegen_resume_run(run_id, prompt=<user guidance>)`
5. If skip: mark task as skipped, continue to next
6. If stop: halt execution

**f. On pause (agent needs input):**

1. Call `codegen_get_logs(run_id, limit=10)` to see what agent is asking
2. Show the agent's question/blocker to user
3. Get user's response
4. `codegen_resume_run(run_id, prompt=<user response>)`
5. Resume polling

### Step 4: Report Between Tasks

After each task completes:
- Show what was done
- Show PR link if created
- Show current progress (N/M tasks)
- Say: "Ready for next task, or do you want to review first?"

### Step 5: Final Summary

After all tasks:
- List all completed tasks with PR links
- Show any skipped/failed tasks
- Total agent runs created
- Suggest: "Review the PRs on GitHub and merge when ready."

## Differences from Local Execution

| Aspect | executing-plans (local) | executing-via-codegen (cloud) |
|--------|------------------------|------------------------------|
| Where | Your terminal | Codegen cloud sandbox |
| Output | Files on disk | PRs on GitHub |
| Branch | Git worktree required | Codegen creates branch |
| Review | Local diff | PR diff on GitHub |
| Batch size | 3 tasks per batch | 1 task = 1 agent run |
| Monitoring | Direct stdout | codegen_get_logs |

## When to Stop and Ask

**STOP immediately when:**
- HTTP 402 — billing limit reached (tell user)
- HTTP 403 — check API key / org_id
- Agent fails repeatedly (>2 retries)
- User requests stop
- Plan has critical gaps

## Error Recovery

If `codegen_create_run` returns HTTP error:
- 429: Wait 60 seconds, retry once
- 402: "Codegen billing limit reached. Cannot continue."
- 500+: Retry once, then report error

If polling times out (10 min):
- Show last known status
- Ask: "Agent still running. Wait longer, check logs, or cancel?"

## Remember
- One task = one agent run (NOT batching)
- Include full task text in prompt (not file references)
- Include previous task summaries for context
- Poll with `sleep 30` between checks
- Always show PR links when available
- Stop on blockers, don't guess
```text

Write to: `~/.claude/plugins/codegen-bridge/skills/executing-via-codegen/SKILL.md`

**Step 2: Verify frontmatter parses correctly**

Read the file and verify YAML frontmatter is valid (name + description fields present).

**Step 3: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add skills/
git commit -m "feat: add executing-via-codegen skill"
```

---

## Task 7: Slash Commands

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/commands/codegen.md`
- Create: `~/.claude/plugins/codegen-bridge/commands/cg-status.md`
- Create: `~/.claude/plugins/codegen-bridge/commands/cg-logs.md`

**Step 1: Create /codegen command**

```markdown
---
description: "Delegate a task to Codegen cloud agent"
---

Use the codegen MCP tools to handle this request.

If the user provided a task description, use `codegen_create_run` to create an agent run with that task.

If no task was provided, show available actions:
- Create new agent run: `codegen_create_run`
- Check status: `codegen_get_run` or `codegen_list_runs`
- View logs: `codegen_get_logs`
- Resume paused run: `codegen_resume_run`
- List repos: `codegen_list_repos`
```

Write to: `~/.claude/plugins/codegen-bridge/commands/codegen.md`

**Step 2: Create /cg-status command**

```markdown
---
description: "Quick overview of active Codegen agent runs"
---

Call `codegen_list_runs` to show all recent agent runs. Format as a concise table showing: ID, status, summary, and PR link (if any). Group by status: running first, then queued, then recently completed.
```

Write to: `~/.claude/plugins/codegen-bridge/commands/cg-status.md`

**Step 3: Create /cg-logs command**

```markdown
---
description: "View execution logs for a Codegen agent run"
---

Call `codegen_get_logs` for the specified run_id. If no run_id provided, call `codegen_list_runs` first and ask the user which run to show logs for.

Format logs showing: timestamp, thought (💭), tool calls (🔧), and errors (❌). Truncate long tool outputs.
```

Write to: `~/.claude/plugins/codegen-bridge/commands/cg-logs.md`

**Step 4: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add commands/
git commit -m "feat: add slash commands (/codegen, /cg-status, /cg-logs)"
```

---

## Task 8: README and Final Polish

**Files:**
- Create: `~/.claude/plugins/codegen-bridge/README.md`

**Step 1: Write README**

```markdown
# Codegen Bridge

Claude Code plugin for delegating implementation plans to [Codegen](https://codegen.com) cloud AI agents.

## What it does

- **7 MCP tools** for Codegen API: create/monitor/resume agent runs, view logs
- **executing-via-codegen skill** — orchestrates plan execution task-by-task via cloud agents
- **Slash commands** — `/codegen`, `/cg-status`, `/cg-logs`

## Setup

1. Get API key from [codegen.com](https://codegen.com)
2. Set environment variables:

```bash
export CODEGEN_API_KEY="your-api-key"
export CODEGEN_ORG_ID="your-org-id"
```

3. Install the plugin in Claude Code:

```text
/install-plugin ~/.claude/plugins/codegen-bridge
```

## Usage with Superpowers

When `writing-plans` offers execution options, choose **"Codegen Remote"** to delegate to cloud agents. The `executing-via-codegen` skill will:

1. Parse the plan into tasks
2. Create one Codegen agent run per task
3. Monitor progress (polling every 30s)
4. Report results with PR links
5. Handle failures and pauses

## MCP Tools

| Tool | Purpose |
|------|---------|
| `codegen_create_run` | Create agent run (prompt + repo + model) |
| `codegen_get_run` | Get run status + result + PRs |
| `codegen_list_runs` | List recent runs |
| `codegen_resume_run` | Resume blocked run |
| `codegen_get_logs` | View step-by-step agent logs |
| `codegen_list_orgs` | List organizations |
| `codegen_list_repos` | List repositories |

## Development

```bash
cd ~/.claude/plugins/codegen-bridge
uv sync --dev
uv run pytest -v
uv run ruff check .
```
```text

Write to: `~/.claude/plugins/codegen-bridge/README.md`

**Step 2: Run full test suite one more time**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run pytest -v`
Expected: All PASSED

**Step 3: Run lint on everything**

Run: `cd ~/.claude/plugins/codegen-bridge && uv run ruff check .`
Expected: No errors

**Step 4: Commit**

```bash
cd ~/.claude/plugins/codegen-bridge
git add README.md
git commit -m "docs: add README with setup and usage instructions"
```

---

## Task 9: Integration Smoke Test

**Step 1: Verify MCP server starts**

Run: `cd ~/.claude/plugins/codegen-bridge && CODEGEN_API_KEY=test CODEGEN_ORG_ID=1 uv run mcp/server.py &`

Then: `cd ~/.claude/plugins/codegen-bridge && uv run fastmcp list --command "uv run mcp/server.py"`

Expected: List of 7 tools

Kill the background process after.

**Step 2: Verify plugin structure**

Check that all required files exist:
- `.claude-plugin/plugin.json`
- `.mcp.json`
- `skills/executing-via-codegen/SKILL.md`
- `commands/codegen.md`
- `mcp/server.py`
- `mcp/client.py`
- `mcp/types.py`
- `tests/test_client.py`
- `tests/test_server.py`

**Step 3: Final commit with version tag**

```bash
cd ~/.claude/plugins/codegen-bridge
git add -A
git status  # verify nothing unexpected
git commit -m "chore: finalize v0.1.0"
git tag v0.1.0
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Plugin scaffold | plugin.json, .mcp.json, pyproject.toml |
| 2 | Pydantic types | mcp/types.py |
| 3 | API client + tests | mcp/client.py, tests/test_client.py |
| 4 | MCP server (7 tools) | mcp/server.py |
| 5 | MCP server tests | tests/test_server.py |
| 6 | executing-via-codegen skill | skills/.../SKILL.md |
| 7 | Slash commands | commands/*.md |
| 8 | README + polish | README.md |
| 9 | Smoke test | (verification only) |
