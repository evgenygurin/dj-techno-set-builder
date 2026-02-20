# FastMCP Dev Workflow Design

**Date:** 2026-02-14
**Status:** Approved
**Problem:** Changing MCP tool code requires restarting Claude Code/Desktop sessions, killing dev velocity.

## Decision

**Approach A: HTTP dev-server + stdio prod**

- Dev: `fastmcp run --transport http --port 9100 --reload` — clients reconnect automatically
- Prod: `fastmcp install claude-desktop/claude-code` — stdio transport
- Config: `fastmcp.json` as single source of truth

## Architecture

```text
┌─────────────────────────────────────────────────┐
│  make mcp-dev (HTTP :9100 + --reload)           │
│  fastmcp run --transport http --reload          │
│  create_dj_mcp() → Gateway                     │
│    ├── YM (ns "ym") — ~30 tools                │
│    └── DJ (ns "dj") — 12 tools                 │
│                                                 │
│  Claude Code (.mcp.json) ──→ http://...:9100   │
│  Claude Desktop (stdio)  ──→ fastmcp run       │
│  Inspector (:6274)       ──→ fastmcp dev       │
│  CLI                     ──→ fastmcp call      │
└─────────────────────────────────────────────────┘
```

## New Files

### `fastmcp.json` — central FastMCP config

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

Default transport is stdio (for `fastmcp install`). Dev transport overridden via CLI flags.

### `.mcp.json` — Claude Code project-level config (HTTP dev)

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

Requires `make mcp-dev` running. Checked into git for team use.

## Modified Files

### `Makefile` — 6 new MCP targets

| Target | Command | Purpose |
|--------|---------|---------|
| `mcp-dev` | `fastmcp run --transport http --port 9100 --reload --reload-dir app/mcp` | HTTP dev server with hot-reload |
| `mcp-inspect` | `fastmcp dev inspector --ui-port 6274 --reload --reload-dir app/mcp` | Visual tool debugger |
| `mcp-list` | `fastmcp list --skip-env` | List all tools |
| `mcp-call` | `fastmcp call --skip-env $(TOOL) $(ARGS)` | Call a specific tool |
| `mcp-install-desktop` | `fastmcp install claude-desktop ... --env-file .env` | Install in Claude Desktop |
| `mcp-install-code` | `fastmcp install claude-code ... --env-file .env` | Install in Claude Code globally |

### `.claude/rules/mcp.md` — updated dev workflow section

Add documentation for new Makefile targets and dev workflow.

## What Does NOT Change

- `app/mcp/gateway.py` — no modifications
- `app/main.py` — FastAPI mount stays
- Existing tests — no modifications
- `claude_desktop_config.json` — updated only via `make mcp-install-desktop`

## Out of Scope

- Integration tests with `Client(transport=mcp)` — separate ticket
- Production HTTP deployment / authentication
- Docker MCP configuration
