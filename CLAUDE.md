# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

// Всегда думай по-русски и отвечай по-русски, если только явно не просят другое.

Detailed rules for each layer are in `.claude/rules/` (auto-loaded):
- `api.md` — routers, schemas, services, error handling
- `database.md` — models, repositories, migrations, SQLite compat
- `audio.md` — audio utils, transition scoring, set generation
- `testing.md` — fixtures, test organization, conventions
- `mcp.md` — FastMCP server, tools, DI, gateway
- `in-memoria.md` — codebase intelligence tools (session start, when to use, reliability)
- `documentation.md` — meta-rules for maintaining this documentation system

Workflow skills in `.claude/skills/` (read when working on that domain):
- `dj-set-workflow.md` — декларативный гайд: build → score → deliver → YM sync
- `mcp-tool-dev.md` — разработка MCP-инструментов: DI, staged pattern, тесты, чеклист
- `audio-analysis.md` — аудио пайплайн, scoring, cheat_sheet, iCloud стабы, M3U8

## Workflow

- **Linear**: branches and PR titles must start with the Linear issue ID (e.g. `BPM-123: ...`). See `docs/linear.md`.
- **Session handoff**: при передаче работы — commit, push, prompt для новой сессии. Протокол в `.claude/rules/documentation.md`.
- **`.mcp.json`**: `${VAR}` в `args` и `env` блоке НЕ раскрывается в VSCode extension — sourсить `.env` из `sh -c`. После правки — перезапуск сессии.

## Commands

```bash
fd
rg
ast-grep
jq
yq
```

```bash
uv sync --all-extras                    # Install all deps (audio + ml)
uv sync --extra audio                   # Audio deps only (no ML/torch)
uv run pytest -v                        # Run all tests
uv run pytest tests/test_tracks.py -v   # Single test file
uv run ruff check && uv run ruff format --check  # Lint
uv run mypy app/                        # Type-check
uv run uvicorn app.main:app --reload    # Dev server (REST + MCP at /mcp/mcp)
uv run alembic upgrade head             # Apply migrations
```

### Makefile shortcuts

```bash
make check           # lint + test (full CI check)
make lint            # ruff check + format check + mypy
make test            # pytest
make test-v          # pytest -v
make test-k MATCH=x  # pytest -k x
make coverage        # pytest-cov (html + terminal)
make ruff-fix        # auto-fix + format
make run             # uvicorn --reload (PORT=8000)
make mcp-dev         # HTTP dev-сервер с hot-reload (PORT=9100)
make mcp-inspect     # MCP Inspector UI (порт 6274)
make mcp-list        # Список всех MCP-инструментов
make mcp-call TOOL=x ARGS='{...}'  # Вызов инструмента
make mcp-install-desktop  # Установить в Claude Desktop (stdio)
make mcp-install-code     # Установить в Claude Code (stdio)
```

## Architecture

```text
Router → Service → Repository → AsyncSession → DB
  ↕         ↕          ↕
Schemas   Errors     Models

MCP Gateway (FastMCP 3.0)
  ├── Yandex Music (namespace "ym") — ~30 OpenAPI-generated tools
  └── DJ Workflows (namespace "dj") — 20 hand-written tools

External MCP servers (.mcp.json):
  ├── dj-techno (HTTP :9100) — project FastMCP gateway
  ├── sqlite-db (stdio, sh -c npx) — direct SQL access to dev.db via $DJ_DB_PATH
  └── in-memoria (stdio, sh) — codebase intelligence (13 tools)
```

- **DI**: `DbSession = Annotated[AsyncSession, Depends(get_session)]` in `app/dependencies.py`
- **App factory**: `create_app()` in `app/main.py` — lifespan manages DB + MCP
- **Routes**: `/health` (unversioned), `/api/v1/...` (13 domain routers), `/mcp/mcp` (MCP)

## Plugins & Settings

- **codegen-bridge** — делегирование задач в Codegen облачные агенты (`github:evgenygurin/codegen-bridge`)

| File | Scope | Git | Purpose |
|------|-------|-----|---------|
| `.claude/settings.json` | Project (team) | Yes | Marketplaces, plugins |
| `.claude/settings.local.json` | Personal | No | Env vars (`DJ_DB_PATH`), outputStyle, permissions |
| `.mcp.json` | Project (team) | Yes | MCP servers (dj-techno, sqlite-db, in-memoria) |

## Official Documentation (ОБЯЗАТЕЛЬНО к изучению)

**СТРОГОЕ ТРЕБОВАНИЕ**: Перед работой с любой подсистемой Claude Code — ИЗУЧИ соответствующий раздел
официальной документации. Используй скилл `working-with-claude-code` для доступа к offline-копиям.

| Тема | URL | Когда изучать |
|------|-----|---------------|
| Settings & Config | https://docs.anthropic.com/en/docs/claude-code/settings | Перед правкой settings.json, env, permissions |
| MCP Servers | https://docs.anthropic.com/en/docs/claude-code/mcp | Перед правкой .mcp.json, добавлением MCP |
| Hooks | https://docs.anthropic.com/en/docs/claude-code/hooks | Перед созданием/правкой hooks |
| Hooks Guide | https://docs.anthropic.com/en/docs/claude-code/hooks-guide | Примеры и best practices для hooks |
| Plugins | https://docs.anthropic.com/en/docs/claude-code/plugins | Перед работой с плагинами |
| Plugins Reference | https://docs.anthropic.com/en/docs/claude-code/plugins-reference | API, схемы, манифесты плагинов |
| Skills | https://docs.anthropic.com/en/docs/claude-code/skills | Перед созданием/правкой .claude/skills/ |
| Memory (CLAUDE.md) | https://docs.anthropic.com/en/docs/claude-code/memory | Перед правкой CLAUDE.md, rules/, imports |
| Sub-agents | https://docs.anthropic.com/en/docs/claude-code/sub-agents | Перед использованием Agent tool |
| CLI Reference | https://docs.anthropic.com/en/docs/claude-code/cli-reference | Команды claude CLI |
| Output Styles | https://docs.anthropic.com/en/docs/claude-code/output-styles | Перед настройкой outputStyle |
| Troubleshooting | https://docs.anthropic.com/en/docs/claude-code/troubleshooting | При проблемах с Claude Code |

## Lint & Type Rules

- **ruff**: Python 3.12, line-length 99, rules: E/F/W/I/N/UP/B/SIM/RUF. `A003` ignored. B008 per-file ignore for MCP.
- **mypy**: strict + `pydantic.mypy` plugin. `ignore_missing_imports`: fastmcp, alembic, essentia, soundfile, scipy, demucs, torch, torchaudio.
- **pytest-asyncio**: `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed.
