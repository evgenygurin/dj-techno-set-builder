# Yandex Music Client Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate 3 duplicate YM clients into one `app/clients/yandex_music.py`, move YM services into `app/services/yandex/`, eliminate cross-layer imports.

**Architecture:** Single YM HTTP client with rate limiting + download + all playlist operations. Services in `app/services/yandex/` handle business logic (import, enrich, download). MCP tools and platforms import only from these two locations.

**Tech Stack:** httpx, SQLAlchemy async, FastMCP Depends

---

## Problem

3 YM HTTP clients exist:

| File | LOC | Has rate-limit | Has download | Has playlist write | Used by |
|------|-----|---------------|-------------|-------------------|---------|
| `app/clients/yandex_music.py` | 112 | No | No | Yes | platforms/yandex.py, enrichment |
| `app/services/yandex_music_client.py` | 201 | Yes | Yes | No | import_yandex.py, download.py, MCP DI |
| `app/mcp/platforms/yandex.py` | 135 | — | Delegates | Delegates | sync, MCP tools |

This violates DRY. The adapter wraps BOTH clients because neither is complete.

## Target Structure

```text
app/clients/
└── yandex_music.py          # Single HTTP client (merge of both, ~250 LOC)
                               # rate-limit, download, search, playlist CRUD, batch fetch

app/services/yandex/
├── __init__.py               # re-exports
├── importer.py               # ImportYandexService (from import_yandex.py)
├── enrichment.py             # YandexMusicEnrichmentService (from yandex_music_enrichment.py)
└── downloader.py             # DownloadService (from download.py)

app/mcp/platforms/
└── yandex.py                 # YandexMusicAdapter (delegates to single client)
```

**Deleted files:**
- `app/services/yandex_music_client.py` (merged into `app/clients/yandex_music.py`)
- `app/services/import_yandex.py` (moved to `app/services/yandex/importer.py`)
- `app/services/yandex_music_enrichment.py` (moved to `app/services/yandex/enrichment.py`)
- `app/services/download.py` (moved to `app/services/yandex/downloader.py`)

---

### Task 1: Merge two HTTP clients into one

**Files:**
- Modify: `app/clients/yandex_music.py` (merge from services/yandex_music_client.py)
- Delete: `app/services/yandex_music_client.py`
- Test: `tests/test_ym_client.py`, `tests/test_yandex_music_client.py`

The merged client has:
- Rate limiting (from services/yandex_music_client.py)
- All methods from both clients (search, fetch, download, playlist CRUD, similar tracks)
- `ParsedYmTrack` dataclass and `parse_ym_track()` function (keep in client module)
- No BaseService inheritance (pure HTTP client, not a service)

- [ ] **Step 1: Write test for merged client**

```python
# tests/test_ym_client_merged.py
async def test_client_has_all_methods():
    from app.clients.yandex_music import YandexMusicClient
    client = YandexMusicClient(token="test", user_id="123")
    # Check all methods exist
    assert hasattr(client, 'search_tracks')
    assert hasattr(client, 'fetch_tracks')
    assert hasattr(client, 'fetch_tracks_metadata')
    assert hasattr(client, 'fetch_playlist_tracks')
    assert hasattr(client, 'create_playlist')
    assert hasattr(client, 'add_tracks_to_playlist')
    assert hasattr(client, 'delete_playlist')
    assert hasattr(client, 'get_similar_tracks')
    assert hasattr(client, 'resolve_download_url')
    assert hasattr(client, 'download_track')
    await client.close()
```

Run: `pytest tests/test_ym_client_merged.py -v`

- [ ] **Step 2: Merge clients**

Rewrite `app/clients/yandex_music.py` — combine rate limiting, download, all playlist ops from both sources. Keep `ParsedYmTrack` + `parse_ym_track()` in this file.

- [ ] **Step 3: Run existing YM tests**

Run: `pytest tests/test_ym_client.py tests/test_yandex_music_client.py -v`
Fix any import errors — update to `from app.clients.yandex_music import ...`

- [ ] **Step 4: Update all consumers**

Replace all imports of old client:
- `app/services/import_yandex.py` — `from app.services.yandex_music_client import` → `from app.clients.yandex_music import`
- `app/services/download.py` — same
- `app/mcp/dependencies.py` — remove `YMDownloadClient` alias, use single `YandexMusicClient`
- `app/mcp/platforms/yandex.py` — remove `YMApiClient` alias, use single client
- `app/mcp/tools/*.py` — update any direct imports

Run: `pytest -x -q` — all tests pass

- [ ] **Step 5: Delete old file**

```bash
rm app/services/yandex_music_client.py
```

Run: `pytest -x -q` — all tests pass

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor(ym): merge two HTTP clients into one"
```

---

### Task 2: Create `app/services/yandex/` subpackage

**Files:**
- Create: `app/services/yandex/__init__.py`
- Move: `app/services/import_yandex.py` → `app/services/yandex/importer.py`
- Move: `app/services/yandex_music_enrichment.py` → `app/services/yandex/enrichment.py`
- Move: `app/services/download.py` → `app/services/yandex/downloader.py`

- [ ] **Step 1: Create subpackage and move files**

```bash
mkdir -p app/services/yandex
mv app/services/import_yandex.py app/services/yandex/importer.py
mv app/services/yandex_music_enrichment.py app/services/yandex/enrichment.py
mv app/services/download.py app/services/yandex/downloader.py
```

Create `app/services/yandex/__init__.py`:
```python
"""Yandex Music integration services."""

from app.services.yandex.downloader import DownloadResult, DownloadService
from app.services.yandex.enrichment import YandexMusicEnrichmentService
from app.services.yandex.importer import ImportYandexService

__all__ = [
    "DownloadResult",
    "DownloadService",
    "ImportYandexService",
    "YandexMusicEnrichmentService",
]
```

- [ ] **Step 2: Update all consumers**

Search and replace imports:
- `from app.services.import_yandex import` → `from app.services.yandex.importer import`
- `from app.services.yandex_music_enrichment import` → `from app.services.yandex.enrichment import`
- `from app.services.download import` → `from app.services.yandex.downloader import`

Files to update:
- `app/mcp/dependencies.py`
- `app/mcp/tools/download.py`
- `app/mcp/tools/sync.py`
- `app/mcp/tools/curation_discovery.py`
- `tests/test_import_yandex_service.py`
- `tests/test_ym_enrichment_service.py`
- `tests/services/test_download_service.py`

- [ ] **Step 3: Run full test suite**

Run: `pytest -x -q`

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor(ym): move YM services into app/services/yandex/"
```

---

### Task 3: Simplify YandexMusicAdapter

**Files:**
- Modify: `app/mcp/platforms/yandex.py`

Now that there's one client, the adapter no longer needs two client references.

- [ ] **Step 1: Simplify constructor**

Remove `api_client` parameter — the single `YandexMusicClient` has all methods.

```python
class YandexMusicAdapter:
    def __init__(self, client: YandexMusicClient, user_id: str) -> None:
        self._client = client
        self._user_id = user_id
```

- [ ] **Step 2: Update factory**

`app/mcp/platforms/factory.py` — simplify creation to pass single client.

- [ ] **Step 3: Run platform tests**

Run: `pytest tests/mcp/platforms/ -v`

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor(ym): simplify adapter to use single client"
```

---

### Task 4: Clean up MCP dependencies

**Files:**
- Modify: `app/mcp/dependencies.py`

- [ ] **Step 1: Simplify DI providers**

Remove separate `YMApiClient` / `YMDownloadClient` aliases. Single `get_ym_client()` provider.

- [ ] **Step 2: Run MCP tests**

Run: `pytest tests/mcp/ -v`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "refactor(ym): clean up MCP DI providers"
```

---

### Task 5: Remove `app/schemas/yandex_music.py` dependency from services

**Files:**
- Modify: `app/services/yandex/enrichment.py`

The enrichment service imports `YmEnrichResponse` from schemas. Replace with a plain dataclass.

- [ ] **Step 1: Replace schema dependency**

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_ym_enrichment_service.py -v`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "refactor(ym): decouple enrichment from REST schemas"
```

---

## Verification

After all tasks:

```bash
pytest -x -q                    # All tests pass
uv run lint-imports             # Import contracts clean
make mcp-list                   # 84 tools registered
rg "from app.services.yandex_music_client" app/  # 0 results
rg "from app.services.import_yandex" app/        # 0 results
rg "from app.services.download" app/             # 0 results (only yandex/downloader)
```
