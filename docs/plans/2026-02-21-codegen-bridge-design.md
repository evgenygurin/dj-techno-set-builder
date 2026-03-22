# Codegen Bridge Plugin — Design Document

> **Date:** 2026-02-21
> **Status:** Approved
> **Author:** Claude Opus 4.6

## Goal

Create a standalone Claude Code plugin (`codegen-bridge`) that provides an MCP server for the Codegen AI agent platform API, enabling plan execution via cloud agents as a third option alongside subagent-driven and parallel session approaches.

## Context

**Codegen** is an AI agent orchestration platform (not a code generator). You give it a prompt + repository + model, and it runs an agent (codegen or claude_code) in a sandbox that can create PRs, fix bugs, and refactor code.

**Superpowers `writing-plans`** currently offers two execution paths:
1. Subagent-Driven (same session) — via `subagent-driven-development` skill
2. Parallel Session (separate terminal) — via `executing-plans` skill

This plugin adds a third option:
3. **Codegen Remote** (cloud agent) — via `executing-via-codegen` skill

## Architecture

```text
Claude Code (local)
  │
  ├── writing-plans skill → offers 3 execution options
  │
  └── executing-via-codegen skill (orchestrator)
        │
        ├── codegen_create_run()  ─── per task ───→  Codegen API
        ├── codegen_get_run()     ← poll status ──→  (cloud sandbox)
        ├── codegen_get_logs()    ← review logs ──→
        ├── codegen_resume_run()  ─ if blocked ──→
        │
        └── Report to user ← PR links, results
```

**Approach:** Thin MCP + Smart Skill
- MCP server = thin httpx wrapper around Codegen REST API (7 tools)
- Skill = SKILL.md orchestrating the per-task execution workflow
- LLM decides when to create runs, poll, resume, report

## Plugin Structure

```text
codegen-bridge/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── .mcp.json                    # MCP server declaration
├── mcp/
│   ├── server.py                # FastMCP server (entry point)
│   ├── client.py                # httpx-based Codegen API client
│   └── types.py                 # Pydantic response models
├── skills/
│   └── executing-via-codegen/
│       └── SKILL.md             # Orchestration skill
├── pyproject.toml               # Dependencies: fastmcp, httpx, pydantic
└── README.md
```

### plugin.json

```json
{
  "name": "codegen-bridge",
  "description": "Bridge to Codegen AI agent platform — execute implementation plans via cloud agents",
  "version": "0.1.0"
}
```

### .mcp.json

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

### Dependencies

```toml
[project]
name = "codegen-bridge"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.0",
    "httpx>=0.27",
    "pydantic>=2.0",
]
```

## MCP Server — 7 Tools

### API Client (mcp/client.py)

```python
class CodegenClient:
    """Async client for Codegen REST API v1."""

    base_url = "https://api.codegen.com/v1"

    def __init__(self, api_key: str, org_id: int):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self.org_id = org_id

    async def create_run(self, prompt, repo_id, model, agent_type, metadata) -> dict: ...
    async def get_run(self, run_id) -> dict: ...
    async def list_runs(self, skip, limit, source_type) -> dict: ...
    async def resume_run(self, run_id, prompt, model) -> dict: ...
    async def get_logs(self, run_id, skip, limit, reverse) -> dict: ...
    async def list_orgs(self) -> dict: ...
    async def list_repos(self, skip, limit) -> dict: ...

    async def close(self): ...
```

### Tool Definitions (mcp/server.py)

| Tool | API Endpoint | Purpose |
|------|-------------|---------|
| `codegen_create_run` | `POST /orgs/{id}/agent/run` | Create agent run (prompt + repo + model + agent_type) |
| `codegen_get_run` | `GET /orgs/{id}/agent/run/{id}` | Status + result + PR links |
| `codegen_list_runs` | `GET /orgs/{id}/agent/runs` | List runs (filter by status/source) |
| `codegen_resume_run` | `POST /orgs/{id}/agent/run/resume` | Resume blocked run with new instructions |
| `codegen_get_logs` | `GET (alpha) /orgs/{id}/agent/run/{id}/logs` | Step-by-step logs (thought + tool_name + output) |
| `codegen_list_orgs` | `GET /organizations` | User's organizations |
| `codegen_list_repos` | `GET /orgs/{id}/repos` | Organization repositories |

### Key Signatures

```python
@mcp.tool(tags={"execution"})
async def codegen_create_run(
    prompt: str,
    repo_id: int | None = None,
    model: str | None = None,
    agent_type: Literal["codegen", "claude_code"] = "claude_code",
    metadata: dict | None = None,
) -> str:
    """Create a new Codegen agent run.

    Args:
        prompt: Task description (natural language, full context).
        repo_id: Repository ID. None = auto-detect from git remote.
        model: LLM model. None = organization default.
        agent_type: "codegen" or "claude_code".
        metadata: Arbitrary metadata (e.g. {"plan_task": "Task 3"}).

    Returns: JSON {id, status, web_url}
    """

@mcp.tool(tags={"execution"})
async def codegen_get_run(run_id: int) -> str:
    """Get agent run status, result, summary, and created PRs.

    Returns: JSON {id, status, result, summary, web_url, github_pull_requests}
    """

@mcp.tool(tags={"execution"})
async def codegen_get_logs(
    run_id: int,
    limit: int = 50,
    reverse: bool = True,
) -> str:
    """Get step-by-step agent logs (thoughts + tool calls + outputs).

    Args:
        run_id: Agent run ID.
        limit: Max log entries (default 50, max 100).
        reverse: If true, newest first.

    Returns: JSON {logs: [{thought, tool_name, tool_input, tool_output, created_at}], total_logs}
    """

@mcp.tool(tags={"execution"})
async def codegen_resume_run(
    run_id: int,
    prompt: str,
    model: str | None = None,
) -> str:
    """Resume a paused/blocked agent run with new instructions.

    Returns: JSON {id, status, web_url}
    """

@mcp.tool(tags={"setup"})
async def codegen_list_orgs() -> str:
    """List organizations the authenticated user belongs to.

    Returns: JSON {items: [{id, name}]}
    """

@mcp.tool(tags={"setup"})
async def codegen_list_repos(limit: int = 50) -> str:
    """List repositories in the configured organization.

    Returns: JSON {items: [{id, name, full_name, language, setup_status}]}
    """

@mcp.tool(tags={"execution"})
async def codegen_list_runs(
    limit: int = 10,
    source_type: str | None = None,
) -> str:
    """List recent agent runs.

    Args:
        limit: Max results (default 10).
        source_type: Filter by source (API, LOCAL, etc.)

    Returns: JSON {items: [{id, status, created_at, web_url, summary}]}
    """
```

### Auto-detect repo_id

When `repo_id=None`:
1. Run `git remote get-url origin` via subprocess
2. Parse `owner/repo` from GitHub URL
3. Match against `list_repos()` by `full_name`
4. Cache result in module-level dict (per-process lifetime)
5. Raise ToolError if not found

## Skill: executing-via-codegen

### SKILL.md Overview

The skill orchestrates plan execution by creating one Codegen agent run per task, monitoring progress, and reporting results between tasks.

### Workflow

```bash
Step 1: Load plan → parse tasks
Step 2: Setup — codegen_list_repos() to verify repo access
Step 3: For each task:
  a. Build prompt (plan context + task text + constraints)
  b. codegen_create_run(prompt, agent_type="claude_code")
  c. Poll codegen_get_run() every 30s
  d. On completion: codegen_get_logs() → review
  e. On failure/pause: show logs, ask user
  f. Report: what was done, PRs created
  g. Mark task complete in TodoWrite
Step 4: Summary — all PRs, all results
```

### Prompt Construction for Agent Run

Each task prompt includes:
1. **Plan context** — Goal, Architecture, Tech Stack from plan header
2. **Full task text** — all steps verbatim (NOT a file reference)
3. **Constraints** — "Create branch from main. Run tests after each step. Commit with conventional commits."
4. **Previous context** — one-line summary of completed tasks

### Differences from executing-plans

| Aspect | executing-plans | executing-via-codegen |
|--------|----------------|----------------------|
| Execution location | Local terminal | Codegen cloud sandbox |
| Output | Files on disk | PRs on GitHub |
| Monitoring | Direct stdout/stderr | codegen_get_logs() |
| Interruption | Ctrl+C | codegen_resume_run() |
| Git worktree | Required | Not needed (Codegen creates branch) |
| Batch size | 3 tasks per batch | 1 task = 1 agent run |
| Review | Local file diff | PR diff on GitHub |

### Stop Conditions

- Agent run status = "failed" → show logs, ask user (resume/skip/stop)
- Agent run status = "paused" → ask user for guidance → resume_run
- HTTP 402 (billing limit) → inform user, stop execution
- Tests failing in logs → offer resume with fix instructions

## Integration with Superpowers

### How writing-plans discovers the third option

The `executing-via-codegen` skill has a description matching the use case. When `writing-plans` reaches handoff, the LLM sees this skill in available skills and offers:

```text
Plan complete. Three execution options:

1. Subagent-Driven (this session)
2. Parallel Session (separate terminal)
3. Codegen Remote (cloud agent on GitHub)

Which approach?
```

No modification to superpowers plugin is needed — the skill is discovered automatically.

## Error Handling

### HTTP Error Matrix

| Code | Meaning | Action |
|------|---------|--------|
| 200 | OK | Continue |
| 402 | Billing limit reached | Inform user, stop |
| 403 | No permissions | Check API key / org_id |
| 404 | Run not found | Invalid run_id |
| 429 | Rate limited | Wait 60s, retry once |
| 500+ | Server error | Retry once, then report |

### Agent Run Statuses

| Status | Action |
|--------|--------|
| `running` | Continue polling (30s interval) |
| `completed` | Get logs, verify result, next task |
| `failed` | Get logs, show user, offer resume/skip |
| `paused` | Ask user for guidance, resume |

### Security

- API key NEVER logged or shown to user
- MCP server masks auth errors (no key in traces)
- `ToolError` for business errors, generic for unexpected

## Authentication & Configuration

Environment variables:
- `CODEGEN_API_KEY` (required) — Bearer token for Codegen API
- `CODEGEN_ORG_ID` (required) — Organization ID (numeric)

The MCP server validates both on startup and raises a clear error if missing.

## Polling Strategy

- Interval: 30 seconds between `codegen_get_run()` calls
- The skill instructs the LLM to use `sleep 30` in Bash between checks
- Max polling time: 10 minutes per task (configurable via skill instructions)
- Webhooks deferred to v2

## Open Questions (for v2)

1. **Webhook support** — instead of polling, register webhook for run completion
2. **Parallel task execution** — multiple agent runs in parallel for independent tasks
3. **PR merge automation** — auto-merge PRs after successful review
4. **Model selection UI** — `codegen_list_models` tool for interactive model choice
5. **Cost tracking** — track agent runs and estimated costs per plan execution
