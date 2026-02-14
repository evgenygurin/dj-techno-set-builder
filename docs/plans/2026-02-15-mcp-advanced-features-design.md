# MCP Advanced Features Design

**Date:** 2026-02-15
**Scope:** Sampling, Skills, Pagination, Progress
**Approach:** Incremental integration (A+B) — each feature as a separate module, config via Settings

## Overview

Add 4 FastMCP capabilities to the DJ Set Builder MCP server:

1. **Pagination** — cursor-based list pagination for tools/resources/prompts
2. **Progress** — real-time progress reporting for long-running tools
3. **Sampling** — full LLM sampling with structured output, tool use, and fallback handler
4. **Skills** — DJ workflow recipes exposed as MCP resources

## 1. Pagination

**Complexity:** Trivial (one parameter)

### Changes

| File | Change |
|------|--------|
| `app/config.py` | Add `mcp_page_size: int = 50` |
| `app/mcp/gateway.py` | Pass `list_page_size=settings.mcp_page_size` to FastMCP constructor |

### Behavior

- All list operations (`tools/list`, `resources/list`, `prompts/list`, `resources/templates/list`) return paginated results
- Responses include `nextCursor` (opaque base64 string) when more pages available
- Current tool count (~46) fits in one page at default page_size=50
- Pagination becomes effective as tool count grows

### Tests

- Create server with `list_page_size=2`, register 5 tools, verify cursor-based iteration

## 2. Progress Reporting

**Complexity:** Low-medium (5 tool modifications)

### Tools with Progress

| Tool | Pattern | Stages |
|------|---------|--------|
| `build_set` | Multi-stage (%) | validate(0-10), generate(10-80), score(80-100) |
| `score_transitions` | Absolute count | `i / (n-1)` per track pair |
| `import_playlist` | Absolute count | `i / total` per track |
| `import_tracks` | Absolute count | `i / total` per track |
| `find_similar_tracks` | Multi-stage (%) | profile(0-25), sample(25-75), search(75-100) |

### API Usage

```python
# Absolute counting pattern
for i, item in enumerate(items):
    await ctx.report_progress(progress=i, total=len(items))
    # ... process item ...
await ctx.report_progress(progress=len(items), total=len(items))

# Multi-stage pattern (percentage-based)
await ctx.report_progress(progress=0, total=100)
# Stage 1: Validation
await ctx.report_progress(progress=10, total=100)
# Stage 2: Generation
result = await gen_svc.generate(...)
await ctx.report_progress(progress=80, total=100)
# Stage 3: Scoring
await ctx.report_progress(progress=100, total=100)
```

### Notes

- `report_progress()` is a no-op if client doesn't provide `progressToken` — safe to add unconditionally
- No config changes needed

### Tests

- Mock `ctx.report_progress`, verify call count and argument values for each tool

## 3. Sampling (Full Feature Set)

**Complexity:** High (4 subsystems)

### 3a. Anthropic Fallback Handler

**Config additions:**

```python
# app/config.py
anthropic_api_key: str = ""
sampling_model: str = "claude-sonnet-4-5-20250929"
sampling_max_tokens: int = 1024
```

**Gateway changes:**

```python
# app/mcp/gateway.py
from fastmcp.client.sampling.handlers.anthropic import AnthropicSamplingHandler

handler = None
if settings.anthropic_api_key:
    handler = AnthropicSamplingHandler(default_model=settings.sampling_model)

gateway = FastMCP(
    "DJ Set Builder",
    sampling_handler=handler,
    sampling_handler_behavior="fallback",
    list_page_size=settings.mcp_page_size,
    lifespan=mcp_lifespan,
)
```

**Dependency:** `fastmcp[anthropic]` extra in pyproject.toml

**Behavior:**
- `"fallback"` mode: use handler only when client doesn't support sampling
- When `anthropic_api_key` is empty, handler is `None` → existing graceful fallback in tools still works
- Sentry-connected tools (find_similar_tracks, adjust_set) keep their try/except for NotImplementedError

### 3b. Structured Output (result_type)

**New types in `app/mcp/types.py`:**

```python
class SwapSuggestion(BaseModel):
    """Suggestion to swap a track at a position."""
    position: int
    reason: str

class ReorderSuggestion(BaseModel):
    """Suggestion to move a track to a new position."""
    from_position: int
    to_position: int
    reason: str

class AdjustmentPlan(BaseModel):
    """LLM-generated plan for adjusting a DJ set."""
    reasoning: str
    swap_suggestions: list[SwapSuggestion]
    reorder_suggestions: list[ReorderSuggestion]
```

**Refactored tools:**

| Tool | result_type | What changes |
|------|-------------|-------------|
| `find_similar_tracks` | `SearchStrategy` (existing) | Replace string parsing with `result.result` |
| `adjust_set` | `AdjustmentPlan` (new) | Replace string parsing with validated plan |

**Example (find_similar_tracks):**

```python
result = await ctx.sample(
    messages=profile_text,
    system_prompt="You are a DJ assistant analyzing playlist profiles...",
    result_type=SearchStrategy,
    max_tokens=settings.sampling_max_tokens,
)
strategy: SearchStrategy = result.result
```

### 3c. Tool Use in Sampling

**`find_similar_tracks` — agentic workflow:**

Give the LLM access to `search_by_criteria` as a sampling tool:

```python
def _search_tool(bpm_min: float, bpm_max: float,
                 keys: list[str] | None = None,
                 energy_min: float | None = None,
                 energy_max: float | None = None) -> list[dict]:
    """Search local tracks by audio criteria."""
    # Thin wrapper around search_by_criteria logic
    ...

result = await ctx.sample(
    messages=profile_text,
    tools=[_search_tool],
    result_type=SimilarTracksResult,
    max_tokens=settings.sampling_max_tokens,
)
```

The LLM will:
1. Analyze the playlist profile
2. Call `_search_tool` with appropriate criteria
3. Review results and call again with adjusted criteria
4. Return a structured `SimilarTracksResult`

### 3d. sample_step() for adjust_set

Fine-grained control loop for set adjustment:

```python
async def _adjust_with_sampling(ctx, items, instructions, svc):
    """Run agentic adjustment loop with manual step control."""
    messages = [build_adjustment_prompt(items, instructions)]

    while True:
        step = await ctx.sample_step(
            messages=messages,
            tools=[score_transition_fn, get_track_details_fn],
            execute_tools=True,
        )

        if step.is_tool_use:
            for call in step.tool_calls:
                await ctx.report_progress(...)  # Progress + tool use combined
            messages = step.history
            continue

        # Final response — parse as AdjustmentPlan
        return step.text
```

### Tests

- **Fallback handler:** Mock AnthropicSamplingHandler, verify it's used when client lacks sampling
- **Structured output:** Mock `ctx.sample()` returning JSON, verify Pydantic validation
- **Tool use:** Mock tools + sample(), verify tool calls happen
- **sample_step:** Mock step responses, verify loop terminates correctly

## 4. Skills Provider

**Complexity:** Medium (new directory + provider integration)

### Directory Structure

```text
app/mcp/skills/
├── expand-playlist/
│   └── SKILL.md
├── build-set-from-scratch/
│   └── SKILL.md
└── improve-set/
    └── SKILL.md
```

### Skill Content (from existing prompts)

Each SKILL.md contains YAML frontmatter + step-by-step instructions derived from
the corresponding prompt function in `app/mcp/prompts/workflows.py`.

**Example — expand-playlist/SKILL.md:**

```markdown
---
description: Expand a playlist with similar tracks and build an optimized DJ set
---

# Expand Playlist

## Parameters
- playlist_name: Name of the playlist to expand
- count: Number of tracks to add (default: 20)
- style: Target style (default: "dark techno")

## Steps
1. Use `dj_get_playlist_status` to analyze the current playlist
2. Use `dj_find_similar_tracks` to discover {count} similar tracks matching {style}
3. Use `dj_build_set` to create an optimized DJ set from the expanded playlist
4. Use `dj_score_transitions` to verify transition quality
5. If average score < 0.7, use `dj_adjust_set` to improve weak transitions
```

### Gateway Integration

```python
# app/mcp/gateway.py
from pathlib import Path
from fastmcp.server.providers.skills import SkillsDirectoryProvider

skills_dir = Path(__file__).parent / "skills"
if skills_dir.exists():
    gateway.add_provider(SkillsDirectoryProvider(
        roots=skills_dir,
        supporting_files="template",
    ))
```

### Resource URIs

| URI | Content |
|-----|---------|
| `skill://expand-playlist/SKILL.md` | Skill instructions |
| `skill://expand-playlist/_manifest` | File listing with SHA256 hashes |
| `skill://build-set-from-scratch/SKILL.md` | Skill instructions |
| `skill://build-set-from-scratch/_manifest` | File listing |
| `skill://improve-set/SKILL.md` | Skill instructions |
| `skill://improve-set/_manifest` | File listing |

### Relationship with Existing Prompts

Skills complement, not replace, prompts:
- **Prompts** (MCP protocol): Tool-calling clients use them for structured multi-step flows
- **Skills** (MCP resources): Human-in-the-loop workflows, shareable DJ recipes

### Tests

- SkillsDirectoryProvider finds 3 skills
- Manifest contains correct file count and SHA256 hashes
- SKILL.md readable via resource URI
- Frontmatter `description` parsed correctly

## Config Summary

New settings in `app/config.py`:

```python
# Pagination
mcp_page_size: int = 50

# Sampling
anthropic_api_key: str = ""
sampling_model: str = "claude-sonnet-4-5-20250929"
sampling_max_tokens: int = 1024
```

New dependency in `pyproject.toml`:

```toml
[project.optional-dependencies]
anthropic = ["fastmcp[anthropic]"]
```

## Files Changed

| File | Changes |
|------|---------|
| `app/config.py` | 4 new settings |
| `app/mcp/gateway.py` | Pagination, sampling handler, skills provider |
| `app/mcp/types.py` | SwapSuggestion, ReorderSuggestion, AdjustmentPlan |
| `app/mcp/workflows/discovery_tools.py` | Structured output + tool use in find_similar_tracks |
| `app/mcp/workflows/setbuilder_tools.py` | Progress + sample_step in build_set, score_transitions, adjust_set |
| `app/mcp/workflows/import_tools.py` | Progress in import_playlist, import_tracks |
| `app/mcp/skills/expand-playlist/SKILL.md` | New file |
| `app/mcp/skills/build-set-from-scratch/SKILL.md` | New file |
| `app/mcp/skills/improve-set/SKILL.md` | New file |
| `pyproject.toml` | anthropic optional dependency |
| `.env.example` | New env vars |
| `tests/mcp/test_pagination.py` | New |
| `tests/mcp/test_progress.py` | New |
| `tests/mcp/test_sampling.py` | New |
| `tests/mcp/test_skills.py` | New |

## Implementation Order

1. **Pagination** — trivial, unlocks infra
2. **Progress** — independent, additive
3. **Skills** — independent, new files only
4. **Sampling** — depends on config changes from (1), most complex
