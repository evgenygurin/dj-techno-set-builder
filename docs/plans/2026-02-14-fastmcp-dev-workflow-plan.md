# FastMCP Dev Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up FastMCP dev workflow with HTTP hot-reload, MCP Inspector, CLI helpers, and one-command installation for Claude Code/Desktop.

**Architecture:** `fastmcp.json` as central config, HTTP transport (:9100) with `--reload` for dev, stdio via `fastmcp install` for prod. `.mcp.json` connects Claude Code to local dev server.

**Tech Stack:** FastMCP 3.0.0rc2, uv, Make

---

### Task 1: Create `fastmcp.json`

**Files:**
- Create: `fastmcp.json`

**Step 1: Create the config file**

```json
{
  "$schema": "https://gofastmcp.com/public/schemas/fastmcp.json/v1.json",
  "source": {
    "type": "filesystem",
    "path": "app/mcp/gateway.py",
    "entrypoint": "create_dj_mcp"
  },
  "environment": {
    "type": "uv",
    "python": "3.12",
    "editable": ["."]
  },
  "deployment": {
    "transport": "stdio",
    "log_level": "INFO",
    "env": {
      "YANDEX_MUSIC_TOKEN": "${YANDEX_MUSIC_TOKEN}",
      "YANDEX_MUSIC_USER_ID": "${YANDEX_MUSIC_USER_ID}",
      "YANDEX_MUSIC_BASE_URL": "${YANDEX_MUSIC_BASE_URL}"
    }
  }
}
```

**Step 2: Verify FastMCP detects the config**

Run: `uv run fastmcp inspect --skip-env`
Expected: Shows 46 tools (gateway detected from `fastmcp.json`)

**Step 3: Verify `fastmcp run` works with auto-detected config**

Run: `uv run fastmcp list --skip-env | head -5`
Expected: Tool names starting with `ym_` and `dj_`

---

### Task 2: Create `.mcp.json` for Claude Code (HTTP dev)

**Files:**
- Create: `.mcp.json`

**Step 1: Create project-level Claude Code MCP config**

```json
{
  "mcpServers": {
    "dj-techno": {
      "type": "url",
      "url": "http://localhost:9100/mcp/"
    }
  }
}
```

This connects Claude Code to the local HTTP dev server (`make mcp-dev`).

**Step 2: Verify `.mcp.json` is NOT in `.gitignore`**

Run: `grep -c '.mcp.json' .gitignore`
Expected: 0 (not ignored — this is a project-level config for team)

---

### Task 3: Add MCP targets to Makefile

**Files:**
- Modify: `Makefile` — add variables, .PHONY, help section, and 6 targets

**Step 1: Add MCP variables after existing variables block (line 8)**

After `WORKERS  ?= 4` add:

```makefile
MCP_PORT ?= 9100
MCP_SPEC := app/mcp/gateway.py:create_dj_mcp
```

**Step 2: Add MCP to .PHONY list (line 16)**

Append to the `.PHONY` declaration:

```makefile
        mcp-dev mcp-inspect mcp-list mcp-call mcp-install-desktop mcp-install-code
```

**Step 3: Add MCP help section before "CI / All" section**

Insert before line 237 (`# CI / All`):

```makefile
# ═════════════════════════════════════════════════════════════════════════════
# MCP Server
# ═════════════════════════════════════════════════════════════════════════════

mcp-dev:
	$(UV) run fastmcp run $(MCP_SPEC) --transport http --host 127.0.0.1 --port $(MCP_PORT) --reload --reload-dir app/mcp --skip-env

mcp-inspect:
	$(UV) run fastmcp dev inspector $(MCP_SPEC) --ui-port 6274 --reload --reload-dir app/mcp

mcp-list:
	$(UV) run fastmcp list $(MCP_SPEC) --skip-env

mcp-call:
ifndef TOOL
	$(error Укажи инструмент: make mcp-call TOOL=dj_get_track_details ARGS='track_id=45')
endif
	$(UV) run fastmcp call $(MCP_SPEC) $(TOOL) $(ARGS) --skip-env

mcp-install-desktop:
	$(UV) run fastmcp install claude-desktop $(MCP_SPEC) --name dj-techno --env-file .env --with-editable .

mcp-install-code:
	$(UV) run fastmcp install claude-code $(MCP_SPEC) --name dj-techno --env-file .env --with-editable .
```

**Step 4: Add MCP help entries**

Insert in the `help` target between "Docker" and "CI / All" sections:

```makefile
	@echo "  MCP Server"
	@echo "  ─────────────────────────────────────"
	@echo "  mcp-dev        HTTP dev-сервер с hot-reload (порт $(MCP_PORT))"
	@echo "  mcp-inspect    MCP Inspector UI (порт 6274)"
	@echo "  mcp-list       Список всех MCP-инструментов"
	@echo "  mcp-call TOOL= Вызов инструмента (make mcp-call TOOL=dj_get_track_details ARGS='track_id=45')"
	@echo "  mcp-install-desktop  Установить в Claude Desktop (stdio)"
	@echo "  mcp-install-code     Установить в Claude Code глобально (stdio)"
	@echo ""
```

**Step 5: Verify `make help` shows new targets**

Run: `make help 2>&1 | grep -A8 "MCP Server"`
Expected: 6 MCP targets listed

**Step 6: Verify `make mcp-list` works**

Run: `make mcp-list 2>&1 | head -10`
Expected: Tool list output

---

### Task 4: Update `.claude/rules/mcp.md` dev workflow section

**Files:**
- Modify: `.claude/rules/mcp.md` — replace CLI usage section at the end

**Step 1: Replace the "CLI usage" section (lines 167-181)**

Replace with:

```markdown
## Dev workflow

Four ways to interact with MCP during development:

| Command | Port | Purpose |
|---------|------|---------|
| `make mcp-dev` | 9100 | HTTP dev-server with hot-reload. Claude Code connects via `.mcp.json` |
| `make mcp-inspect` | 6274 | Visual tool debugger in browser |
| `make mcp-list` | — | List all registered tools |
| `make mcp-call TOOL=... ARGS='...'` | — | Call a specific tool from CLI |
| `make run` | 8000 | FastAPI + MCP together (REST at `/api/v1`, MCP at `/mcp/mcp`) |

Installation into MCP clients:

| Command | Target |
|---------|--------|
| `make mcp-install-desktop` | Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`) |
| `make mcp-install-code` | Claude Code global (`~/.claude.json`) |

**Hot-reload workflow:**
1. Run `make mcp-dev` in a terminal (keeps running)
2. Start Claude Code session — `.mcp.json` auto-connects to `:9100`
3. Edit any file in `app/mcp/` — server restarts automatically
4. Claude Code reconnects — no session restart needed

**Config files:**
- `fastmcp.json` — central FastMCP config (source, env, deployment)
- `.mcp.json` — Claude Code project-level config (HTTP URL for dev)
```

---

### Task 5: Smoke test the full workflow

**Step 1: Start HTTP dev server**

Run: `make mcp-dev` (in background, verify it starts)
Expected: FastMCP banner with "Listening on http://127.0.0.1:9100"

**Step 2: Test tool call against HTTP server**

Run: `uv run fastmcp call http://localhost:9100/mcp/ dj_get_track_details track_id=45 --transport http`
Expected: Track details for track 45

**Step 3: Stop the dev server**

Kill the background process.

---

### Task 6: Commit

**Step 1: Stage and commit all changes**

```bash
git add fastmcp.json .mcp.json Makefile .claude/rules/mcp.md
git commit -m "feat: add FastMCP dev workflow with hot-reload

- fastmcp.json: central config (source, env, deployment)
- .mcp.json: Claude Code project-level HTTP URL for dev
- Makefile: 6 new MCP targets (mcp-dev, mcp-inspect, mcp-list,
  mcp-call, mcp-install-desktop, mcp-install-code)
- .claude/rules/mcp.md: updated dev workflow documentation

Hot-reload workflow: make mcp-dev → edit app/mcp/ → auto-restart
→ Claude Code reconnects without session restart."
```
