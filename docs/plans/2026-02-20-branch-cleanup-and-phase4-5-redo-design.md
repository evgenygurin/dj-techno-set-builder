# Branch Cleanup & Phase 4–5 Redo Design

**Date:** 2026-02-20
**Status:** Approved and executed (Blocks 1–2), Phase 4–5 redo pending

## Problem Statement

MCP redesign work (Phases 0–5) was split across sessions with different agents.
Phases 1–3 were correctly implemented on `dev`, but Phase 4 and Phase 5 were
branched from `main` (commit `9b54e9c` — docs only) instead of `dev`.

This resulted in:
- **Phase 5 merged into `origin/main`** (PR #23) without Phases 1–4 foundation code
- **Phase 4** on a separate branch (`phase4-mcp-cleanup`) also based on `main`, not `dev`
- Both Phase 4 and Phase 5 code logically incompatible with Phase 1–3 code on `dev`

## Branch State Before Cleanup

```text
origin/main (5ed7f70)     = plan docs + Phase 5 merge (NO Phases 1-4)
dev (8bd904b)             = plan docs + Phase 1 + Phase 2 + Phase 3
phase4-mcp-cleanup        = plan docs + Phase 4 (based on main, NOT dev)
feat/phase5 (merged)      = plan docs + Phase 5 (based on main, NOT dev)
```

**File conflicts** between Phase 4/5 (based on main) and dev (Phase 1–3):
- Phase 4 ↔ dev: 7 overlapping files (`types_v2.py`, `server.py`, `sync_tools.py`, etc.)
- Phase 5 ↔ dev: 2 overlapping files (`server.py`, `sync_tools.py`)

## Cleanup Actions (Executed)

### Block 1: Revert Phase 5 on main
- Fetched `origin/main` (was at `5ed7f70`, merge of PR #23)
- Created revert commit `e71006c` using `git revert -m 1 5ed7f70`
- Pushed to `origin/main`
- **Result:** main is now functionally at `9b54e9c` state (plan docs only)

### Block 2: Close stale PRs and branches
- Closed PR #22 (Phase 4 → main) with explanation
- Deleted remote branch `phase4-mcp-cleanup`
- Remote branch `feat/phase5-mcp-platform-features` already deleted (was cleaned on merge)

## Current State After Cleanup

```text
main (e71006c)   = plan docs + Phase 5 merge + Phase 5 revert = effectively 9b54e9c
dev (8bd904b)    = plan docs + Phase 1 + Phase 2 + Phase 3
```

## Plan Forward

### Phase 4: Redo on dev (from scratch)
Phase 4 = cleanup of legacy tools, stubs, dead types. Must be re-implemented
on top of dev (which has Phase 1–3 code). Use existing plan docs as reference:
- `docs/plans/2026-02-19-mcp-redesign-phase4-plan.md`
- `docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan.md`
- `docs/plans/2026-02-19-mcp-tools-redesign-phase4-plan-review.md` (9 blockers)

**Key blockers from review to address:**
1. Sync module location ambiguity (Phase 3 rewrites, Phase 4 should clean old)
2. Test updates for new tool names
3. Export unification decision
4. Error handling (use project AppError, not ValueError)

### Phase 5: Redo on dev (from scratch)
Phase 5 = FastMCP v3 platform features. Must be re-implemented after Phase 4.
Use existing plan docs as reference:
- `docs/plans/2026-02-19-mcp-redesign-phase5-plan.md`
- `docs/plans/2026-02-19-mcp-platform-features-plan.md`
- `docs/plans/2026-02-19-mcp-platform-features-plan-review.md` (9 blockers)

**Key blockers from review to address:**
1. FastMCP API reality (rc2 vs plan assumptions)
2. Background tasks dependency (`docket`)
3. ResponseLimiting must preserve structured output
4. Elicitation must fail-closed on decline (not fail-open)
5. Tool names only stabilize after Phase 4

### Final merge
When Phase 5 is complete and tested:
- Create PR: dev → main
- Merge brings all Phase 1–5 code into main in correct order

## Document Inventory

Two parallel series exist (both valid, use together):

| Series | Purpose |
|--------|---------|
| `mcp-redesign-phase*` | High-level strategy, infrastructure focus |
| `mcp-tools-redesign-phase*` | Detailed code patterns, DJ namespace focus |
| `mcp-platform-features-*` | Phase 5 only, FastMCP v3 features |
| `*-review.md` | Critical reviews with blockers — MUST READ before implementing |

**Total blockers identified across all reviews:** ~40 items.
New Phase 4/5 plans should address all blockers from the corresponding review docs.

## Lessons Learned

1. **Always branch from dev** for sequential work — never from main mid-sequence
2. **Check branch base** before implementing — verify Phase N-1 code is present
3. **One session per phase** to avoid context loss between agents
4. **Review docs are valuable** — the 40 blockers they found would have caused bugs
