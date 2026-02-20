# FastMCP 3.0.0rc2 API Verification

Verified 2026-02-20 against `fastmcp==3.0.0rc2`.

## Middleware

| Class | Available | Import |
|-------|-----------|--------|
| `ErrorHandlingMiddleware` | YES | `fastmcp.server.middleware.error_handling` |
| `RetryMiddleware` | YES | `fastmcp.server.middleware.error_handling` |
| `AuthMiddleware` | YES | `fastmcp.server.middleware.authorization` |
| `PingMiddleware` | YES | `fastmcp.server.middleware.ping` |
| `ResponseLimitingMiddleware` | **NO** | — |
| `ResponseCachingMiddleware` | **NO** | — |

**Impact:** Tasks 3 (ResponseLimiting) and 4 (ResponseCaching) are **SKIPPED**.

## Context API

| Method | Signature |
|--------|-----------|
| `elicit` | `(message, response_type=None) → Accepted\|Declined\|Cancelled` |
| `set_state` | `(key, value, *, serializable=True) → None` |
| `get_state` | `(key) → Any` |
| `delete_state` | exists |
| `report_progress` | `(progress, total=None, message=None) → None` |
| `info/warning/error/debug` | `(message, logger_name=None, extra=None) → None` |
| `enable_components` | `(names, keys, version, tags, components, match_all)` |
| `disable_components` | exists |
| `reset_visibility` | exists |
| `sample` / `sample_step` | exists |
| `is_background_task` | exists |

## Elicitation Types

```python
from fastmcp.server.elicitation import AcceptedElicitation  # fields: action, data
from mcp.server.elicitation import DeclinedElicitation       # fields: action
from mcp.server.elicitation import CancelledElicitation      # fields: action
```

- `response_type` can be: `type[T]`, `list[str]` (choices), `dict`, `list[list[str]]`, `None`
- `AcceptedElicitation.data` contains the typed response
- Check with `isinstance(result, AcceptedElicitation)`, NOT `result.accepted`

## Tool Decorator

```python
@mcp.tool(
    name=...,
    version=...,      # ✅ exists
    timeout=...,       # ✅ exists (seconds)
    tags={...},
    annotations={...},
    title=...,
    icons=...,
    meta=...,
    auth=...,
)
```

## Decisions

| Feature | Decision |
|---------|----------|
| ResponseLimiting | SKIP — not available |
| ResponseCaching | SKIP — not available |
| Timeouts | Use `@mcp.tool(timeout=N)` |
| Versioning | Use `@mcp.tool(version="1.0.0")` |
| Elicitation | Use `isinstance()` checks, not `.accepted` |
| Session state | `ctx.set_state/get_state`, handle `None` |
