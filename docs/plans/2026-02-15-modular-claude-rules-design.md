# Modular CLAUDE.md Rules Design

**Goal:** Restructure the monolithic CLAUDE.md (307 lines) into a minimal root file (~60 lines) plus 5 focused `.claude/rules/*.md` files with path-specific loading.

**Approach:** Split by architectural layers. Each rules file uses YAML frontmatter `paths:` to load only when Claude works with files in that layer.

## File Structure

```text
CLAUDE.md                          # ~60 lines: commands + architecture + lint
.claude/
└── rules/
    ├── database.md                # Models, conventions, SQLite compat
    ├── mcp.md                     # Gateway, tools, DI, visibility, gotchas
    ├── audio.md                   # Pipeline, modules, transition scoring
    ├── testing.md                 # Fixtures, patterns, critical imports
    └── api.md                     # Adding domains, key abstractions, routing
```

## Content Mapping

### CLAUDE.md (root, unconditional, ~60 lines)

Keeps only globally-needed sections:
- **Commands** — build, test, lint, MCP CLI, Makefile shortcuts (lines 7-59 current)
- **Architecture** — diagram (REST + MCP), request flow, DI pattern, app factory, versioned routes (lines 61-88 current)
- **Lint & Type Rules** — ruff, mypy, pytest-asyncio config (lines 303-307 current)

### .claude/rules/mcp.md (~130 lines)

```yaml
paths:
  - "app/mcp/**"
```

Full content of current "MCP Server (FastMCP 3.0)" section:
- Structure (file tree)
- Gateway composition (YM + Workflows, ~46 tools)
- DJ Workflow tools table (12 tools with tags, read-only status)
- Yandex Music tools (OpenAPI-generated)
- MCP DI pattern (FastMCP Depends example)
- Visibility control
- Prompts (3 workflow recipes)
- Resources (3 URI templates)
- Structured output (10 Pydantic models)
- MCP mounting in FastAPI
- Adding a new MCP tool (5 steps)
- MCP gotchas (B008, combine_lifespans, ctx.sample, Context, mypy)

### .claude/rules/database.md (~35 lines)

```yaml
paths:
  - "app/models/**"
  - "app/repositories/**"
  - "migrations/**"
```

Content from current "Models & Database" section:
- DDL source of truth (schema_v6.sql)
- Dev DB (SQLite) / Prod DB (PostgreSQL)
- 30+ ORM models
- Model conventions (Base, TimestampMixin, CreatedAtMixin, CHECK constraints, enums, `__all__` sorting)
- SQLite compatibility rules (JSON vs JSONB, func.now(), pgvector, int4range)

### .claude/rules/audio.md (~30 lines)

```yaml
paths:
  - "app/utils/audio/**"
  - "app/services/transition_scoring.py"
```

Content from current "Audio analysis utils" + "Transition scoring" sections:
- 16 pure-function modules with frozen dataclasses
- Pipeline pattern (error wrapping)
- Individual module listing
- TransitionScoringService 5-component formula with weights

### .claude/rules/testing.md (~25 lines)

```yaml
paths:
  - "tests/**"
```

Content from current "Test fixtures" section:
- 3 async fixtures (engine, session, client)
- Critical `from app.models import Base` import requirement
- Audio utils test location + synthetic fixtures
- MCP test location + patterns

### .claude/rules/api.md (~40 lines)

```yaml
paths:
  - "app/routers/**"
  - "app/schemas/**"
  - "app/services/**"
```

Content from current "Adding a new domain" + "Key abstractions" + "Multi-repo service" sections:
- Step-by-step: adding a new domain (5 steps with file paths)
- BaseRepository, BaseSchema, BaseService, AppError descriptions
- Multi-repo service pattern (TrackAnalysisService)

## Trade-offs

**Pros:**
- Context economy: MCP rules (~130 lines) only load when editing `app/mcp/**`
- Each file covers one architectural layer — easy to find and maintain
- Path-specific loading prevents irrelevant rules from consuming context window
- 5 files — manageable count, maps 1:1 to architecture layers

**Cons:**
- Cross-cutting concerns (e.g. ruff B008 for MCP) must live in the right rules file
- Path patterns must be maintained as project structure evolves
- First-time users see only ~60 lines in CLAUDE.md — need to know about rules/

## Implementation

1. Create `.claude/rules/` directory
2. Write 5 rules files with content extracted from CLAUDE.md
3. Trim CLAUDE.md to ~60 lines (commands + architecture + lint)
4. Verify all content preserved (no information lost)
5. Run tests to confirm nothing broken
