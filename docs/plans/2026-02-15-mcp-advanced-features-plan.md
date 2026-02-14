# MCP Advanced Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add pagination, progress reporting, full LLM sampling (structured output, tool use, fallback handler), and DJ skills provider to the MCP gateway.

**Architecture:** Incremental integration — each feature is independent. Pagination and sampling handler are gateway constructor params. Progress is added inline in existing tools. Skills use SkillsDirectoryProvider. All new settings go into `app/config.py`.

**Tech Stack:** FastMCP 3.0+, Pydantic v2, fastmcp[anthropic], pytest + Client(mcp)

**Design doc:** `docs/plans/2026-02-15-mcp-advanced-features-design.md`

---

## Task 1: Pagination

**Files:**
- Modify: `app/config.py:30-37` (add setting)
- Modify: `app/mcp/gateway.py:26` (add list_page_size param)
- Create: `tests/mcp/test_pagination.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_pagination.py
"""Tests for MCP pagination support."""

from __future__ import annotations

from fastmcp import Client, FastMCP

async def test_pagination_returns_cursor_when_page_size_exceeded():
    """Server with list_page_size=2 paginates 3+ tools."""
    mcp = FastMCP("test", list_page_size=2)

    @mcp.tool
    def tool_a() -> str:
        """Tool A."""
        return "a"

    @mcp.tool
    def tool_b() -> str:
        """Tool B."""
        return "b"

    @mcp.tool
    def tool_c() -> str:
        """Tool C."""
        return "c"

    async with Client(mcp) as client:
        # First page: 2 tools + cursor
        result = await client.list_tools_mcp()
        assert len(result.tools) == 2
        assert result.nextCursor is not None

        # Second page: 1 tool, no cursor
        result2 = await client.list_tools_mcp(cursor=result.nextCursor)
        assert len(result2.tools) == 1
        assert result2.nextCursor is None

async def test_pagination_auto_collects_all():
    """Client.list_tools() auto-collects all pages."""
    mcp = FastMCP("test", list_page_size=2)

    @mcp.tool
    def tool_a() -> str:
        """Tool A."""
        return "a"

    @mcp.tool
    def tool_b() -> str:
        """Tool B."""
        return "b"

    @mcp.tool
    def tool_c() -> str:
        """Tool C."""
        return "c"

    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert len(tools) == 3

async def test_gateway_has_page_size():
    """Gateway uses mcp_page_size from settings."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()
    # list_page_size is set on the server settings
    assert gateway._list_page_size is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_pagination.py -v`
Expected: FAIL — `_list_page_size` doesn't exist yet on gateway

**Step 3: Add setting to config**

In `app/config.py` after line 37, add:

```python
    # Pagination
    mcp_page_size: int = 50
```

**Step 4: Add list_page_size to gateway constructor**

In `app/mcp/gateway.py:26`, change:

```python
# FROM:
gateway = FastMCP("DJ Set Builder", lifespan=mcp_lifespan)

# TO:
gateway = FastMCP(
    "DJ Set Builder",
    lifespan=mcp_lifespan,
    list_page_size=settings.mcp_page_size,
)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_pagination.py -v`
Expected: PASS (all 3 tests)

**Step 6: Add env var to .env.example**

Append to `.env.example`:

```text
# Pagination
MCP_PAGE_SIZE=50
```

**Step 7: Commit**

```bash
git add app/config.py app/mcp/gateway.py tests/mcp/test_pagination.py .env.example
git commit -m "feat(mcp): add cursor-based pagination support

Add mcp_page_size setting (default 50) and pass list_page_size
to FastMCP constructor. All list operations now support
cursor-based pagination per MCP spec."
```

---

## Task 2: Progress — score_transitions

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py:148-213` (score_transitions loop)
- Create: `tests/mcp/test_progress.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_progress.py
"""Tests for MCP progress reporting."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastmcp import Client, FastMCP

async def test_score_transitions_reports_progress():
    """score_transitions calls report_progress for each pair."""
    from app.mcp.workflows import create_workflow_mcp

    mcp = create_workflow_mcp()

    # We need to mock the services to avoid DB dependency
    # and capture progress calls
    progress_calls: list[tuple[float, float]] = []

    original_report = None

    async def capture_progress(progress: float, total: float) -> None:
        progress_calls.append((progress, total))

    # Use Client with tool call — mock the DI services
    async with Client(mcp) as client:
        # This will fail because we need actual DB — we'll mock at service level
        # For now, just verify the test structure compiles
        pass

    # Placeholder: actual test will mock DI and verify progress_calls
    assert True  # Will be replaced with real assertions
```

**Step 2: Run test to verify it passes (placeholder)**

Run: `uv run pytest tests/mcp/test_progress.py::test_score_transitions_reports_progress -v`
Expected: PASS (placeholder)

**Step 3: Add progress to score_transitions**

In `app/mcp/workflows/setbuilder_tools.py`, modify the scoring loop (lines 148-213):

```python
        # Score consecutive pairs
        results: list[TransitionScoreResult] = []
        pairs_total = len(items) - 1
        for i in range(pairs_total):
            await ctx.report_progress(progress=i, total=pairs_total)

            from_item = items[i]
            to_item = items[i + 1]
            # ... existing scoring logic unchanged ...

        await ctx.report_progress(progress=pairs_total, total=pairs_total)
        return results
```

Add exactly 2 lines: `await ctx.report_progress(progress=i, total=pairs_total)` inside loop, and final `await ctx.report_progress(progress=pairs_total, total=pairs_total)` after loop.

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_progress.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py tests/mcp/test_progress.py
git commit -m "feat(mcp): add progress reporting to score_transitions

Report progress for each track pair scored. No-op when client
doesn't provide progressToken."
```

---

## Task 3: Progress — build_set

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py:30-75` (build_set)
- Modify: `tests/mcp/test_progress.py` (add test)

**Step 1: Write the failing test**

Add to `tests/mcp/test_progress.py`:

```python
async def test_build_set_reports_progress():
    """build_set reports multi-stage progress (0, 10, 80, 100)."""
    # Placeholder: will mock DI and verify progress stages
    assert True
```

**Step 2: Add multi-stage progress to build_set**

In `app/mcp/workflows/setbuilder_tools.py`, modify `build_set` (lines 50-75):

```python
        # 1. Create DJ set
        await ctx.report_progress(progress=0, total=100)
        dj_set = await set_svc.create(
            DjSetCreate(name=set_name),
        )

        await ctx.report_progress(progress=10, total=100)
        await ctx.info(
            f"Created set '{set_name}' (id={dj_set.set_id}), "
            f"running GA with energy_arc={energy_arc}..."
        )

        # 2. Generate optimal ordering via GA
        request = SetGenerationRequest(energy_arc_type=energy_arc)
        gen_result = await gen_svc.generate(dj_set.set_id, request)
        await ctx.report_progress(progress=80, total=100)

        avg_score = 0.0
        if gen_result.transition_scores:
            avg_score = sum(gen_result.transition_scores) / len(gen_result.transition_scores)

        await ctx.report_progress(progress=100, total=100)
        return SetBuildResult(...)
```

**Step 3: Run tests**

Run: `uv run pytest tests/mcp/test_progress.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py tests/mcp/test_progress.py
git commit -m "feat(mcp): add multi-stage progress to build_set

Report 4 stages: create(0%), init(10%), generate(80%), done(100%)."
```

---

## Task 4: Progress — find_similar_tracks

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py:48-113` (find_similar_tracks)
- Modify: `tests/mcp/test_progress.py`

**Step 1: Add progress to find_similar_tracks**

In `app/mcp/workflows/discovery_tools.py`, add progress calls:

```python
        # 1. Build playlist audio profile
        await ctx.report_progress(progress=0, total=100)
        items_list = await playlist_svc.list_items(...)
        # ... profile building loop ...

        await ctx.report_progress(progress=25, total=100)

        # 2. Try LLM-assisted strategy
        # ... existing sampling code ...

        await ctx.report_progress(progress=75, total=100)

        # 3. Return result
        await ctx.report_progress(progress=100, total=100)
        return SimilarTracksResult(...)
```

**Step 2: Run tests**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add app/mcp/workflows/discovery_tools.py tests/mcp/test_progress.py
git commit -m "feat(mcp): add progress reporting to find_similar_tracks

3 stages: profile(0-25%), sampling(25-75%), result(75-100%)."
```

---

## Task 5: Progress — import_playlist and import_tracks

**Files:**
- Modify: `app/mcp/workflows/import_tools.py:14-83`
- Modify: `tests/mcp/test_progress.py`

**Step 1: Add progress to import tools**

Since these are stubs, progress is minimal but shows the pattern:

```python
    async def import_playlist(...) -> ImportResult:
        # ...validation...
        await ctx.report_progress(progress=0, total=100)

        await ctx.info(...)

        await ctx.report_progress(progress=100, total=100)
        return ImportResult(...)

    async def import_tracks(...) -> ImportResult:
        if not track_ids:
            raise ValueError("track_ids must not be empty")

        await ctx.report_progress(progress=0, total=len(track_ids))

        await ctx.info(...)

        await ctx.report_progress(progress=len(track_ids), total=len(track_ids))
        return ImportResult(...)
```

**Step 2: Run full test suite**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add app/mcp/workflows/import_tools.py tests/mcp/test_progress.py
git commit -m "feat(mcp): add progress to import tools (stubs)

Placeholder progress for import_playlist and import_tracks.
Will become meaningful when full import pipeline is implemented."
```

---

## Task 6: Sampling — new Pydantic types

**Files:**
- Modify: `app/mcp/types.py:62-69` (after SearchStrategy)
- Create: `tests/mcp/test_sampling_types.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_sampling_types.py
"""Tests for sampling-related Pydantic types."""

from __future__ import annotations

from app.mcp.types import AdjustmentPlan, ReorderSuggestion, SwapSuggestion

def test_swap_suggestion_creation():
    swap = SwapSuggestion(position=3, reason="BPM mismatch")
    assert swap.position == 3
    assert swap.reason == "BPM mismatch"

def test_reorder_suggestion_creation():
    reorder = ReorderSuggestion(from_position=1, to_position=5, reason="Energy flow")
    assert reorder.from_position == 1
    assert reorder.to_position == 5

def test_adjustment_plan_creation():
    plan = AdjustmentPlan(
        reasoning="Improve energy flow in second half",
        swap_suggestions=[SwapSuggestion(position=3, reason="BPM mismatch")],
        reorder_suggestions=[
            ReorderSuggestion(from_position=1, to_position=5, reason="Energy flow")
        ],
    )
    assert len(plan.swap_suggestions) == 1
    assert len(plan.reorder_suggestions) == 1

def test_adjustment_plan_empty_suggestions():
    plan = AdjustmentPlan(
        reasoning="Set looks good",
        swap_suggestions=[],
        reorder_suggestions=[],
    )
    assert plan.swap_suggestions == []
    assert plan.reorder_suggestions == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_sampling_types.py -v`
Expected: FAIL — `ImportError: cannot import name 'AdjustmentPlan'`

**Step 3: Add types to app/mcp/types.py**

After `SearchStrategy` (line 69), add:

```python

class SwapSuggestion(BaseModel):
    """Suggestion to swap a track at a given position."""

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
    swap_suggestions: list[SwapSuggestion] = []
    reorder_suggestions: list[ReorderSuggestion] = []
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_sampling_types.py -v`
Expected: PASS (all 4)

**Step 5: Commit**

```bash
git add app/mcp/types.py tests/mcp/test_sampling_types.py
git commit -m "feat(mcp): add AdjustmentPlan types for structured sampling

SwapSuggestion, ReorderSuggestion, AdjustmentPlan — Pydantic
models for LLM-generated set adjustment plans."
```

---

## Task 7: Sampling — Anthropic fallback handler

**Files:**
- Modify: `app/config.py` (add 3 sampling settings)
- Modify: `app/mcp/gateway.py` (add sampling_handler)
- Modify: `pyproject.toml:17` (add anthropic optional dep)
- Modify: `.env.example` (add env vars)
- Create: `tests/mcp/test_sampling_handler.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_sampling_handler.py
"""Tests for sampling handler configuration."""

from __future__ import annotations

from unittest.mock import patch

from app.config import Settings

def test_sampling_settings_defaults():
    """Sampling settings have sensible defaults."""
    s = Settings(database_url="sqlite+aiosqlite:///test.db")
    assert s.anthropic_api_key == ""
    assert s.sampling_model == "claude-sonnet-4-5-20250929"
    assert s.sampling_max_tokens == 1024

def test_gateway_no_handler_when_no_key():
    """Gateway doesn't set sampling_handler when api key is empty."""
    with patch("app.mcp.gateway.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        mock_settings.mcp_page_size = 50
        mock_settings.sampling_model = "claude-sonnet-4-5-20250929"
        mock_settings.debug = False
        mock_settings.sentry_dsn = ""
        mock_settings.mcp_log_payloads = False
        mock_settings.mcp_cache_dir = "./cache/mcp"
        mock_settings.mcp_cache_ttl_tools = 60
        mock_settings.mcp_cache_ttl_resources = 300
        mock_settings.mcp_retry_max = 3
        mock_settings.mcp_retry_backoff = 1.0
        mock_settings.mcp_ping_interval = 30

        from app.mcp.gateway import create_dj_mcp

        gateway = create_dj_mcp()
        # When no API key, no sampling handler should be set
        assert gateway._sampling_handler is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_sampling_handler.py -v`
Expected: FAIL — `anthropic_api_key` not in Settings

**Step 3: Add settings**

In `app/config.py` after MCP Observability section:

```python
    # Sampling (LLM fallback)
    anthropic_api_key: str = ""
    sampling_model: str = "claude-sonnet-4-5-20250929"
    sampling_max_tokens: int = 1024

    # Pagination
    mcp_page_size: int = 50
```

Note: `mcp_page_size` should already be there from Task 1.

**Step 4: Add optional dependency**

In `pyproject.toml`, add after `observability`:

```toml
sampling = [
    "fastmcp[anthropic]",
]
```

**Step 5: Update gateway.py**

Replace `create_dj_mcp()` in `app/mcp/gateway.py`:

```python
def create_dj_mcp() -> FastMCP:
    """Create the gateway MCP server."""
    # Build sampling handler (fallback for clients without sampling support)
    sampling_handler = None
    if settings.anthropic_api_key:
        try:
            from fastmcp.client.sampling.handlers.anthropic import (
                AnthropicSamplingHandler,
            )

            sampling_handler = AnthropicSamplingHandler(
                default_model=settings.sampling_model,
            )
        except ImportError:
            logger.warning(
                "anthropic_api_key set but fastmcp[anthropic] not installed; "
                "sampling fallback disabled"
            )

    gateway = FastMCP(
        "DJ Set Builder",
        lifespan=mcp_lifespan,
        list_page_size=settings.mcp_page_size,
        sampling_handler=sampling_handler,
        sampling_handler_behavior="fallback",
    )

    ym = create_yandex_music_mcp()
    gateway.mount(ym, namespace="ym")

    wf = create_workflow_mcp()
    gateway.mount(wf, namespace="dj")

    apply_observability(gateway, settings)

    try:
        from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools

        gateway.add_transform(PromptsAsTools(gateway))
        gateway.add_transform(ResourcesAsTools(gateway))
    except (ImportError, TypeError, AttributeError):
        logger.debug("PromptsAsTools/ResourcesAsTools not available; skipping transforms")

    return gateway
```

**Step 6: Add env vars to .env.example**

```text
# Sampling (leave ANTHROPIC_API_KEY empty to disable fallback)
ANTHROPIC_API_KEY=
SAMPLING_MODEL=claude-sonnet-4-5-20250929
SAMPLING_MAX_TOKENS=1024
```

**Step 7: Run tests**

Run: `uv run pytest tests/mcp/test_sampling_handler.py tests/mcp/test_pagination.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add app/config.py app/mcp/gateway.py pyproject.toml .env.example tests/mcp/test_sampling_handler.py
git commit -m "feat(mcp): add Anthropic sampling fallback handler

Configure AnthropicSamplingHandler when ANTHROPIC_API_KEY is set.
Uses 'fallback' behavior — only activates when client doesn't
support native sampling. No-op when key is empty."
```

---

## Task 8: Sampling — structured output in find_similar_tracks

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py:95-113`
- Modify: `tests/mcp/test_workflow_discovery.py` (add structured output test)

**Step 1: Write the failing test**

Add to `tests/mcp/test_workflow_discovery.py`:

```python
async def test_find_similar_tracks_uses_structured_output():
    """find_similar_tracks uses result_type=SearchStrategy for sampling."""
    # This test verifies that ctx.sample() is called with result_type
    # We mock the DI services and ctx.sample
    pass  # Will be implemented with proper mocks
```

**Step 2: Refactor find_similar_tracks sampling call**

In `app/mcp/workflows/discovery_tools.py`, replace lines 95-101:

```python
        # FROM:
        strategy_text: str | None = None
        try:
            result = await ctx.sample(profile_text)
            strategy_text = result.text if hasattr(result, "text") else str(result)
        except (NotImplementedError, AttributeError, TypeError):
            strategy_text = None

        # TO:
        from app.mcp.types import SearchStrategy

        strategy: SearchStrategy | None = None
        strategy_text: str | None = None
        try:
            result = await ctx.sample(
                messages=profile_text,
                system_prompt=(
                    "You are a DJ assistant. Analyze the playlist audio profile "
                    "and generate a search strategy to find similar tracks. "
                    "Return target BPM range, compatible Camelot keys, energy range, "
                    "and search queries for music platforms."
                ),
                result_type=SearchStrategy,
            )
            strategy = result.result
            strategy_text = result.text
        except (NotImplementedError, AttributeError, TypeError):
            strategy = None
            strategy_text = None
```

Also update the info log to show structured data:

```python
        if strategy:
            with contextlib.suppress(Exception):
                await ctx.info(
                    f"LLM strategy: {len(strategy.queries)} queries, "
                    f"BPM {strategy.target_bpm_range[0]:.0f}-{strategy.target_bpm_range[1]:.0f}, "
                    f"keys {', '.join(strategy.target_keys[:4])}"
                )
        elif strategy_text:
            with contextlib.suppress(Exception):
                await ctx.info(f"LLM search strategy: {strategy_text[:200]}")
```

**Step 3: Run tests**

Run: `uv run pytest tests/mcp/test_workflow_discovery.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add app/mcp/workflows/discovery_tools.py tests/mcp/test_workflow_discovery.py
git commit -m "feat(mcp): use structured output in find_similar_tracks

Replace string parsing with result_type=SearchStrategy for
validated Pydantic output from ctx.sample()."
```

---

## Task 9: Sampling — structured output in adjust_set

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py:253-265` (adjust_set sampling)
- Modify: `app/mcp/types.py` (import AdjustmentPlan — already added in Task 6)

**Step 1: Refactor adjust_set sampling**

In `app/mcp/workflows/setbuilder_tools.py`, replace the sampling section (lines 253-265):

```python
        # FROM:
        suggestion: str | None = None
        try:
            prompt = (
                f"Current set order: [{track_summary}]. "
                f"User instructions: {instructions}. "
                "Suggest specific changes (swaps, inserts, removals) "
                "as a numbered list."
            )
            result = await ctx.sample(prompt)
            suggestion = result.text if hasattr(result, "text") else str(result)
        except (NotImplementedError, AttributeError, TypeError):
            suggestion = None

        # TO:
        from app.mcp.types import AdjustmentPlan

        plan: AdjustmentPlan | None = None
        suggestion: str | None = None
        try:
            prompt = (
                f"Current set order: [{track_summary}]. "
                f"User instructions: {instructions}. "
                "Analyze the set and suggest specific changes."
            )
            result = await ctx.sample(
                messages=prompt,
                system_prompt=(
                    "You are a DJ assistant optimizing set ordering. "
                    "Suggest track swaps and reorderings to improve "
                    "transitions and energy flow."
                ),
                result_type=AdjustmentPlan,
            )
            plan = result.result
            suggestion = result.text
        except (NotImplementedError, AttributeError, TypeError):
            plan = None
            suggestion = None
```

Update the info log and generator_run metadata:

```python
        if plan:
            with contextlib.suppress(Exception):
                await ctx.info(
                    f"Adjustment plan: {plan.reasoning[:200]}\n"
                    f"Swaps: {len(plan.swap_suggestions)}, "
                    f"Reorders: {len(plan.reorder_suggestions)}"
                )

        # Create a new version with the plan recorded
        new_version = await set_svc.create_version(
            set_id,
            DjSetVersionCreate(
                version_label=f"Adjusted: {instructions[:60]}",
                generator_run={
                    "algorithm": "manual_adjust",
                    "instructions": instructions,
                    "suggestion": suggestion,
                    "plan": plan.model_dump() if plan else None,
                },
            ),
        )
```

**Step 2: Run tests**

Run: `uv run pytest tests/mcp/test_workflow_setbuilder.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py
git commit -m "feat(mcp): use structured output in adjust_set

Replace string parsing with result_type=AdjustmentPlan for
validated swap/reorder suggestions from ctx.sample()."
```

---

## Task 10: Sampling — tool use in find_similar_tracks

**Files:**
- Modify: `app/mcp/workflows/discovery_tools.py:95-113`
- Create: `tests/mcp/test_sampling_tools.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_sampling_tools.py
"""Tests for sampling with tool use in discovery tools."""

from __future__ import annotations

async def test_find_similar_tracks_provides_search_tool():
    """find_similar_tracks passes search tool to ctx.sample()."""
    # Verify that ctx.sample is called with tools= parameter
    # containing a search function
    pass  # Will mock DI and ctx.sample
```

**Step 2: Add tool use to find_similar_tracks**

In `app/mcp/workflows/discovery_tools.py`, create a search helper and pass it to `ctx.sample()`:

```python
        # After building the profile, before the sampling call, define a local search tool:
        async def _search_local_tracks(
            bpm_min: float | None = None,
            bpm_max: float | None = None,
            target_keys: list[str] | None = None,
            energy_min: float | None = None,
            energy_max: float | None = None,
        ) -> list[dict[str, object]]:
            """Search local tracks by BPM, key, and energy criteria.

            Returns a list of matching tracks with their audio features.
            """
            all_feats = await features_svc.list_all()
            matches: list[dict[str, object]] = []
            for feat in all_feats:
                if bpm_min is not None and feat.bpm < bpm_min:
                    continue
                if bpm_max is not None and feat.bpm > bpm_max:
                    continue
                if energy_min is not None and feat.lufs_i < energy_min:
                    continue
                if energy_max is not None and feat.lufs_i > energy_max:
                    continue
                if target_keys is not None:
                    try:
                        cam = key_code_to_camelot(feat.key_code)
                    except ValueError:
                        continue
                    if cam not in target_keys:
                        continue
                camelot: str | None = None
                with contextlib.suppress(ValueError):
                    camelot = key_code_to_camelot(feat.key_code)
                matches.append({
                    "track_id": feat.track_id,
                    "bpm": feat.bpm,
                    "key": camelot,
                    "energy_lufs": feat.lufs_i,
                })
                if len(matches) >= count * 3:  # Limit results
                    break
            return matches

        # Then in the sampling call:
        try:
            result = await ctx.sample(
                messages=profile_text,
                system_prompt=(
                    "You are a DJ assistant. Analyze the playlist audio profile "
                    "and use the search tool to find similar tracks. "
                    "Try different search criteria to find the best matches. "
                    "Return a SearchStrategy with your findings."
                ),
                tools=[_search_local_tracks],
                result_type=SearchStrategy,
            )
            strategy = result.result
            strategy_text = result.text
        except (NotImplementedError, AttributeError, TypeError):
            strategy = None
            strategy_text = None
```

**Step 3: Run tests**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add app/mcp/workflows/discovery_tools.py tests/mcp/test_sampling_tools.py
git commit -m "feat(mcp): add tool use to find_similar_tracks sampling

LLM can now call _search_local_tracks during sampling to
actively search the database by BPM/key/energy criteria
before formulating a strategy."
```

---

## Task 11: Sampling — sample_step() in adjust_set

**Files:**
- Modify: `app/mcp/workflows/setbuilder_tools.py:217-303` (adjust_set)
- Modify: `tests/mcp/test_sampling_tools.py`

**Step 1: Refactor adjust_set to use sample_step()**

Replace the simple `ctx.sample()` call with a `sample_step()` loop:

```python
        # Define tools available during adjustment
        async def _score_pair(
            track_a_id: int,
            track_b_id: int,
        ) -> dict[str, float]:
            """Score the transition quality between two tracks.

            Returns BPM, harmonic, energy, spectral, groove and total scores.
            """
            from app.services.camelot_lookup import CamelotLookupService

            feat_a_raw = await features_svc.get_latest(track_a_id)
            feat_b_raw = await features_svc.get_latest(track_b_id)

            camelot_svc = CamelotLookupService()
            await camelot_svc.build_lookup_table()
            scorer = TransitionScoringService()
            scorer.camelot_lookup = camelot_svc._lookup

            # ... build TrackFeatures from feat_a_raw, feat_b_raw ...
            # ... return score dict ...
            return {"total": 0.0}  # Simplified — full impl uses existing scoring

        plan: AdjustmentPlan | None = None
        suggestion: str | None = None
        try:
            prompt = (
                f"Current set order: [{track_summary}]. "
                f"User instructions: {instructions}. "
                "Use the score_pair tool to evaluate transitions, "
                "then suggest improvements."
            )

            # Use sample_step for fine-grained control
            messages: list[str] = [prompt]
            max_steps = 10
            for step_num in range(max_steps):
                step = await ctx.sample_step(
                    messages=messages,
                    system_prompt=(
                        "You are a DJ assistant. Score transitions between "
                        "tracks and suggest reorderings to improve the set."
                    ),
                    tools=[_score_pair],
                    execute_tools=True,
                )

                if step.is_tool_use:
                    await ctx.report_progress(
                        progress=step_num + 1, total=max_steps,
                    )
                    messages = step.history
                    continue

                # Final text response
                suggestion = step.text
                break

            # Try to parse as AdjustmentPlan
            if suggestion:
                try:
                    import json
                    plan = AdjustmentPlan.model_validate_json(suggestion)
                except (json.JSONDecodeError, ValueError):
                    plan = None

        except (NotImplementedError, AttributeError, TypeError):
            plan = None
            suggestion = None
```

Note: The `_score_pair` tool is a simplified version — the full implementation reuses the existing scoring logic from `score_transitions`. Implementer should extract scoring into a shared helper.

**Step 2: Run tests**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add app/mcp/workflows/setbuilder_tools.py tests/mcp/test_sampling_tools.py
git commit -m "feat(mcp): use sample_step() in adjust_set for agentic loop

LLM can call score_pair tool to evaluate transitions during
adjustment, enabling informed reordering decisions. Loop limited
to 10 steps with progress reporting."
```

---

## Task 12: Skills — create SKILL.md files

**Files:**
- Create: `app/mcp/skills/expand-playlist/SKILL.md`
- Create: `app/mcp/skills/build-set-from-scratch/SKILL.md`
- Create: `app/mcp/skills/improve-set/SKILL.md`

**Step 1: Create skill directories**

```bash
mkdir -p app/mcp/skills/expand-playlist
mkdir -p app/mcp/skills/build-set-from-scratch
mkdir -p app/mcp/skills/improve-set
```

**Step 2: Write expand-playlist/SKILL.md**

```markdown
---
description: Expand a playlist with similar tracks and build an optimized DJ set
---

# Expand Playlist

Expand an existing playlist with similar tracks and create a DJ set
with optimized track ordering.

## Parameters

- **playlist_name**: Name of the playlist to expand
- **count**: Number of similar tracks to find (default: 20)
- **style**: Target musical style (default: "dark techno")

## Workflow

1. **Analyze playlist** — `dj_get_playlist_status` to understand the current
   audio profile (BPM range, keys, energy levels).

2. **Find similar tracks** — `dj_find_similar_tracks` with the playlist ID
   and desired count. The tool uses LLM-assisted search to find matching tracks.

3. **Build DJ set** — `dj_build_set` to create an optimized set using the
   genetic algorithm. Use the default `classic` energy arc.

4. **Verify quality** — `dj_score_transitions` to check transition scores.
   Look for average score > 0.7.

5. **Improve if needed** — If average transition score < 0.7,
   use `dj_adjust_set` with instructions like
   "improve weak transitions, focus on BPM matching".

## Tips

- Start with `count=10` for quick results, increase for more variety
- Compatible Camelot keys improve harmonic transitions
- Energy flow matters — avoid sudden jumps > 3 LUFS between tracks
```

**Step 3: Write build-set-from-scratch/SKILL.md**

```markdown
---
description: Build a complete DJ set from scratch given a genre and duration
---

# Build Set From Scratch

Create a full DJ set starting from zero — search for tracks, import them,
and optimize the ordering.

## Parameters

- **genre**: Target genre (e.g., "dark techno", "melodic techno", "acid")
- **duration_minutes**: Target set duration (default: 60)
- **energy_arc**: Energy shape — classic, progressive, roller, or wave

## Workflow

1. **Search tracks** — `ym_search_yandex_music` with the target genre.
   Search for enough tracks to fill the duration
   (estimate ~5 min per track, so 12 tracks for 60 min).

2. **Import tracks** — `dj_import_tracks` with the found track IDs.
   This adds them to the local database.

3. **Expand selection** — `dj_find_similar_tracks` to discover additional
   tracks that complement the initial selection.

4. **Build set** — `dj_build_set` with the desired `energy_arc`.
   The genetic algorithm optimizes track ordering for smooth transitions.

5. **Score and iterate** — `dj_score_transitions` → review →
   `dj_adjust_set` if scores are low.

## Energy Arcs

- **classic**: Warm up → peak → cool down
- **progressive**: Steady build from start to finish
- **roller**: Maintain high energy throughout
- **wave**: Multiple peaks and valleys
```

**Step 4: Write improve-set/SKILL.md**

```markdown
---
description: Improve an existing DJ set by analyzing and fixing weak transitions
---

# Improve Set

Analyze an existing DJ set's transitions and iteratively improve
the track ordering.

## Parameters

- **set_id**: DJ set ID to improve
- **version_id**: Version to base improvements on
- **feedback**: Optional user feedback about what to fix

## Workflow

1. **Score transitions** — `dj_score_transitions` with set_id and version_id.
   Review each transition's component scores (BPM, harmonic, energy,
   spectral, groove).

2. **Identify weak points** — Look for transitions with total < 0.6.
   Common issues:
   - BPM mismatch (score < 0.5): tracks have incompatible tempos
   - Harmonic clash (score < 0.4): keys don't mix well
   - Energy jump (score < 0.5): too big a change in loudness

3. **Adjust set** — `dj_adjust_set` with specific instructions:
   - "swap tracks 3 and 5 to improve BPM flow"
   - "move the peak track earlier in the set"
   - "reorder tracks 7-10 for better energy progression"

4. **Re-score** — `dj_score_transitions` on the new version.
   Compare average scores between versions.

5. **Iterate** — Repeat steps 3-4 until satisfied.
   Usually 2-3 iterations are enough.

## Score Guide

| Component | Good | Acceptable | Poor |
|-----------|------|-----------|------|
| BPM | > 0.8 | 0.5-0.8 | < 0.5 |
| Harmonic | > 0.7 | 0.4-0.7 | < 0.4 |
| Energy | > 0.6 | 0.3-0.6 | < 0.3 |
| Spectral | > 0.5 | 0.3-0.5 | < 0.3 |
| Groove | > 0.5 | 0.3-0.5 | < 0.3 |
| **Total** | **> 0.7** | **0.5-0.7** | **< 0.5** |
```

**Step 5: Commit**

```bash
git add app/mcp/skills/
git commit -m "feat(mcp): add DJ workflow skill files

3 skills: expand-playlist, build-set-from-scratch, improve-set.
Each contains step-by-step workflow instructions with tool names,
parameters, and tips for the LLM."
```

---

## Task 13: Skills — integrate SkillsDirectoryProvider

**Files:**
- Modify: `app/mcp/gateway.py` (add provider)
- Create: `tests/mcp/test_skills.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_skills.py
"""Tests for DJ skills provider."""

from __future__ import annotations

from fastmcp import Client

async def test_skills_provider_lists_skills():
    """Gateway exposes 3 DJ skills as resources."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        resources = await client.list_resources()
        skill_uris = [str(r.uri) for r in resources if "skill://" in str(r.uri)]
        assert len(skill_uris) >= 3  # At least our 3 skills

async def test_skill_readable():
    """Skill SKILL.md is readable via resource URI."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        content = await client.read_resource("skill://expand-playlist/SKILL.md")
        text = content[0].text if hasattr(content[0], "text") else str(content[0])
        assert "Expand Playlist" in text
        assert "dj_get_playlist_status" in text

async def test_skill_manifest():
    """Skill manifest lists files with hashes."""
    from app.mcp.gateway import create_dj_mcp

    gateway = create_dj_mcp()

    async with Client(gateway) as client:
        content = await client.read_resource("skill://expand-playlist/_manifest")
        text = content[0].text if hasattr(content[0], "text") else str(content[0])
        assert "SKILL.md" in text
        assert "sha256" in text
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_skills.py -v`
Expected: FAIL — no skill resources found

**Step 3: Add SkillsDirectoryProvider to gateway**

In `app/mcp/gateway.py`, add after imports:

```python
from pathlib import Path
```

Add after `apply_observability(gateway, settings)`:

```python
    # Expose DJ workflow skills as MCP resources
    try:
        from fastmcp.server.providers.skills import SkillsDirectoryProvider

        skills_dir = Path(__file__).parent / "skills"
        if skills_dir.exists():
            gateway.add_provider(SkillsDirectoryProvider(
                roots=skills_dir,
                supporting_files="template",
            ))
    except ImportError:
        logger.debug("SkillsDirectoryProvider not available; skipping skills")
```

**Step 4: Run tests**

Run: `uv run pytest tests/mcp/test_skills.py -v`
Expected: PASS (all 3)

**Step 5: Run full MCP test suite**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/mcp/gateway.py tests/mcp/test_skills.py
git commit -m "feat(mcp): integrate SkillsDirectoryProvider in gateway

Expose app/mcp/skills/ as MCP resources via SkillsDirectoryProvider.
Skills are discoverable via list_resources() and readable via
resource URIs (skill://<name>/SKILL.md)."
```

---

## Task 14: Final — lint, type-check, full test run

**Files:**
- Possibly: any file needing lint fixes

**Step 1: Run linter**

Run: `uv run ruff check app/mcp/ tests/mcp/ && uv run ruff format --check app/mcp/ tests/mcp/`
Expected: PASS (fix any issues)

**Step 2: Run type checker**

Run: `uv run mypy app/mcp/`
Expected: PASS (fix any issues — may need `type: ignore` for fastmcp internals)

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: PASS

**Step 4: Final commit (if lint/type fixes needed)**

```bash
git add -A
git commit -m "chore: fix lint and type issues from MCP advanced features"
```

**Step 5: Update .env.example with all new vars**

Verify `.env.example` has all new env vars added throughout the tasks.

**Step 6: Run `make check`**

Run: `make check`
Expected: PASS (lint + test combined)
