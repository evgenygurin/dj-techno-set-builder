# MCP Tools Redesign — Agent-First Architecture

**Date**: 2026-02-19
**Status**: Design
**Scope**: Full MCP server redesign — tools, namespaces, data layer, multi-platform

## Problem

Current MCP server (~50 tools) designed around rigid workflows:
- Agent must chain 3-5 calls for simple operations (download → analyze → save)
- YM API responses pollute context (2.5 MB per track query)
- Track IDs are platform-specific — agent juggles `track_id`, `ym_track_id`
- No unified search — separate tools for DB, YM, criteria
- No multi-platform support beyond YM
- Stubs and duplicates bloat the tool list

## Design Principles

### Three Rules of Tool Generation

**Rule 1: Entity → CRUD**

Every entity in the system gets a standard set of operations:

```sql
Entity(X) → {
    list_X(limit, cursor)        # paginated list + stats
    get_X(ref)                   # one by ref
    create_X(data)               # create
    update_X(ref, data)          # update
    delete_X(ref)                # delete
}
```

Applies to: Track, Playlist, Set, SetVersion, Artist, AudioFeatures, Section.

**Rule 2: Compute Function → Tool**

Each pure audio analysis function becomes a separate tool:

```text
audio_util(fn) → tool(fn_name, input: track_ref | audio_path, output: Result)
```

Applies to: bpm, key, loudness, band_energies, spectral, beats, mfcc, structure,
stems, groove_similarity, mood_classify, score_transition.

**Rule 3: External API Endpoint → Tool**

Each endpoint of an external API maps 1:1 to a tool:

```text
API_endpoint(path, method) → tool(operation_name, params, response)
```

Applies to: Yandex Music (now), Spotify (future), Beatport (future), SoundCloud (future).

### Cross-Cutting Capabilities

On top of the three rules, universal capabilities apply to ALL tools:

| Capability | Description |
|-----------|-------------|
| Universal Search | One `search(query)` fans out to all sources |
| EntityFinder | `*_ref: str` parameter resolution (URN, text, fuzzy) |
| Response Shaping | Three levels: summary / detail / full |
| Pagination + Stats | Cursor-based + background metadata statistics |
| Visibility Control | Tags + `activate_*()` to show/hide tool groups |
| SyncEngine | Bidirectional per-playlist sync across platforms |

## Architecture

### Three Namespaces

```text
Gateway (DJ Set Builder)
│
├── Cross-cutting capabilities
│   ├── Universal Search (fan-out to all sources)
│   ├── EntityFinder (ref resolution via PlatformRegistry)
│   ├── Response Shaping (summary/detail/full + stats)
│   ├── Pagination (cursor + background metadata)
│   └── SyncEngine (bidirectional, per-playlist strategy)
│
├── PlatformRegistry
│   ├── YandexMusicAdapter (connected)
│   ├── SpotifyAdapter (future)
│   ├── BeatportAdapter (future)
│   └── SoundCloudAdapter (future)
│
├── dj namespace (visible by default)
│   ├── CRUD: tracks, playlists, sets, features, sections...
│   ├── Orchestrators: analyze, build, score, export, download
│   └── Sync: sync_playlist, set_source_of_truth
│
├── audio namespace (hidden, activate_audio_mode())
│   └── 1:1 with audio util pure functions
│
└── Platform-specific namespaces (hidden, raw API access)
    ├── ym (raw YM API via from_openapi())
    └── spotify (future)
```

## Entity Reference System (URN)

### Format

All `dj` tools accept `*_ref: str` instead of `*_id: int`:

```text
local:42              → internal DB ID
ym:12345              → Yandex Music track/playlist/artist
spotify:abc123        → Spotify (future)
beatport:67890        → Beatport (future)
42                    → auto: int → local:42
"Boris Brejcha"       → auto: text → fuzzy search
```

Entity type is determined by the parameter name (`track_ref`, `playlist_ref`, `set_ref`).

### Resolution Behavior

| Input Type | Behavior |
|-----------|----------|
| Exact ID (int, URN) | Resolve to one entity, execute action |
| Text string | Return ranked list of matches (always) |

Text refs ALWAYS return a list of matches — the agent decides which one(s) to act on.

### EntityFinder

```python
class EntityFinder:
    async def find(ref: str, entity_type: EntityType) -> FindResult

FindResult:
    exact: bool           # True = exact ID, False = text search
    entities: list[...]   # always a list (even for exact: list of 1)
    source: str           # "local" | "ym" | "spotify" | ...
```

Applies uniformly to: Track, Playlist, Set, Artist — all entities.

## Response Design

### Token Budget Principle

MCP tools NEVER return raw API data. Everything goes through Pydantic models.

### Three Response Levels

| Level | When | Size per entity |
|-------|------|----------------|
| Summary | Lists, search, batch | ~150 bytes |
| Detail | Single entity, get_* | ~300 bytes |
| Full | Explicit request, audio namespace | ~2 KB |

### Response Structure (all tools)

```json
{
    "results": { ... },              // actual data (paginated)
    "stats": {                       // background statistics
        "total_matches": {"tracks": 23, "playlists": 2, "ym": 156},
        "match_profile": {"bpm_range": [128, 142], "keys": ["5A", "7B"]}
    },
    "library": {                     // library context
        "total_tracks": 3247, "analyzed": 2890,
        "total_playlists": 15, "total_sets": 8
    },
    "pagination": {
        "limit": 20, "has_more": true, "cursor": "..."
    }
}
```

Agent always sees: filtered results + total counts + library context. No extra calls needed.

### Batch Operations

For batch operations (analyze, download) — progress summary only:

```json
{
    "total": 100, "completed": 98, "failed": 2,
    "failed_refs": ["ym:45", "ym:67"],
    "summary": {"bpm_range": [138, 152], "keys": ["5A", "6A"]}
}
```

## Universal Search

One `search()` tool replaces all separate search tools:

```python
search(
    query: str,                    # "Boris Brejcha", "acid techno", etc.
    scope: str = "all",            # "all" | "tracks" | "playlists" | "sets" | "ym"
    platform: str = "all",         # "all" | "local" | "ym" | "spotify"
    limit: int = 20,
)
```

Fan-out: local DB (tracks, playlists, sets, artists) + all connected platforms.
Fuzzy matching with Levenshtein/trigram for OCR tolerance.

Response includes categorized results + stats for each category.

## Multi-Platform Architecture

### Port/Adapter Pattern

```python
class MusicPlatform(Protocol):
    """Common interface for all music platforms."""

    async def search_tracks(query: str, limit: int) -> list[TrackSummary]
    async def get_track(platform_id: str) -> TrackDetail
    async def get_playlist(platform_id: str) -> PlaylistDetail
    async def create_playlist(name: str, track_ids: list[str]) -> str
    async def add_tracks_to_playlist(playlist_id: str, track_ids: list[str]) -> None
    async def remove_tracks_from_playlist(playlist_id: str, track_ids: list[str]) -> None
    async def delete_playlist(playlist_id: str) -> None
    async def get_download_url(track_id: str, bitrate: int) -> str | None
```

### Platform Registry

```python
class PlatformRegistry:
    platforms: dict[str, MusicPlatform]

    def is_connected(name: str) -> bool
    def get(name: str) -> MusicPlatform
    def list_connected() -> list[str]
```

### Bidirectional Sync

Source of truth is configurable per playlist:

```python
class SyncStrategy:
    source_of_truth: str    # "local" (default) | "ym" | "spotify"
    direction: str          # "local→remote" | "remote→local" | "bidirectional"
    conflict: str           # "source_wins" | "newest_wins" | "manual"
```

**Default flow (local = source):**
1. Agent modifies local playlist
2. SyncEngine detects connected platforms
3. For each: playlist exists? sync. Doesn't exist? create + sync.
4. Returns sync status per platform.

**Reverse flow (platform = source):**
1. Agent calls `sync_playlist(ref, source="ym")`
2. SyncEngine fetches remote playlist → diffs with local
3. Applies changes to local DB
4. Optionally propagates to other platforms.

### Playlist Model Extension

```python
Playlist:
    name: str
    source_of_truth: str = "local"
    sync_targets: list[str] = []          # ["ym", "spotify"]
    platform_ids: dict[str, str] = {}     # {"ym": "1003:250905515", "spotify": "abc"}
```

## Tool Inventory

### dj namespace (visible, ~20+ tools)

**CRUD** (5 per entity × N entities):

| Entity | list | get | create | update | delete |
|--------|------|-----|--------|--------|--------|
| Track | list_tracks | get_track | create_track | update_track | delete_track |
| Playlist | list_playlists | get_playlist | create_playlist | update_playlist | delete_playlist |
| Set | list_sets | get_set | create_set | update_set | delete_set |
| AudioFeatures | list_features | get_features | save_features | — | — |

**Orchestrators:**

| Tool | Purpose | Type |
|------|---------|------|
| search | Universal fan-out search | read |
| filter_tracks | Filter by BPM/key/energy/mood | read |
| analyze_track | Full audio analysis pipeline (no DB) | compute |
| analyze_batch | Batch analysis with progress | compute |
| build_set | GA optimization (no DB) | compute |
| score_transitions | Score all adjacent pairs | compute |
| export_set | Generate m3u/json/rekordbox | compute |
| download_tracks | Download from platform + progress | action |
| sync_playlist | Bidirectional sync with platform(s) | action |
| set_source_of_truth | Configure sync strategy | action |
| classify_tracks | Mood classification | compute |

### audio namespace (hidden, ~12 tools)

| Tool | Input | Output | Deps |
|------|-------|--------|------|
| compute_bpm | track_ref \| path | BpmResult | essentia |
| compute_key | track_ref \| path | KeyResult | essentia |
| compute_loudness | track_ref \| path | LoudnessResult | essentia |
| compute_band_energies | track_ref \| path | BandEnergyResult | scipy |
| compute_spectral | track_ref \| path | SpectralResult | essentia |
| detect_beats | track_ref \| path | BeatsResult | essentia |
| extract_mfcc | track_ref \| path | MfccResult | librosa |
| segment_structure | track_ref \| path | list[SectionResult] | essentia |
| separate_stems | track_ref \| path | StemsResult | demucs |
| score_transition_raw | features_a, features_b | TransitionScore | numpy |
| groove_similarity | ref_a, ref_b \| env_a, env_b | float | numpy |
| classify_mood | track_ref \| features | MoodClassification | — |

### Platform namespaces (hidden, raw API access)

**ym** (~30 tools via from_openapi()) — full YM API, for advanced use.
Future: **spotify**, **beatport**, **soundcloud**.

### Visibility Control

```python
# Default
dj:       visible      # CRUD + orchestrators
audio:    hidden       # activate_audio_mode()
ym:       hidden       # activate_ym_raw()
spotify:  hidden       # activate_spotify_raw()
```

## Workflows Layer

**MCP Prompts** — server-side workflow recipes (universal, any MCP client):
- `expand_playlist` — search → download → analyze → add
- `build_set_from_scratch` — search YM → import → build → export
- `improve_set` — score → identify weak → rebuild → compare

**Claude Code Skills** — extended workflows (.md files):
- Detailed step-by-step instructions for complex multi-tool flows
- Reference specific tool names and expected outputs
- Include decision trees for edge cases

Both layers describe WHEN and HOW to use tools. Tools themselves are stateless operations.

## What Changes vs Current

| Aspect | Current | New |
|--------|---------|-----|
| Tools count | ~50 (20 DJ + 30 YM) | ~45 DJ + 12 audio + 30 YM (hidden) |
| Search | 3 separate tools | 1 universal `search()` |
| Track identity | `track_id: int` | `track_ref: str` (URN) |
| Response size | Raw API data leaks | Pydantic models + stats |
| Pagination | None | Cursor-based + metadata |
| Persist | Mixed (some auto, some not) | Explicit: compute returns data, persist saves |
| Stubs | 5 stubs | Removed (implement when ready) |
| Duplicates | 2 export sets | 1 `export_set(format=...)` |
| Multi-platform | YM only, hardcoded | Port/Adapter + Registry |
| Sync | 3 stubs | SyncEngine with configurable source of truth |
| Visibility | 1 heavy tag | Namespace-level + tags |

## Implementation Notes

### Key Components to Build

1. **EntityFinder** — ref parsing + fuzzy search + platform resolution
2. **PlatformRegistry** — adapter management + connection status
3. **MusicPlatform protocol** — common interface
4. **YandexMusicAdapter** — wraps existing YM client
5. **SyncEngine** — diff + apply + conflict resolution
6. **Response shaping** — summary/detail/full Pydantic models
7. **Universal search** — fan-out + merge + rank
8. **CRUD generators** — DRY tool generation from entity definitions
9. **Pagination** — cursor encoding/decoding + count queries
10. **Visibility manager** — activate/deactivate namespace tools

### Migration Path

Phase 1: EntityFinder + response shaping + universal search (no breaking changes)
Phase 2: CRUD paradigm + compute/persist split
Phase 3: Multi-platform abstraction + SyncEngine
Phase 4: Remove legacy tools, stubs, duplicates
