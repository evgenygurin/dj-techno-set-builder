# MCP Platform Features (Phase 5) -- Plan Review (Critical)

Date: 2026-02-19
Target plan: `docs/plans/2026-02-19-mcp-platform-features-plan.md`

This is a critical plan review (blockers first). It is written against the current repository state + the actually-installed FastMCP version in this repo (`fastmcp==3.0.0rc2` in `.venv`).

## Executive Summary

Directionally, Phase 5 is the right kind of hardening (OTEL, response limiting/caching, timeouts, elicitation, session state). But as written, it will not be implementable without rework:

- Several tasks and tests assume FastMCP APIs that do not exist in this repo (notably `FastMCP.get_tools()` and `fastmcp.server.tool.ToolResult`).
- Background tasks (`task=True`) are not available with current dependencies (missing `fastmcp[tasks]` / `docket`), so Task 5 is blocked.
- ResponseLimitingMiddleware (as implemented in FastMCP 3.0.0rc2) drops `structured_content` when truncating, so enabling it globally will break agent-grade structured outputs.
- ResponseCachingMiddleware uses a GLOBAL cache key for `list_tools`, which is incompatible with session-specific visibility (`activate_heavy_mode` / `ctx.enable_components`) and any other per-session tool filtering.

Net: tighten the plan around the real FastMCP rc2 APIs, scope limiting/caching carefully, and avoid hard-coding tool names so the phase remains compatible with Phases 1-4.

## Blockers (Must Fix Before Implementation)

### 1) Tests use non-existent FastMCP APIs (`get_tools`)

The plan repeatedly uses `workflow_mcp.get_tools()` and expects `Tool.timeout`, `Tool.version`, etc. (`docs/plans/2026-02-19-mcp-platform-features-plan.md:418`, `docs/plans/2026-02-19-mcp-platform-features-plan.md:1217`)

In `fastmcp==3.0.0rc2`, `FastMCP` does NOT have `get_tools()`; the public API is async `await mcp.list_tools()` (which returns `fastmcp.tools.tool.Tool` objects that *do* have `.timeout`, `.version`, `.task_config`).

Fix:
- Rewrite tests to use `await workflow_mcp.list_tools()` (async tests) and inspect the returned `Tool` objects.
- Avoid brittle internal access like `mcp._tool_manager...` unless there is no public alternative.

### 2) Background tasks are blocked by missing dependencies (`fastmcp[tasks]` / `docket`)

Task 5 assumes `@mcp.tool(task=True, ...)` is available. (`docs/plans/2026-02-19-mcp-platform-features-plan.md:561`)

In this repo, setting `task=True` currently raises:
- `ImportError: FastMCP background tasks require the 'tasks' extra. Install with: pip install 'fastmcp[tasks]'` (triggered by missing `docket`).

Fix:
- Add the missing dependency explicitly:
  - Either add `fastmcp[tasks]` to `pyproject.toml` deps (or to an optional group and ensure CI installs it),
  - or add the underlying `docket` dependency if you want finer control.
- Update the plan to include dependency install + a CI guard test that fails fast if tasks extras are missing.

### 3) ResponseLimitingMiddleware drops structured output on truncation (breaks agent contracts)

Task 2 proposes enabling `ResponseLimitingMiddleware` globally. (`docs/plans/2026-02-19-mcp-platform-features-plan.md:219`)

In FastMCP 3.0.0rc2, when a tool response exceeds max size, the middleware:
- serializes the entire `ToolResult`,
- extracts text,
- returns a new `ToolResult` with a single `TextContent`,
- and **drops `structured_content` entirely**.

Impact:
- Any tool relying on structured output (Pydantic return types in this repo) can silently degrade into “text-only”, making agents brittle.

Fix:
- Use ResponseLimitingMiddleware only for a targeted set of tools that are allowed to degrade (e.g. `ym_*` raw tools), via its `tools=[...]` allowlist.
- Alternatively, implement a custom limiter that truncates only `.content` but preserves `.structured_content` (if you truly need global limiting).

### 4) ResponseCaching plan uses wrong store import and unsafe defaults (list_tools + call_tool)

Task 3 suggests:
- importing `DiskStore` from `fastmcp.utilities.cache` (does not exist in rc2),
- caching `call_tool` broadly,
- and setting `list_tools TTL=0` instead of disabling caching.

In FastMCP rc2:
- ResponseCachingMiddleware expects a `key_value.aio.protocols.key_value.AsyncKeyValue` store.
- A disk-backed store exists in `key_value` (e.g. `key_value.aio.stores.disk.store.DiskStore`).
- `list_tools` caching uses a **GLOBAL_KEY**, not session-aware.

Impact:
- Any session-specific visibility (this repo already has `activate_heavy_mode` and `ctx.enable_components`) makes `list_tools` caching incorrect. Caching it globally risks leaking tool visibility across sessions.
- Caching `call_tool` globally is dangerous for non-idempotent tools (download/build/sync/import); it can skip execution and return cached responses.

Fix:
- Use: `ResponseCachingMiddleware(list_tools_settings={"enabled": False}, ...)` (not TTL=0).
- Configure `call_tool_settings` with `included_tools=[...]` for true read-only tools only, or `excluded_tools=[...]` for all mutating tools.
- Use correct store import path from `key_value` if you want disk persistence.

### 5) ToolResult usage is incorrect (imports + content/structured types)

Task 8 imports ToolResult from `fastmcp.server.tool` and assumes:
- `ToolResult.content` is a string,
- `structured_content` can be a list.

In rc2:
- The import path is `from fastmcp.tools.tool import ToolResult`.
- `ToolResult.content` is a list of MCP content blocks (e.g. `[TextContent(...)]`).
- `structured_content` must be a dict or None (FastMCP raises ValueError on list).

Fix:
- Use `ToolResult(content=[TextContent(...)] or content="...")` but assert on `content[0].text` in tests.
- Wrap lists in a dict: `structured_content={"items": [...]}`
- Or just keep Pydantic return types (already used in this repo) and let FastMCP handle structured output without ToolResult.

### 6) Elicitation helper fails open on decline/cancel (dangerous for destructive ops)

Task 6’s `confirm_action()` treats missing `.data` as an exception and returns True (proceed). (`docs/plans/2026-02-19-mcp-platform-features-plan.md:742`)

But FastMCP’s `ctx.elicit()` returns:
- AcceptedElicitation (has `.data`), or
- DeclinedElicitation / CancelledElicitation (no `.data`).

Impact:
- If a user declines/cancels, your helper will proceed anyway (because it catches AttributeError/Exception and returns True).

Fix:
- Handle the returned union explicitly:
  - accept -> use `.data`
  - decline/cancel -> return False
  - elicitation unsupported -> decide via a config flag (`fail_open` vs `fail_closed`), defaulting to fail-closed for destructive actions.

### 7) Session state helper uses a `default` arg that FastMCP does not support

Task 7 uses `ctx.get_state(key, default=None)` in code and tests. (`docs/plans/2026-02-19-mcp-platform-features-plan.md:839`, `docs/plans/2026-02-19-mcp-platform-features-plan.md:919`)

In FastMCP rc2, `await ctx.get_state(key)` returns None when missing; there is no `default=` parameter.

Fix:
- Use `value = await ctx.get_state(key)` and treat None as “missing”.

## High-Risk / Likely Rework

### 8) “Independent of Phases 1-4” is not true in practice (tool names will change)

Tasks 4/9 hard-code today’s tool names, and Phase 4 explicitly removes/renames many of them (get_playlist_status, import stubs, etc.).

Fix:
- Make Phase 5 checks *tag-based* and *contract-based*:
  - All tools must have `timeout` and `version`.
  - Tools tagged `sync`/`download` must have higher timeouts.
  - Tools with `annotations.readOnlyHint=True` can be cached; mutating tools cannot.
- Keep Phase 5 tests resilient across refactor waves.

### 9) OTEL init placement should consider Sentry/TracerProvider ordering

`app/main.py` currently initializes Sentry before importing FastMCP, with a comment about tracer provider ordering. Adding another tracer provider init in `app/mcp/lifespan.py` can:
- override an already-configured provider,
- produce inconsistent tracing behavior if set after server import.

Fix:
- In `_init_otel`, check if a non-default TracerProvider is already installed; if so, skip or attach processors without overriding (depending on desired behavior).
- Consider moving OTEL init to the same early-init stage as Sentry (or documenting the precedence).

## Concrete Plan Edits I Recommend

1) Add a Task 0: “FastMCP API reality check” (pin to `fastmcp==3.0.0rc2`):
   - Correct imports (`ToolResult`, caching stores).
   - Confirm availability of tasks extra; fail early if missing.

2) Redesign Task 2 + Task 3 around safe scoping:
   - Response limiting: only for known “big response” tools (likely `ym_*`).
   - Caching: disable list_tools caching; cache only read-only tools via included_tools.

3) Replace name-based timeout/version tests with tag/annotation-based policies.

4) Fix elicitation semantics (decline/cancel) and decide fail-open vs fail-closed explicitly per operation class.

