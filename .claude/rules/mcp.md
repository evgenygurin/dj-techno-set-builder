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
├── types/
│   ├── __init__.py          # re-exports all 36 Pydantic models
│   ├── curation.py          # 8 curation workflow types
│   ├── entities.py          # 7 entity summary/detail types
│   ├── responses.py         # 8 response envelope types
│   └── workflows.py         # 13 DJ workflow result types
├── dependencies.py          # DI providers (FastMCP Depends, async session)
├── tools/
│   ├── __init__.py            # re-exports create_workflow_mcp
│   ├── server.py              # Factory + visibility control
│   ├── compute.py             # analyze_track, compute_set_order (heavy)
│   ├── curation.py            # classify_tracks, review_set, analyze_library_gaps
│   ├── delivery.py            # deliver_set (score → write files → optional YM sync)
│   ├── discovery.py           # find_similar_tracks
│   ├── download.py            # download_tracks
│   ├── export.py              # export_set_rekordbox
│   ├── features.py            # list_features, get_features, save_features
│   ├── playlist.py            # list/get/create/update/delete playlists
│   ├── search.py              # search, filter_tracks
│   ├── set.py                 # list/get/create/update/delete sets + versions, cheat_sheet
│   ├── setbuilder.py          # build_set, rebuild_set, score_transitions
│   ├── sync.py                # sync_playlist, link_playlist, set_source_of_truth, sync_set_to/from_ym
│   ├── track.py               # list/get/create/update/delete tracks
│   └── unified_export.py      # export_set (m3u/json/rekordbox)
├── prompts/
│   └── workflows.py         # 4 recipe prompts (expand, build, improve, deliver)
├── resources/
│   └── status.py            # 3 resources (playlist, catalog, set)
└── yandex_music/
    ├── __init__.py           # re-exports create_yandex_music_mcp
    ├── server.py             # OpenAPI -> FastMCP factory with spec patching
    └── config.py             # RouteMap exclusions, camelCase->snake_case
```

## Gateway composition

`create_dj_mcp()` in `app/mcp/gateway.py`:
- Mounts **Yandex Music** sub-server at namespace `"ym"` (28 tools from OpenAPI)
- Mounts **DJ Tools** sub-server at namespace `"dj"` (52 hand-written tools)
- Adds `PromptsAsTools` + `ResourcesAsTools` transforms for tool-only MCP clients
- Total: 84 tools (28 YM + 52 DJ + 4 transforms)

## DJ Workflow tools (namespace "dj")

52 tools across 16 modules + server.py:

| Tool | Tags | Read-only | Description |
|------|------|-----------|-------------|
| `search` | search | Yes | Universal search across all entities and platforms |
| `filter_tracks` | search | Yes | Filter tracks by audio parameters (BPM, key, energy) |
| `list_tracks` | crud, track | Yes | List tracks with optional text search |
| `get_track` | crud, track | Yes | Get track details by ref |
| `create_track` | crud, track | No | Create a new track |
| `update_track` | crud, track | No | Update track fields by ref |
| `delete_track` | crud, track | No | Delete a track by ref |
| `list_playlists` | crud, playlist | Yes | List playlists with optional text search |
| `get_playlist` | crud, playlist | Yes | Get playlist details by ref |
| `create_playlist` | crud, playlist | No | Create a new playlist |
| `update_playlist` | crud, playlist | No | Update playlist fields by ref |
| `delete_playlist` | crud, playlist | No | Delete a playlist by ref |
| `list_sets` | crud, set | Yes | List DJ sets |
| `get_set` | crud, set | Yes | Get set details by ref |
| `create_set` | crud, set | No | Create a new DJ set |
| `update_set` | crud, set | No | Update set fields by ref |
| `delete_set` | crud, set | No | Delete a DJ set by ref |
| `get_set_tracks` | crud, set | Yes | All tracks of a version with BPM/key/LUFS/pinned |
| `list_set_versions` | crud, set | Yes | Version history with track_count and score |
| `get_set_cheat_sheet` | set, setbuilder | Yes | Full set: tracks + transitions + summary + text |
| `list_features` | crud, features | Yes | List tracks with computed audio features |
| `get_features` | crud, features | Yes | Get full audio features for a track |
| `save_features` | crud, features | No | Persist computed audio features |
| `analyze_track` | compute, analysis | No | Run full audio analysis pipeline on a track |
| `compute_set_order` | compute, setbuilder | No | Compute optimal track ordering without saving |
| `export_set` | export | Yes | Export set (m3u/json/rekordbox) |
| `export_set_rekordbox` | export | Yes | Export set as Rekordbox XML |
| `download_tracks` | download, yandex | No | Download MP3 files from YM to iCloud library |
| `find_similar_tracks` | discovery | No | LLM-assisted similar track search via `ctx.sample()` |
| `build_set` | setbuilder | No | Create DJ set + template-aware GA optimization |
| `rebuild_set` | setbuilder | No | Rebuild set with pinned/excluded constraints |
| `score_transitions` | setbuilder | Yes | Score all transitions in a set version |
| `deliver_set` | setbuilder | No | Score → write files → optional YM (3 visible stages) |
| `classify_tracks` | curation | Yes | Classify all tracks by 15 mood categories |
| `analyze_library_gaps` | curation | Yes | Analyze library for gaps relative to a template |
| `review_set` | curation, setbuilder | Yes | Review set: weak transitions, suggestions |
| `audit_playlist` | curation | Yes | Audit playlist tracks against techno criteria |
| `distribute_to_subgenres` | curation | No | Distribute tracks to 15 subgenre playlists |
| `discover_candidates` | discovery, curation | No | Find similar tracks via YM recommendations |
| `expand_playlist_discover` | discovery, curation | No | Discover + filter candidates in one call |
| `expand_playlist_full` | discovery, curation | No | Full expand: discover + import + add to playlist |
| `populate_from_ym` | crud, playlist | No | Populate local playlist from YM playlist |
| `score_track_pairs` | setbuilder | Yes | Score specific track pair transitions |
| `sync_playlist` | sync | No | Bidirectional sync between local playlist and platform |
| `set_source_of_truth` | sync | No | Configure source of truth for a playlist |
| `link_playlist` | sync | No | Link local playlist to platform playlist |
| `sync_set_to_ym` | sync, yandex | No | Push DJ set to YM as playlist |
| `sync_set_from_ym` | sync, yandex | No | Read feedback from YM, detect changes |
| `batch_sync_sets_to_ym` | sync, yandex | No | Batch-push multiple sets to YM |
| `activate_heavy_mode` | admin | No | Enable heavy analysis tools |
| `activate_ym_raw` | admin | No | Enable raw Yandex Music API tools |
| `list_platforms` | admin | Yes | List configured music platforms |

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

Each returns `list[Message]` with step-by-step instructions referencing namespaced tool names (e.g. `dj_get_playlist`, `ym_search_yandex_music`).

## Resources

- `playlist://{playlist_id}/status` — track count
- `catalog://stats` — total tracks
- `set://{set_id}/summary` — version count

Resources use FastMCP DI (`Depends`) for service injection, same as tools.

## Structured output

All DJ tools return typed Pydantic models (37 types across 4 files in `app/mcp/types/`):

| File | Count | Key types |
|------|-------|-----------|
| `entities.py` | 7 | TrackSummary, TrackDetail, PlaylistSummary, PlaylistDetail, SetSummary, SetDetail, ArtistSummary |
| `responses.py` | 8 | PaginationInfo, MatchStats, LibraryStats, SearchResponse, FindResult, EntityListResponse, EntityDetailResponse, ActionResponse |
| `workflows.py` | 13 | SimilarTracksResult, SearchStrategy, SetBuildResult, TransitionScoreResult, ExportResult, SetTrackItem, SetVersionSummary, SetCheatSheet, DeliveryResult, TransitionSummary, AdjustmentPlan, SwapSuggestion, ReorderSuggestion |
| `curation.py` | 9 | ClassifyResult, MoodDistribution, CurateCandidate, CurateSetResult, WeakTransition, SetReviewResult, GapDescription, LibraryGapResult, DistributeResult |

Return type annotation → `structuredContent` in MCP protocol response.

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
4. Return a Pydantic model from `app/mcp/types/` (create new if needed)
5. Add tests in `tests/mcp/test_workflow_*.py` — verify registration, tags, annotations, gateway namespacing
6. `Context` parameter: always non-optional (`ctx: Context`), FastMCP injects it automatically

## MCP gotchas

- **Pydantic return → `structured_content` shape**: FastMCP кладёт поля модели напрямую в `structured_content`, НЕ в `{"result": ...}`. Тест: `sc = raw.structured_content; assert sc["field"] == expected`.
- **MCP test seeding**: `workflow_mcp_with_db` патчит `app.mcp.dependencies.session_factory`. Seed данных — только через `engine` fixture: `factory = async_sessionmaker(engine); async with factory() as s: s.add(...)`.
- **`DjSetVersion` PK**: поле называется `set_version_id`, не `version_id`.
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
- **DB-independent tools**: read-only tools without DI don't need database fixtures. DB-dependent tools need session mocking via `workflow_mcp_with_db`.

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
make mcp-list                                                    # ~75 tools
make mcp-call TOOL=dj_get_track ARGS='{"track_ref": 45}'        # call tool
make mcp-dev                                                     # HTTP :9100 + reload
make mcp-inspect                                                 # Inspector :6274
```
