---
paths:
  - "app/mcp/**"
---

# MCP Server (FastMCP 3.0)

## Structure

```text
app/mcp/
├── __init__.py              # re-exports create_dj_mcp
├── gateway.py               # Gateway: mount YM + Workflows, add transforms
├── types_v2.py              # 11 Pydantic models for structured output
├── dependencies.py          # DI providers (FastMCP Depends, async session)
├── workflows/
│   ├── __init__.py          # re-exports create_workflow_mcp
│   ├── server.py            # Factory + visibility control
│   ├── import_tools.py      # download_tracks
│   ├── discovery_tools.py   # find_similar_tracks
│   ├── setbuilder_tools.py  # build_set, rebuild_set, score_transitions
│   ├── export_tools.py      # export_set_m3u, export_set_json, export_set_rekordbox
│   └── curation_tools.py    # classify_tracks, analyze_library_gaps, review_set
├── prompts/
│   └── workflows.py         # 3 recipe prompts (expand, build, improve)
├── resources/
│   └── status.py            # 3 resources (playlist, catalog, set)
└── yandex_music/
    ├── __init__.py           # re-exports create_yandex_music_mcp
    ├── server.py             # OpenAPI -> FastMCP factory with spec patching
    └── config.py             # RouteMap exclusions, camelCase->snake_case
```

## Gateway composition

`create_dj_mcp()` in `app/mcp/gateway.py`:
- Mounts **Yandex Music** sub-server at namespace `"ym"` (~30 tools from OpenAPI)
- Mounts **DJ Workflows** sub-server at namespace `"dj"` (12 hand-written tools)
- Adds `PromptsAsTools` + `ResourcesAsTools` transforms for tool-only MCP clients
- Total: ~46 tools (30 YM + 12 DJ + 4 transforms)

## DJ Workflow tools (namespace "dj")

| Tool | Tag | Read-only | Description |
|------|-----|-----------|-------------|
| `download_tracks` | download, yandex | No | Download MP3 files from Yandex Music to iCloud library |
| `find_similar_tracks` | discovery | No | LLM-assisted similar track search via `ctx.sample()` |
| `build_set` | setbuilder | No | Create DJ set + template-aware GA optimization |
| `rebuild_set` | setbuilder | No | Rebuild set with pinned/excluded constraints |
| `score_transitions` | setbuilder | Yes | Score all transitions in a set version |
| `export_set_m3u` | export | Yes | Export set as Extended M3U8 with VLC opts, DJ metadata |
| `export_set_json` | export | Yes | Export set as JSON transition guide with scoring |
| `export_set_rekordbox` | export | Yes | Export set as Rekordbox XML (DJ_PLAYLISTS) |
| `classify_tracks` | curation | Yes | Classify all tracks by 6 mood categories |
| `review_set` | curation, setbuilder | Yes | Review set: weak transitions, variety, suggestions |
| `analyze_library_gaps` | curation | Yes | Compare library vs template needs, find gaps |
| `activate_heavy_mode` | admin | No | Enable heavy analysis tools |

### Removed in Phase 4

- `get_playlist_status` / `get_track_details` — analysis stubs, replaced by REST API
- `import_playlist` / `import_tracks` — import stubs, superseded by `download_tracks`
- `search_by_criteria` — local filter, will return as CRUD search in Phase 2
- `sync_set_to_ym` / `sync_set_from_ym` / `sync_playlist` — sync stubs, deferred to Phase 3

## Yandex Music tools (namespace "ym")

Generated from OpenAPI spec (`data/yandex-music.yaml`) via `FastMCP.from_openapi()`. Includes search, tracks, albums, artists, playlists endpoints. Non-DJ endpoints excluded via `RouteMap` patterns (account, feed, rotor, queues, settings).

Tool names: camelCase operationIds converted to snake_case in `config.py`. Special case: `search` -> `search_yandex_music` to avoid collisions.

## MCP DI pattern

`app/mcp/dependencies.py` uses **FastMCP's `Depends()`** (from `fastmcp.dependencies`, NOT FastAPI's):

```python
from fastmcp.dependencies import Depends

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session

def get_track_service(session: AsyncSession = Depends(get_session)) -> TrackService:
    return TrackService(TrackRepository(session))
```

8 DI providers: `get_session`, `get_track_service`, `get_playlist_service`, `get_features_service`, `get_analysis_service`, `get_set_service`, `get_set_generation_service`, `get_transition_service`, `get_ym_client`.

Tool function signature pattern:
```python
async def build_set(
    playlist_id: int,           # visible to MCP client
    set_name: str,              # visible to MCP client
    ctx: Context,               # injected by FastMCP (hidden from client)
    set_svc: DjSetService = Depends(get_set_service),  # injected (hidden)
) -> SetBuildResult:            # structured output -> structuredContent in MCP
```

## Tool registration pattern

Each workflow module exports a `register_*_tools(mcp)` function called by `create_workflow_mcp()`:

```python
def register_curation_tools(mcp: FastMCP) -> None:
    @mcp.tool(annotations={"readOnlyHint": True}, tags={"curation"})
    async def classify_tracks(...) -> ClassifyResult:
        ...
```

## Visibility control

Heavy tools (tagged `"heavy"`) are hidden by default via `mcp.disable(tags={"heavy"})` in `server.py`. Clients call `activate_heavy_mode` to unlock via `ctx.enable_components(tags={"heavy"})`.

## Prompts (workflow recipes)

3 prompts guide multi-step workflows:
- `expand_playlist` — analyze -> find similar -> build set
- `build_set_from_scratch` — search YM -> import -> find similar -> build set
- `improve_set` — score transitions -> adjust -> re-score

Each returns `list[Message]` with step-by-step instructions referencing namespaced tool names (e.g. `dj_build_set`, `ym_search_yandex_music`).

## Resources

- `playlist://{playlist_id}/status` — track count
- `catalog://stats` — total tracks
- `set://{set_id}/summary` — version count

Resources use FastMCP DI (`Depends`) for service injection, same as tools.

## Structured output

All DJ tools return typed Pydantic models (11 types in `app/mcp/types_v2.py`):
`SetBuildResult`, `TransitionScoreResult`, `ExportResult`, `SimilarTracksResult`, `SearchStrategy`, `MoodDistribution`, `ClassifyResult`, `WeakTransition`, `SetReviewResult`, `GapDescription`, `LibraryGapResult`.

Return type annotation -> `structuredContent` in MCP protocol response.

## MCP mounting in FastAPI

```python
# app/main.py
mcp = create_dj_mcp()
mcp_app = mcp.http_app(path="/mcp")
app = FastAPI(lifespan=combine_lifespans(lifespan, mcp_app.lifespan))
app.mount("/mcp", mcp_app)
```

MCP endpoint: `POST /mcp/mcp` (StreamableHTTP). The double `/mcp` is because FastAPI mounts at `/mcp` and FastMCP internal path is also `/mcp`.

## Adding a new MCP tool

1. Create tool function in the appropriate `app/mcp/workflows/*_tools.py` module
2. Use `@mcp.tool(tags={"tag"}, annotations={"readOnlyHint": True})` for read-only tools
3. Add DI providers in `app/mcp/dependencies.py` if new services needed
4. Return a Pydantic model from `app/mcp/types_v2.py` (create new if needed)
5. Add tests in `tests/mcp/test_workflow_*.py` — verify registration, tags, annotations, gateway namespacing
6. `Context` parameter: always non-optional (`ctx: Context`), FastMCP injects it automatically

## MCP gotchas

- **B008 ruff rule**: `Depends()` in default args triggers B008. Solved with per-file-ignores in `pyproject.toml`:
  ```toml
  [tool.ruff.lint.per-file-ignores]
  "app/mcp/dependencies.py" = ["B008"]
  "app/mcp/workflows/*.py" = ["B008"]
  ```
- **`combine_lifespans()`**: Required to compose FastAPI + MCP ASGI lifespans. Without it, MCP task group won't initialize. Import from `fastmcp.utilities.lifespan`.
- **`ctx.sample()` fallback**: Not all MCP clients support sampling. Always wrap in `try/except (NotImplementedError, AttributeError, TypeError)`.
- **OpenAPI spec patching**: `_patch_spec()` in `yandex_music/server.py` fixes: integer response codes (YAML parses `200` as int), missing operationIds, and circular `$ref` chains (Genre.subGenres, Artist.popularTracks, Album.artists/volumes).
- **`Context` parameter**: Always non-optional (`ctx: Context`), never `ctx: Context = None`. FastMCP injects it automatically.
- **mypy + fastmcp**: `fastmcp` is in `ignore_missing_imports` since it lacks type stubs.
- **MCP tests — two layers**: (1) Metadata tests verify tool names/tags/annotations via `mcp.list_tools()`. (2) Client integration tests use `Client(server)` for in-memory tool invocation. Both use shared fixtures from `tests/mcp/conftest.py`.
- **Server in fixture, Client in test body**: Don't open `Client` in fixtures — create server in fixture, open `Client` context manager inside test functions.
- **DB-dependent tools need session mocking**: All remaining tools require database access. Use session fixtures for testing.

## Testing

Two-layer testing in `tests/mcp/` (see `rules/testing.md` for full details):

| Layer | What | How | DB needed |
|-------|------|-----|-----------|
| Metadata | Tool names, tags, annotations, namespacing | `mcp.list_tools()` on fixture | No |
| Client integration | Tool invocation, structured output, errors | `Client(server)` in-memory | Stubs: No, real tools: Yes |

Shared fixtures in `tests/mcp/conftest.py`: `workflow_mcp`, `gateway_mcp`, `ym_mcp`.

```python
# Client integration test pattern
async def test_build_set(workflow_mcp: FastMCP):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("build_set", {...})
        assert not result.is_error
```

## Dev workflow

Four ways to interact with MCP during development:

| Command | Port | Purpose |
|---------|------|---------|
| `make mcp-dev` | 9100 | HTTP dev-server with hot-reload. Claude Code connects via `.mcp.json` |
| `make mcp-inspect` | 6274 | Visual tool debugger in browser |
| `make mcp-list` | — | List all registered tools |
| `make mcp-call TOOL=... ARGS='{...}'` | — | Call a specific tool from CLI |
| `make run` | 8000 | FastAPI + MCP together (REST at `/api/v1`, MCP at `/mcp/mcp`) |

Installation into MCP clients:

| Command | Target |
|---------|--------|
| `make mcp-install-desktop` | Claude Desktop (`claude_desktop_config.json`) |
| `make mcp-install-code` | Claude Code global (`~/.claude.json`) |

**Hot-reload workflow:**
1. Run `make mcp-dev` in a terminal (keeps running)
2. Start Claude Code session — `.mcp.json` auto-connects to `:9100`
3. Edit any file in `app/mcp/` — server restarts automatically
4. Claude Code reconnects — no session restart needed

**Config files:**
- `fastmcp.json` — central FastMCP config (source, env, deployment). Auto-detected by `fastmcp run`
- `.mcp.json` — Claude Code project-level config (HTTP URL for dev)

**CLI quick reference:**
```bash
make mcp-list                                                    # ~46 tools
make mcp-call TOOL=dj_build_set ARGS='{"playlist_id": 1, "set_name": "test"}' # call tool
make mcp-dev                                                     # HTTP :9100 + reload
make mcp-inspect                                                 # Inspector :6274
```
