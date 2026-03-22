# MCP Tools Redesign (Phase 3) — Plan Review (Critical)

Date: 2026-02-19
Target plan: `docs/plans/2026-02-19-mcp-tools-redesign-phase3-plan.md`

This is a critical plan review (blockers first). It is written against the current repository state, not an idealized greenfield.

## Executive Summary

Phase 3 is the right milestone (adapters + registry + sync engine), but the plan as written will not deliver a working multi-platform sync:

- The identifier system is internally inconsistent (`ym` vs `yandex_music`, raw IDs vs prefixed IDs, playlist ID shape), which will make mapping queries silently return empty results and/or break playlist fetches.
- The plan’s Yandex adapter does not implement playlist writes, yet SyncEngine and set sync depend on writes to actually “sync”.
- The MCP tools for sync are described as “refs + envelope” but are specified as `*_id: int` and return plain dicts.
- Visibility tooling for “ym raw” is specified on the wrong server layer and uses tags that are never applied to YM tools.

Net: before coding Phase 3, the plan must lock down canonical IDs + playlist identifier formats, and explicitly implement YM playlist write APIs.

## Blockers (Must Fix Before Implementation)

### 1) Canonical platform key mismatch: `ym` vs `yandex_music` vs `yandex`

The plan mixes at least three different identifiers for the same platform:

- Protocol + adapter name: `"ym"` (e.g. `YandexMusicAdapter.name == "ym"`).
- DB provider code seeded by the app: `"yandex_music"` (see `app/database.py:_seed_providers()` and `app/models/providers.py`).
- Some existing services still use `"yandex"` (e.g. `DownloadService._get_yandex_track_id()` queries `Provider.provider_code == "yandex"`).

Impact:

- `DbTrackMapper` queries `Provider.provider_code == platform` (plan snippet around Task 8). If SyncEngine passes `platform.name == "ym"`, mappings will always be empty because the DB uses `"yandex_music"`.
- Sync operations will “work” but skip everything (or, worse, delete remote tracks due to partial mapping; see blocker #5).

Fix:

- Introduce a single canonical “platform key” used in:
  - URN prefixes (`ym:12345`),
  - `MusicPlatform.name`,
  - playlist `platform_ids` keys,
  - `PlatformRegistry.get(name)`.
- Separately keep “provider_code” for DB (`providers.provider_code`) and add an explicit mapping layer:
  - e.g. `PlatformKey.YM -> provider_code='yandex_music'`.
- Update `DbTrackMapper` API to accept `provider_code` (or accept platform key and internally map to provider_code).

### 2) Platform track IDs are inconsistently represented (`"12345"` vs `"ym_12345"`)

Within Phase 3, tests and examples use both:

- raw YM IDs: `"12345"` (adapter tests), and
- prefixed strings: `"ym_100"` (sync tests/examples).

Impact:

- You cannot safely compute diffs between local↔remote if IDs are not normalized.
- ProviderTrackId should store the raw provider ID (`"12345"`), not a decorated string; the URN prefix belongs in `*_ref` only (e.g. `ym:12345`).

Fix:

- Define: platform IDs are raw provider IDs (strings), no prefixes.
- URNs add the prefix at the ref layer only.
- Update SyncEngine tests and `DbTrackMapper` tests accordingly.

### 3) YM playlist identifier shape is undefined (needs userId + kind)

The plan uses all of these for YM playlists:

- `"1003"` (kind only),
- `"1003:250905515"` (composite), and
- `DjSet.ym_playlist_id` as `int` kind (existing model).

Meanwhile, adapter code for `get_playlist(platform_id)` calls `fetch_playlist_tracks(self._user_id, platform_id)`, which only works if `platform_id == kind` and the adapter is permanently bound to the correct user.

Impact:

- If `DjPlaylist.platform_ids["ym"]` stores composite `"uid:kind"`, SyncEngine will pass that string into `get_playlist()` and break.
- If it stores kind-only, you cannot sync playlists across different YM owners or represent shared playlists cleanly.

Fix:

- Pick and document one format for `platform_ids` values per platform:
  - Option A: store `kind` only and assume adapter user binding.
  - Option B (more robust): store `"{uid}:{kind}"` and make the adapter parse it.
- Align: model columns, schemas, SyncEngine, and tests must all use the same format.

### 4) YandexMusicAdapter does not implement playlist writes, but SyncEngine requires it

Task 3’s adapter explicitly raises `NotImplementedError` for:

- `create_playlist`
- `add_tracks_to_playlist`
- `remove_tracks_from_playlist`
- `delete_playlist`

But SyncEngine’s core promise is to add/remove tracks to sync. Without write support, `sync_playlist(local_to_remote|bidirectional)` will be a no-op and remain effectively a stub.

Fix:

- Implement YM playlist write operations in the adapter (or underlying client) in Phase 3, not later:
  - `create_playlist`
  - `change_playlist_tracks` (diff-based API)
  - `delete_playlist` (optional for Phase 3)
- Reuse existing YM OpenAPI knowledge and form-urlencoding behavior already implemented in `app/mcp/yandex_music/server.py` where possible, instead of inventing a third YM client surface.

### 5) SyncEngine can delete remote tracks when local mapping is incomplete

SyncEngine computes diffs on “platform IDs” that are derived from local tracks by mapping:

- local tracks without mapping are dropped from `local_platform_ids`.

Then `LOCAL_TO_REMOTE` removes remote tracks that are not in `local_platform_ids`.

Impact:

- If mappings are incomplete (common), SyncEngine may delete remote tracks that actually correspond to local tracks without mappings (or tracks the user wants to keep).

Fix:

- Safe default: do not remove from remote when mapping coverage < 100% unless an explicit `prune=True` flag is provided.
- Alternatively: only ever add in `LOCAL_TO_REMOTE` unless a “strict mirror” mode is explicitly enabled.

### 6) Playlist sync columns: server defaults and schema mismatch

Task 5 proposes `server_default="local"` for a string column. In this codebase, string defaults are written as quoted SQL via `text("'running'")` (see `app/models/runs.py`), because unquoted strings can generate invalid SQL.

Fix:

- Use `server_default=text("'local'")` for `source_of_truth`.

Also: the plan text mentions `sync_targets`, but the model snippet only adds `source_of_truth` and `platform_ids`.

Fix:

- Either add `sync_targets` in Phase 3 (as JSON list or string array representation) or remove it from the Phase 3 scope and docs.

### 7) MCP sync tools don’t follow the stated Phase 1–2 conventions

The plan states:

- accept URN refs, and
- return envelope responses.

But tool signatures are still `playlist_id: int` / `set_id: int` and return plain dicts.

Fix:

- Update tool signatures to accept `playlist_ref` / `set_ref` and resolve via EntityFinder.
- Return typed responses (Pydantic) and/or Phase 2 envelope models consistently.

## High-Risk / Design Gaps

### 8) Resource lifecycle: PlatformRegistry singleton needs shutdown handling

The plan adds a module-level `_platform_registry` singleton. YM clients maintain an `httpx.AsyncClient` that should be closed.

Fix:

- Attach registry `close_all()` to MCP lifespan shutdown (gateway lifespan is a good place), or avoid module singleton and use a managed resource in lifespan context.

### 9) Visibility control for raw YM tools is specified at the wrong layer

`activate_ym_raw()` is added to `DJ Workflows` server (`create_workflow_mcp()`), but raw YM tools live on the gateway-mounted `ym` namespace (`create_dj_mcp()` mounts `create_yandex_music_mcp()`).

Additionally, enabling tags `{"ym_raw"}` will do nothing unless YM tools are tagged and disabled by default (not specified in Phase 3).

Fix:

- Implement YM raw visibility on the gateway server, not the workflow server, and explicitly tag+disable YM tools if FastMCP supports it.

### 10) Tests use brittle FastMCP internals

Visibility tests inspect `mcp._tool_manager._tools` directly. This is implementation detail and likely to break on FastMCP upgrades.

Fix:

- Use `Client.list_tools()` or `FastMCP.list_tools()` public API.

## Recommended Plan Adjustments (Minimal to Make Phase 3 Deliverable)

1) Add a “Task 0: Canonical ID Schema”
   - Define platform keys (`ym`, `spotify`, ...) vs DB provider codes.
   - Define platform track ID normalization (raw ID only).
   - Define platform playlist ID format per platform.
   - Update all snippets/tests to match.

2) Expand Task 3: Implement YM playlist write APIs
   - Without this, SyncEngine cannot actually sync.

3) Make SyncEngine safe-by-default against deletions
   - Add `prune` flag and/or mapping-coverage guardrails.

4) Align MCP sync tools with refs + envelope
   - `sync_playlist(playlist_ref=...)`, `set_source_of_truth(playlist_ref=...)`, `link_playlist(playlist_ref=...)`.

5) Wire registry lifecycle into `app/mcp/lifespan.py`
   - Close adapters on shutdown.
