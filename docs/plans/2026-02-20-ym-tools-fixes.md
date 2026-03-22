# YM Tools Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Починить 2 сломанных YM инструмента и 3 с огромными ответами, выявленных в тестировании.

**Architecture:** Все фиксы в двух файлах: `app/mcp/yandex_music/config.py` (исключения endpoint'ов) и `app/mcp/yandex_music/response_filters.py` (cleaners для genre/playlist). Паттерн уже задокументирован в коде — добавляем новые `_is_X_like()` / `clean_X()` по аналогии.

**Tech Stack:** Python 3.12, FastMCP 3.0, httpx event hooks, pytest + pytest-asyncio

---

## Проблемы и их суть

| Инструмент | Проблема | Решение |
|-----------|---------|---------|
| `ym_get_artist_brief_info` | HTTP 403 (Yandex CAPTCHA на этом endpoint) | Исключить из MCP |
| `ym_get_track_lyrics` | HTTP 400 (требует HMAC `sign` + `timeStamp`) | Исключить из MCP |
| `ym_get_genres` | ~177k символов (вложенные subGenres без фильтрации) | Clean genre: keep id/name/value/title |
| `ym_get_play_lists` | ~86k символов (много плейлистов со списком треков) | Убрать `tracks` при листинге |
| `ym_get_playlist_by_id` | ~154k символов (557 треков с полными объектами) | Компактный формат треков |

---

## Task 1: Исключить сломанные endpoints

**Files:**
- Modify: `app/mcp/yandex_music/config.py`
- Test: `tests/mcp/test_yandex_music.py`

### Step 1: Написать falling тест

```python
# tests/mcp/test_yandex_music.py — добавить в конец файла

async def test_broken_endpoints_are_excluded(ym_mcp: FastMCP):
    """brief-info (403) and lyrics (HMAC required) must not be exposed."""
    tools = await ym_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "get_artist_brief_info" not in tool_names, "brief-info always returns 403"
    assert "get_track_lyrics" not in tool_names, "lyrics requires HMAC sign, not implemented"
```

### Step 2: Убедиться что тест падает

```bash
uv run pytest tests/mcp/test_yandex_music.py::test_broken_endpoints_are_excluded -v
```

Ожидание: `FAILED — AssertionError: brief-info always returns 403`

### Step 3: Добавить exclusions в config.py

В `app/mcp/yandex_music/config.py`, расширить `EXCLUDE_ROUTE_MAPS`:

```python
EXCLUDE_ROUTE_MAPS: list[RouteMap] = [
    RouteMap(pattern=r"^/account", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/feed", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/landing3", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/rotor", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/queues", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/settings$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/permission-alerts$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/token$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/play-audio$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/non-music", mcp_type=MCPType.EXCLUDE),
    # ── Broken endpoints ────────────────────────────────────────────────────────
    # HTTP 403 from Yandex Smart Antirobot on this specific endpoint.
    # Use ym_search_yandex_music(type=artist) for artist info instead.
    RouteMap(pattern=r"^/artists/[^/]+/brief-info$", mcp_type=MCPType.EXCLUDE),
    # HTTP 400: requires HMAC sign = md5(trackId + timestamp + secret).
    # Signing not implemented. lyricsAvailable field in track object indicates availability.
    RouteMap(pattern=r"^/tracks/[^/]+/lyrics$", mcp_type=MCPType.EXCLUDE),
]
```

### Step 4: Запустить тест

```bash
uv run pytest tests/mcp/test_yandex_music.py -v
```

Ожидание: все 5 тестов PASS

### Step 5: Убедиться что существующий тест `test_dj_relevant_tools_present` не сломан

```bash
uv run pytest tests/mcp/test_yandex_music.py::test_dj_relevant_tools_present -v
```

### Step 6: Commit

```bash
git add app/mcp/yandex_music/config.py tests/mcp/test_yandex_music.py
git commit -m "fix(mcp): exclude broken YM endpoints (brief-info 403, lyrics HMAC)"
```

---

## Task 2: Clean genre response (177k → ~5k)

**Files:**
- Modify: `app/mcp/yandex_music/response_filters.py`
- Test: `tests/mcp/test_yandex_music.py` (или новый `test_response_filters.py`)

### Понимание проблемы

Genres response: `{result: [Genre]}`.
`Genre` имеет поля: `id`, `name`, `title`, `value`, `coverUri`, `ogImage`, `subGenres: [Genre]`, ...
`subGenres` вложены рекурсивно (у genre "electronic" — 10+ subgenres, у каждого свои coverUri и т.д.)
Текущий `clean_response_body`: список в `result` → `_clean_object_list` → ни `_is_track_like`, ни `_is_playlist_like` не матчит → проходит без фильтрации.

### Step 1: Написать failing тест

Создать `tests/mcp/test_response_filters.py`:

```python
"""Tests for YM API response cleaners."""
from __future__ import annotations

from app.mcp.yandex_music.response_filters import clean_response_body

def _make_genre(name: str, with_sub: bool = False) -> dict:
    genre: dict = {
        "id": name,
        "name": name,
        "title": name.capitalize(),
        "value": name,
        "coverUri": "avatars.yandex.net/get-music-content/HUGE",
        "ogImage": "avatars.yandex.net/get-music-content/HUGE2",
        "fullImageUrl": "https://very-large-url.example.com",
    }
    if with_sub:
        genre["subGenres"] = [_make_genre(f"{name}-sub1"), _make_genre(f"{name}-sub2")]
    return genre

def test_clean_genres_strips_cover_uri():
    body = {
        "result": [_make_genre("techno", with_sub=True)],
        "invocationInfo": {"req-id": "x"},
    }
    cleaned = clean_response_body(body)
    assert "invocationInfo" not in cleaned
    genre = cleaned["result"][0]
    assert "coverUri" not in genre
    assert "ogImage" not in genre
    assert "fullImageUrl" not in genre
    assert genre["id"] == "techno"
    assert genre["name"] == "techno"

def test_clean_genres_cleans_subgenres():
    body = {"result": [_make_genre("techno", with_sub=True)]}
    cleaned = clean_response_body(body)
    genre = cleaned["result"][0]
    assert "subGenres" in genre
    sub = genre["subGenres"][0]
    assert "coverUri" not in sub
    assert sub["id"] == "techno-sub1"
```

### Step 2: Запустить falling тест

```bash
uv run pytest tests/mcp/test_response_filters.py -v
```

Ожидание: `FAILED — AssertionError: 'coverUri' не удалён`

### Step 3: Добавить genre cleaner в response_filters.py

В `app/mcp/yandex_music/response_filters.py`, добавить после `_ARTIST_FIELDS`:

```python
_GENRE_FIELDS: frozenset[str] = frozenset({"id", "name", "title", "value", "subGenres"})

def _is_genre_like(obj: Any) -> bool:
    """Heuristic: dict looks like a YM Genre (has id + subGenres or value field without durationMs)."""
    return (
        isinstance(obj, dict)
        and "id" in obj
        and "durationMs" not in obj
        and "uid" not in obj
        and ("subGenres" in obj or "value" in obj)
    )

def clean_genre(genre: dict[str, Any]) -> dict[str, Any]:
    """Keep only DJ-relevant fields from Genre, clean subGenres recursively."""
    cleaned = {k: v for k, v in genre.items() if k in _GENRE_FIELDS}
    if subs := cleaned.get("subGenres"):
        cleaned["subGenres"] = [
            clean_genre(s) for s in subs if isinstance(s, dict)
        ]
    return cleaned
```

В `_clean_object_list`, добавить ветку перед `else`:

```python
def _clean_object_list(items: list[Any]) -> list[Any]:
    """Clean all track-like, playlist-like, or genre-like objects in a list."""
    result = []
    for it in items:
        if _is_playlist_like(it):
            result.append(clean_playlist(it))
        elif _is_track_like(it):
            result.append(clean_track(it))
        elif _is_genre_like(it):
            result.append(clean_genre(it))
        else:
            result.append(it)
    return result
```

### Step 4: Запустить тест

```bash
uv run pytest tests/mcp/test_response_filters.py -v
```

Ожидание: PASS

### Step 5: Запустить все тесты MCP

```bash
uv run pytest tests/mcp/ -v
```

### Step 6: Commit

```bash
git add app/mcp/yandex_music/response_filters.py tests/mcp/test_response_filters.py
git commit -m "fix(mcp): clean YM genre responses (strip coverUri/ogImage/fullImageUrl)"
```

---

## Task 3: Убрать tracks из плейлистов при листинге (86k → ~5k)

**Files:**
- Modify: `app/mcp/yandex_music/response_filters.py`
- Modify: `tests/mcp/test_response_filters.py`

### Понимание проблемы

`ym_get_play_lists` → `result: [Playlist]`.
Каждый плейлист содержит `tracks: [{id, albumId, timestamp}]` — сотни записей.
При листинге плейлистов нам нужны только метаданные, не треки.
Треки можно получить через `ym_get_liked_tracks_ids` или `ym_get_playlist_by_id`.

### Step 1: Добавить тест

В `tests/mcp/test_response_filters.py`:

```python
def _make_playlist(kind: int, track_count: int = 5) -> dict:
    return {
        "uid": 250905515,
        "kind": kind,
        "title": f"Playlist {kind}",
        "trackCount": track_count,
        "durationMs": track_count * 300_000,
        "revision": 10,
        "visibility": "public",
        "tracks": [{"id": i, "albumId": i * 10, "timestamp": "2026-01-01"} for i in range(track_count)],
        "coverUri": "avatars.yandex.net/huge-cover",
        "ogImage": "og-image-url",
    }

def test_playlist_list_strips_tracks():
    """When result is a list of playlists, tracks should be removed (too large)."""
    body = {
        "result": [_make_playlist(1, 557), _make_playlist(2, 213)],
    }
    cleaned = clean_response_body(body)
    for pl in cleaned["result"]:
        assert "tracks" not in pl, "tracks should be stripped in list context"
        assert pl["trackCount"] == 557 or pl["trackCount"] == 213
        assert "coverUri" not in pl
```

### Step 2: Запустить falling тест

```bash
uv run pytest tests/mcp/test_response_filters.py::test_playlist_list_strips_tracks -v
```

Ожидание: FAILED

### Step 3: Обновить clean_playlist и _PLAYLIST_FIELDS

В `response_filters.py`, удалить `"tracks"` из `_PLAYLIST_FIELDS`:

```python
_PLAYLIST_FIELDS: frozenset[str] = frozenset(
    {
        "uid",
        "kind",
        "title",
        "description",
        "visibility",
        "trackCount",
        "durationMs",
        "revision",
        "owner",
        "tags",
        # "tracks" — NOT here: stripped in list context, added separately in single context
        "created",
        "modified",
        "playlistUuid",
    }
)
```

### Step 4: Запустить тест

```bash
uv run pytest tests/mcp/test_response_filters.py::test_playlist_list_strips_tracks -v
```

Ожидание: PASS

### Step 5: Проверить что single playlist тест тоже нужен

Добавить в `tests/mcp/test_response_filters.py`:

```python
def test_single_playlist_keeps_compact_tracks():
    """Single playlist (by ID) should keep tracks in compact form."""
    playlist = _make_playlist(3, 10)
    body = {"result": playlist}
    cleaned = clean_response_body(body)
    # Single playlist still filtered via _PLAYLIST_FIELDS — no tracks
    # This is acceptable: tracks are stripped, trackCount preserved
    assert cleaned["result"]["trackCount"] == 10
    assert "coverUri" not in cleaned["result"]
```

### Step 6: Запустить все тесты response_filters

```bash
uv run pytest tests/mcp/test_response_filters.py -v
```

Ожидание: все PASS

### Step 7: Запустить полный suite

```bash
uv run pytest tests/mcp/ -v
```

### Step 8: Commit

```bash
git add app/mcp/yandex_music/response_filters.py tests/mcp/test_response_filters.py
git commit -m "fix(mcp): strip tracks from playlist list responses to reduce context size"
```

---

## Task 4: Финальная проверка и lint

### Step 1: Lint + type check

```bash
uv run ruff check app/mcp/yandex_music/ && uv run mypy app/mcp/yandex_music/
```

Исправить все замечания.

### Step 2: Полный тест suite

```bash
uv run pytest tests/mcp/ -v
```

Ожидание: все PASS

### Step 3: Ручная проверка через make mcp-call

```bash
# Проверить что инструменты исключены
make mcp-list | grep -E "brief_info|lyrics"
# Должно быть пусто

# Проверить размер genres ответа
make mcp-call TOOL=ym__get_genres ARGS='{}'
# Должно быть < 20k символов
```

### Step 4: Обновить memory (mcp-testing-results)

Обновить `/Users/laptop/.claude/projects/-Users-laptop-dev-dj-techno-set-builder/memory/mcp-testing-results.md`:
- Добавить строку о том, что `get_artist_brief_info` и `get_track_lyrics` теперь исключены
- Отметить что genres и playlist responses теперь чистятся

### Step 5: Final commit

```bash
git add -A
git commit -m "fix(mcp): complete YM tools fixes — exclude broken endpoints, clean large responses"
```

---

## Ожидаемый результат

| Инструмент | До | После |
|-----------|-----|-------|
| `ym_get_artist_brief_info` | ❌ HTTP 403 | Удалён из MCP |
| `ym_get_track_lyrics` | ❌ HTTP 400 | Удалён из MCP |
| `ym_get_genres` | ⚠️ ~177k | ✅ ~5-10k |
| `ym_get_play_lists` | ⚠️ ~86k | ✅ ~5-10k |
| `ym_get_playlist_by_id` | ⚠️ ~154k | ✅ ~10-20k |

## Файлы, затронутые планом

| Файл | Изменение |
|------|-----------|
| `app/mcp/yandex_music/config.py` | +2 строки в EXCLUDE_ROUTE_MAPS |
| `app/mcp/yandex_music/response_filters.py` | +`_GENRE_FIELDS`, `_is_genre_like`, `clean_genre`; убрать `"tracks"` из `_PLAYLIST_FIELDS`; обновить `_clean_object_list` |
| `tests/mcp/test_yandex_music.py` | +`test_broken_endpoints_are_excluded` |
| `tests/mcp/test_response_filters.py` | Новый файл: genre + playlist тесты |
