---
paths:
  - "app/mcp/**"
---

# MCP Server (FastMCP 3.0)

> **Official docs**: https://docs.anthropic.com/en/docs/claude-code/mcp — ИЗУЧИ перед правкой `.mcp.json` или добавлением MCP серверов.

## Structure

```text
app/mcp/
├── __init__.py              # re-exports create_dj_mcp
├── gateway.py               # Gateway: mount YM + DJ Tools, add transforms
├── types.py                 # 10 Pydantic models for structured output
├── dependencies.py          # DI providers (FastMCP Depends, async session)
├── tools/
│   ├── __init__.py            # re-exports create_workflow_mcp
│   ├── server.py              # Factory + visibility control
│   ├── compute.py             # compute_audio_features (heavy)
│   ├── curation.py            # classify_tracks, review_set, analyze_library_gaps
│   ├── discovery.py           # find_similar_tracks, search_by_criteria
│   ├── download.py            # download_tracks
│   ├── export.py              # export_set_rekordbox
│   ├── features.py            # get_track_features, get_features_summary
│   ├── playlist.py            # get_playlist, list_playlists, create/update/delete
│   ├── search.py              # search_tracks, filter_tracks
│   ├── set.py                 # get_set, list_sets, create/update/delete + get_set_tracks, list_set_versions, get_set_cheat_sheet
│   ├── setbuilder.py          # build_set, rebuild_set, score_transitions
│   ├── sync.py                # sync_set_to_ym, sync_set_from_ym, sync_playlist, ...
│   ├── track.py               # get_track, list_tracks, create/update/archive
│   └── unified_export.py      # export_set (m3u/json/cheat_sheet)
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
- Mounts **DJ Tools** sub-server at namespace `"dj"` (23 hand-written tools)
- Adds `PromptsAsTools` + `ResourcesAsTools` transforms for tool-only MCP clients
- Total: ~57 tools (30 YM + 23 DJ + 4 transforms)

## DJ Workflow tools (namespace "dj")

| Tool | Tag | Read-only | Description |
|------|-----|-----------|-------------|
| `get_playlist_status` | analysis | Yes | Playlist stats: tracks, BPM range, keys, energy, duration |
| `get_track_details` | analysis | Yes | Track metadata + audio features (BPM, key, energy) |
| `import_playlist` | import | No | Import from external source (stub), supports `download_files` param |
| `import_tracks` | import | No | Import tracks by YM IDs (stub) |
| `download_tracks` | download, yandex | No | Download MP3 files from Yandex Music to iCloud library |
| `find_similar_tracks` | discovery | No | LLM-assisted similar track search via `ctx.sample()` |
| `search_by_criteria` | discovery | Yes | Filter local tracks by BPM/key/energy ranges |
| `build_set` | setbuilder | No | Create DJ set + template-aware GA optimization |
| `rebuild_set` | setbuilder | No | Rebuild set with pinned/excluded constraints |
| `score_transitions` | setbuilder | Yes | Score all transitions with from_bpm/to_bpm/key/camelot_distance |
| `get_set_tracks` | crud, set | Yes | All tracks of a version with BPM/key/LUFS/pinned in one call |
| `list_set_versions` | crud, set | Yes | Version history with track_count and score |
| `get_set_cheat_sheet` | set, setbuilder | Yes | Full set view: tracks + transitions + summary + text |
| `deliver_set` | setbuilder | No | Score → write M3U8/JSON/cheat_sheet.txt → optional YM playlist (3 visible stages) |
| `export_set_m3u` | setbuilder | Yes | Export set as Extended M3U8 with VLC opts, DJ metadata |
| `export_set_json` | setbuilder | Yes | Export set as JSON transition guide with scoring |
| `sync_set_to_ym` | sync, yandex | No | Push DJ set to YM as playlist (stub) |
| `sync_set_from_ym` | sync, yandex | No | Read likes/dislikes from YM, update pinned/excluded (stub) |
| `sync_playlist` | sync, yandex | No | Bidirectional sync between YM and local playlist (stub) |
| `classify_tracks` | curation | Yes | Classify all tracks by 6 mood categories |
| `review_set` | curation, setbuilder | Yes | Review set: weak transitions, variety, suggestions |
| `analyze_library_gaps` | curation | Yes | Compare library vs template needs, find gaps |
| `activate_heavy_mode` | admin | No | Enable heavy analysis tools |

## Yandex Music tools (namespace "ym")

Generated from OpenAPI spec (`data/yandex-music.yaml`) via `FastMCP.from_openapi()`. Includes search, tracks, albums, artists, playlists endpoints. Non-DJ endpoints excluded via `RouteMap` patterns (account, feed, rotor, queues, settings).

**Excluded broken endpoints** (in `config.py` `EXCLUDE_ROUTE_MAPS`):
- `brief-info` — HTTP 403 Yandex Antirobot. Use `search_yandex_music(type=artist)` instead.
- `lyrics` — HTTP 400: requires HMAC sign. `lyricsAvailable` field in track object indicates availability.

**Response cleaning** (`response_filters.py`): whitelist pattern strips noise before LLM sees response.
To add a new cleaner: `_X_FIELDS` frozenset + `_is_X_like()` heuristic + `clean_X()` + branch in `_clean_object_list()`.
Playlist responses: `tracks` stripped in all contexts (list + single), `trackCount` preserved. Genres: only `id/name/title/value/subGenres`.

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
async def get_track_details(
    track_id: int,              # visible to MCP client
    ctx: Context,               # injected by FastMCP (hidden from client)
    track_svc: TrackService = Depends(get_track_service),  # injected (hidden)
) -> TrackDetails:              # structured output -> structuredContent in MCP
```

## Tool registration pattern

Each tool module exports a `register_*_tools(mcp)` function called by `create_workflow_mcp()`:

```python
def register_analysis_tools(mcp: FastMCP) -> None:
    @mcp.tool(annotations={"readOnlyHint": True}, tags={"analysis"})
    async def get_playlist_status(...) -> PlaylistStatus:
        ...
```

## Visibility control

Heavy tools (tagged `"heavy"`) are hidden by default via `mcp.disable(tags={"heavy"})` in `server.py`. Clients call `activate_heavy_mode` to unlock via `ctx.enable_components(tags={"heavy"})`.

## Prompts (workflow recipes)

4 prompts guide multi-step workflows:
- `expand_playlist` — analyze -> find similar -> build set
- `build_set_from_scratch` — search YM -> import -> find similar -> build set
- `improve_set` — score transitions -> adjust -> re-score
- `deliver_set_workflow` — score -> write files -> YM sync (with checkpoint on hard conflicts)

Each returns `list[Message]` with step-by-step instructions referencing namespaced tool names (e.g. `dj_get_playlist_status`, `ym_search_tracks`).

## Resources

- `playlist://{playlist_id}/status` — track count
- `catalog://stats` — total tracks
- `set://{set_id}/summary` — version count

Resources use FastMCP DI (`Depends`) for service injection, same as tools.

## Structured output

All DJ tools return typed Pydantic models (13 types in `app/mcp/types/`):
`PlaylistStatus`, `TrackDetails`, `ImportResult`, `AnalysisResult`, `SimilarTracksResult`, `SearchStrategy`, `SetBuildResult`, `TransitionScoreResult`, `ExportResult`, `SetTrackItem`, `SetVersionSummary`, `SetCheatSheet`, `DeliveryResult`.

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

## Visible-stages pattern (для операций > 5 сек)

Инструменты с длинными операциями должны быть прозрачными, не black-box:

```python
@mcp.tool(tags={"setbuilder"}, timeout=300)
async def long_op(ctx: Context, ...) -> ResultModel:
    # Stage 1: проверка — быстро, обратимо
    await ctx.info("Stage 1/3 — checking...")
    await ctx.report_progress(progress=0, total=3)
    result = await check()
    if critical_problem:
        decision = await resolve_conflict(ctx, "Continue?", options=["continue", "abort"])
        if decision != "continue":
            return ResultModel(status="aborted", ...)
    # Stage 2: запись/мутация
    await ctx.report_progress(progress=1, total=3)
    await ctx.info("Stage 2/3 — writing...")
    # Stage 3: опциональный внешний sync
    await ctx.report_progress(progress=2, total=3)
    await ctx.info("Stage 3/3 — syncing...")
    await ctx.report_progress(progress=3, total=3)
    return ResultModel(status="ok", ...)
```

`resolve_conflict` из `app/mcp/elicitation.py` — элицитация с выбором опций.

## Adding a new MCP tool

1. Create tool function in the appropriate `app/mcp/tools/*.py` module
2. Use `@mcp.tool(tags={"tag"}, annotations={"readOnlyHint": True})` for read-only tools
3. Add DI providers in `app/mcp/dependencies.py` if new services needed
4. Return a Pydantic model from `app/mcp/types.py` (create new if needed)
5. Add tests in `tests/mcp/test_workflow_*.py` — verify registration, tags, annotations, gateway namespacing
6. `Context` parameter: always non-optional (`ctx: Context`), FastMCP injects it automatically

## MCP gotchas

- **Pydantic return → `structured_content` shape**: FastMCP кладёт поля модели напрямую в `structured_content`, НЕ в `{"result": ...}`. Тест: `sc = raw.structured_content; assert sc["field"] == expected`.
- **MCP test seeding**: `workflow_mcp_with_db` патчит `app.mcp.dependencies.session_factory`. Seed данных — только через `engine` fixture: `factory = async_sessionmaker(engine); async with factory() as s: s.add(...)`.
- **`DjSetVersion` PK**: поле называется `set_version_id`, не `version_id`.
- **Pre-existing mypy errors (12)**: `wrap_list`/`unified_export`/`compute`/`sync/track_mapper` — не наши, не трогать.
- **B008 ruff rule**: `Depends()` in default args triggers B008. Solved with per-file-ignores in `pyproject.toml`:
  ```toml
  [tool.ruff.lint.per-file-ignores]
  "app/mcp/dependencies.py" = ["B008"]
  "app/mcp/tools/*.py" = ["B008"]
  ```
- **`combine_lifespans()`**: Required to compose FastAPI + MCP ASGI lifespans. Without it, MCP task group won't initialize. Import from `fastmcp.utilities.lifespan`.
- **`ctx.sample()` fallback**: Not all MCP clients support sampling. Always wrap in `try/except (NotImplementedError, AttributeError, TypeError)`.
- **OpenAPI spec patching**: `_patch_spec()` in `yandex_music/server.py` fixes: integer response codes (YAML parses `200` as int), missing operationIds, and circular `$ref` chains (Genre.subGenres, Artist.popularTracks, Album.artists/volumes).
- **`Context` parameter**: Always non-optional (`ctx: Context`), never `ctx: Context = None`. FastMCP injects it automatically.
- **mypy + fastmcp**: `fastmcp` is in `ignore_missing_imports` since it lacks type stubs.
- **MCP tests — two layers**: (1) Metadata tests verify tool names/tags/annotations via `mcp.list_tools()`. (2) Client integration tests use `Client(server)` for in-memory tool invocation. Both use shared fixtures from `tests/mcp/conftest.py`.
- **Server in fixture, Client in test body**: Don't open `Client` in fixtures — create server in fixture, open `Client` context manager inside test functions.
- **Stub tools testable without DB**: `import_playlist` and `import_tracks` are stubs — no database needed. DB-dependent tools need session mocking.

## Testing

Two-layer testing in `tests/mcp/` (see `rules/testing.md` for full details):

| Layer | What | How | DB needed |
|-------|------|-----|-----------|
| Metadata | Tool names, tags, annotations, namespacing | `mcp.list_tools()` on fixture | No |
| Client integration | Tool invocation, structured output, errors | `Client(server)` in-memory | Stubs: No, real tools: Yes |

Shared fixtures in `tests/mcp/conftest.py`: `workflow_mcp`, `gateway_mcp`, `ym_mcp`.

```python
# Client integration test pattern
async def test_import_tracks_stub(workflow_mcp: FastMCP):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("import_tracks", {"track_ids": [1, 2, 3]})
        assert not result.is_error
        assert result.data.skipped_count == 3
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
make mcp-list                                                    # ~57 tools
make mcp-call TOOL=dj_get_track_details ARGS='{"track_id": 45}' # call tool
make mcp-dev                                                     # HTTP :9100 + reload
make mcp-inspect                                                 # Inspector :6274
```
