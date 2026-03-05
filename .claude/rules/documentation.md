# Documentation Meta-Rules

Rules for maintaining the `.claude/rules/` documentation system.

## File hierarchy (load order)

| Level | File | Loaded | Purpose |
|-------|------|--------|---------|
| 1 | `CLAUDE.md` (root) | Always at launch | Commands, architecture overview, lint rules |
| 2 | `.claude/rules/*.md` | Always at launch | Modular topic-specific rules |
| 3 | `.claude/CLAUDE.md` | Always at launch | Project-level instructions (if exists) |
| 4 | `CLAUDE.local.md` | Always at launch | Personal local overrides (gitignored) |
| 5 | Auto memory (`MEMORY.md`) | First 200 lines | Claude's own notes and learnings |

More specific rules take precedence over broader ones.

## When to create a new rules file

- Topic covers a distinct architectural layer (routers, models, utils, etc.)
- Content exceeds 20 lines and is self-contained
- Rules apply to specific file paths (use `paths:` frontmatter)

## When NOT to create a new file

- Content is universal (commands, lint config) — keep in root `CLAUDE.md`
- Content is personal/local — use `CLAUDE.local.md`
- Content is a one-off learning — use auto memory (`MEMORY.md`)

## Path-specific rules (frontmatter)

Use YAML `paths:` when rules apply only to certain files:

```yaml
---
paths:
  - "app/models/**"
  - "app/repositories/**"
---
```

Glob patterns: `**/*.py` (recursive), `src/**/*` (all under dir), `*.md` (root only).

Rules without `paths:` load unconditionally for all files.

## File naming

- Lowercase, hyphen-separated: `api.md`, `database.md`, `audio.md`
- Name reflects the architectural domain, not the action
- Subdirectories allowed for grouping: `rules/frontend/`, `rules/backend/`

## Content structure

Every rules file should follow:

1. **YAML frontmatter** (if path-specific) with `paths:` field
2. **H1 title** — topic name
3. **Overview** — 2-3 lines max
4. **Sections** with tables, code blocks, and patterns
5. **Gotchas** section at the end (if applicable)

## Content principles

- **Concise**: one line per concept where possible, tables over prose
- **Actionable**: describe patterns to follow, not theory
- **DRY**: don't repeat info across files; reference other files if needed
- **Current**: update rules when code changes (new routers, new models, etc.)
- **No obvious info**: skip things any Python developer would know

## What belongs where

| Content type | Location |
|-------------|----------|
| Build/test/lint commands | `CLAUDE.md` (root) |
| Architecture overview diagram | `CLAUDE.md` (root) |
| Lint/mypy config rules | `CLAUDE.md` (root) |
| Router/schema/service patterns | `.claude/rules/api.md` |
| Model/repository/migration patterns | `.claude/rules/database.md` |
| Audio utils/scoring/set generation | `.claude/rules/audio.md` |
| Test fixtures/conventions/organization | `.claude/rules/testing.md` |
| MCP server structure/tools/DI | `.claude/rules/mcp.md` |
| In-Memoria tool usage/reliability | `.claude/rules/in-memoria.md` |
| These meta-rules | `.claude/rules/documentation.md` |
| Personal preferences | `CLAUDE.local.md` |
| Session learnings, gotchas | Auto memory (`MEMORY.md`) |

## Updating rules

When modifying the codebase:

1. **New domain added** (router + schema + service + repo): update `api.md` and `database.md`
2. **New model/enum**: update `database.md` model files table and enums table
3. **New MCP tool**: update `mcp.md` tool table
4. **New audio module**: update `audio.md` module table
5. **New test directory**: update `testing.md` organization tree
6. **Changed lint/mypy config**: update root `CLAUDE.md`
7. **In-Memoria patched/updated**: update `in-memoria.md` tool reliability table
8. **Any meaningful change**: update `CHANGELOG.md` (Unreleased section) + relevant docs/rules

## Session Handoff Protocol

Когда работа не может быть завершена в текущей сессии — выполни ВСЕ шаги перед завершением:

### Обязательный чеклист

| Шаг | Действие | Обязательность |
|-----|----------|----------------|
| 1 | Завершить все изменения в коде, docs, rules, MEMORY.md | Всегда |
| 2 | `CHANGELOG.md` → `[Unreleased]` | Всегда |
| 3 | Commit с conventional commit message | Всегда |
| 4 | Push на remote | Всегда |
| 5 | PR или комментарий в issue (по обстоятельствам) | Если есть Linear issue |
| 6 | Явно сообщить пользователю: "Нужна новая сессия" | Всегда |
| 7 | Написать полный промпт для новой сессии | Всегда |

### Структура промпта для новой сессии

```text
## Контекст: <краткое описание>

### Предыстория
- Ветка, коммиты, что сделано
- Что именно было исправлено/изменено и почему

### Задачи (по порядку)

#### 1. Верификация <что проверить>
- Конкретная команда / MCP вызов
- Ожидаемый результат
- Что делать если не работает (fallback)

#### 2. Основная задача
- Пошаговые инструкции
- Конкретные SQL/команды/файлы

#### 3. (Опционально) Дополнительные задачи
```

### Принципы промпта

- **Самодостаточный**: новая сессия не должна искать контекст в истории
- **Верификация первой**: всегда начинать с проверки того, что предыдущий фикс работает
- **Конкретный**: точные команды, SQL, ожидаемые значения — не абстракции
- **Fallback**: что делать если основной путь не работает
- **Не предполагать состояние MCP**: после изменения `.mcp.json` MCP может быть кэширован

## Mandatory post-change checklist

After EVERY feature/fix/config change, BEFORE committing:

1. Update `CHANGELOG.md` → `[Unreleased]` section (Added/Changed/Fixed/Removed)
2. Update relevant `.claude/rules/*.md` if architecture/patterns changed
3. Update `CLAUDE.md` if new commands, MCP servers, or architecture changes
4. Use `revise-claude-md` skill when in doubt about what to update
5. Update `MEMORY.md` if gotcha/pattern discovered that helps future sessions
6. If work continues in new session — follow Session Handoff Protocol (above)

## Keeping CLAUDE.md minimal

Root `CLAUDE.md` should stay under 80 lines. It contains:

- Commands (install, test, lint, run, migrate, MCP CLI)
- Makefile shortcuts
- Architecture diagram (text art, ~15 lines)
- DI pattern (1 line)
- App factory (1 line)
- Versioned routes (3 lines)
- Lint & type rules (3 lines)

Everything else goes in `.claude/rules/` files.

## Project-specific conventions

- Tables preferred over bullet lists for structured data
- Code blocks with language hints (`python`, `bash`, `toml`, `text`)
- File paths always relative to project root
- Reference specific files: `app/errors.py`, not "the errors module"
- Include both the pattern and a concrete example
- Mark gotchas with bold **Gotcha** or a dedicated section
