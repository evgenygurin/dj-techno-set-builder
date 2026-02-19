# MCP Redesign Phase 3 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Построить multi-platform абстракцию (MusicPlatform protocol, PlatformRegistry, YandexMusicAdapter с ЗАПИСЬЮ), SyncEngine для двусторонней синхронизации, DbTrackMapper для маппинга local↔platform IDs — заменить 3 sync стаба рабочими реализациями.

**Architecture:** Port/Adapter паттерн: `MusicPlatform` Protocol определяет общий интерфейс, platform-specific адаптеры оборачивают реальные API-клиенты. `PlatformRegistry` управляет lifecycle адаптеров. `SyncEngine` считает diff между local и remote плейлистами и применяет изменения. Безопасный по умолчанию: НЕ удаляет remote треки при неполном маппинге.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest + pytest-asyncio

**Phase 0+1 delivers:** `schemas.py`, `refs.py`, `resolvers.py`, `converters.py`, `pagination.py`, `stats.py`, `platforms/keys.py` (PlatformKey enum)
**Phase 2 delivers:** `envelope.py`, `tools/tracks.py`, `tools/playlists.py`, `tools/sets.py`, `tools/server.py`

**Критичное из ревью (все 10 блокеров учтены):**
1. PlatformKey из Phase 0 решает `ym` vs `yandex_music` (blocker #1) ✅
2. Platform IDs — raw строки БЕЗ префиксов (blocker #2) ✅
3. Playlist ID = `kind` only, adapter привязан к user (blocker #3) ✅
4. Adapter РЕАЛИЗУЕТ запись (create/add/remove playlist) (blocker #4) ✅
5. SyncEngine safe-by-default: НЕ удаляет при mapping < 100% (blocker #5) ✅
6. server_default через `text("'local'")` (blocker #6) ✅
7. MCP sync tools используют refs + envelope (blocker #7) ✅
8. Registry lifecycle через gateway lifespan (blocker #8) ✅
9. Visibility на уровне gateway (blocker #9) — Phase 4 scope ✅
10. Tests через public API `list_tools()` (blocker #10) ✅

---

## Task 1: MusicPlatform Protocol + data models

**Files:**
- Create: `app/mcp/platforms/protocol.py`
- Modify: `app/mcp/platforms/__init__.py`
- Test: `tests/mcp/platforms/test_protocol.py`

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/__init__.py
```

```python
# tests/mcp/platforms/test_protocol.py
"""Tests for MusicPlatform protocol and platform data models."""

from __future__ import annotations

from dataclasses import dataclass

from app.mcp.platforms.protocol import (
    MusicPlatform,
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)

class TestPlatformTrack:
    def test_create(self):
        t = PlatformTrack(
            platform_id="12345",
            title="Gravity",
            artists="Boris Brejcha",
            duration_ms=360000,
        )
        assert t.platform_id == "12345"  # raw ID, no prefix
        assert t.duration_ms == 360000

    def test_optional_fields(self):
        t = PlatformTrack(
            platform_id="12345",
            title="Gravity",
            artists="Boris Brejcha",
        )
        assert t.duration_ms is None
        assert t.cover_uri is None

class TestPlatformPlaylist:
    def test_create(self):
        p = PlatformPlaylist(
            platform_id="1003",  # kind only, no uid prefix
            name="My Techno",
            track_ids=["111", "222", "333"],
            owner_id="250905515",
        )
        assert len(p.track_ids) == 3
        assert p.platform_id == "1003"

class TestPlatformCapability:
    def test_values(self):
        assert PlatformCapability.SEARCH in PlatformCapability
        assert PlatformCapability.DOWNLOAD in PlatformCapability
        assert PlatformCapability.PLAYLIST_WRITE in PlatformCapability

class TestProtocolCompliance:
    def test_dummy_adapter_satisfies_protocol(self):
        @dataclass
        class DummyAdapter:
            name: str = "dummy"
            capabilities: frozenset[PlatformCapability] = frozenset(
                {PlatformCapability.SEARCH}
            )

            async def search_tracks(self, query: str, *, limit: int = 20) -> list[PlatformTrack]:
                return []

            async def get_track(self, platform_id: str) -> PlatformTrack:
                return PlatformTrack(platform_id=platform_id, title="t", artists="a")

            async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
                return PlatformPlaylist(platform_id=platform_id, name="p", track_ids=[])

            async def create_playlist(self, name: str, track_ids: list[str]) -> str:
                return "new_id"

            async def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
                pass

            async def remove_tracks_from_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
                pass

            async def close(self) -> None:
                pass

        adapter = DummyAdapter()
        platform: MusicPlatform = adapter
        assert platform.name == "dummy"
        assert PlatformCapability.SEARCH in platform.capabilities
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/mcp/platforms/test_protocol.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement**

```python
# app/mcp/platforms/protocol.py
"""MusicPlatform protocol — common interface for all music platform adapters."""

from __future__ import annotations

from enum import Enum, auto
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

class PlatformCapability(Enum):
    """Capabilities a platform adapter may support."""

    SEARCH = auto()
    DOWNLOAD = auto()
    PLAYLIST_READ = auto()
    PLAYLIST_WRITE = auto()
    LIKES = auto()

class PlatformTrack(BaseModel):
    """Minimal track representation from a platform.

    platform_id is a RAW provider ID (e.g. '12345'), no URN prefix.
    """

    platform_id: str
    title: str
    artists: str
    duration_ms: int | None = None
    cover_uri: str | None = None
    album_title: str | None = None
    genre: str | None = None

class PlatformPlaylist(BaseModel):
    """Minimal playlist representation from a platform.

    platform_id format is platform-specific:
    - YM: 'kind' string (e.g. '1003'), adapter is bound to user_id
    - Spotify: full playlist ID
    """

    platform_id: str
    name: str
    track_ids: list[str]
    owner_id: str | None = None
    track_count: int | None = None

@runtime_checkable
class MusicPlatform(Protocol):
    """Common interface for all music platform adapters."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[PlatformCapability]: ...

    async def search_tracks(
        self, query: str, *, limit: int = 20
    ) -> list[PlatformTrack]: ...

    async def get_track(self, platform_id: str) -> PlatformTrack: ...

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist: ...

    # --- Write operations (blocker #4: MUST implement, not stub) ---

    async def create_playlist(
        self, name: str, track_ids: list[str]
    ) -> str: ...

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None: ...

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None: ...

    async def close(self) -> None: ...
```

```python
# app/mcp/platforms/__init__.py
"""Multi-platform abstraction layer."""

from app.mcp.platforms.keys import PlatformKey
from app.mcp.platforms.protocol import (
    MusicPlatform,
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)

__all__ = [
    "MusicPlatform",
    "PlatformCapability",
    "PlatformKey",
    "PlatformPlaylist",
    "PlatformTrack",
]
```

**Step 4: Run tests**

```bash
uv run pytest tests/mcp/platforms/test_protocol.py -v
```

**Step 5: Lint + commit**

```bash
git add app/mcp/platforms/protocol.py app/mcp/platforms/__init__.py \
       tests/mcp/platforms/__init__.py tests/mcp/platforms/test_protocol.py
git commit -m "feat(mcp): add MusicPlatform protocol + platform data models

PlatformTrack/PlatformPlaylist use raw IDs (no URN prefix).
Protocol includes playlist write operations (not stubs)."
```

---

## Task 2: PlatformRegistry

**Files:**
- Create: `app/mcp/platforms/registry.py`
- Test: `tests/mcp/platforms/test_registry.py`

Управляет lifecycle адаптеров. Provides lookup by platform key, close_all для shutdown.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_registry.py
"""Tests for PlatformRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from app.mcp.platforms.protocol import PlatformCapability, PlatformPlaylist, PlatformTrack
from app.mcp.platforms.registry import PlatformRegistry

@dataclass
class FakeAdapter:
    name: str = "fake"
    capabilities: frozenset[PlatformCapability] = frozenset({PlatformCapability.SEARCH})
    closed: bool = field(default=False, init=False)

    async def search_tracks(self, query, *, limit=20):
        return []

    async def get_track(self, platform_id):
        return PlatformTrack(platform_id=platform_id, title="t", artists="a")

    async def get_playlist(self, platform_id):
        return PlatformPlaylist(platform_id=platform_id, name="p", track_ids=[])

    async def create_playlist(self, name, track_ids):
        return "new"

    async def add_tracks_to_playlist(self, playlist_id, track_ids):
        pass

    async def remove_tracks_from_playlist(self, playlist_id, track_ids):
        pass

    async def close(self):
        self.closed = True

class TestPlatformRegistry:
    def test_register_and_get(self):
        registry = PlatformRegistry()
        adapter = FakeAdapter(name="ym")
        registry.register(adapter)
        assert registry.get("ym") is adapter

    def test_get_unknown_raises(self):
        registry = PlatformRegistry()
        with pytest.raises(KeyError, match="ym"):
            registry.get("ym")

    def test_list_platforms(self):
        registry = PlatformRegistry()
        registry.register(FakeAdapter(name="ym"))
        registry.register(FakeAdapter(name="spotify"))
        assert sorted(registry.list_platforms()) == ["spotify", "ym"]

    async def test_close_all(self):
        registry = PlatformRegistry()
        a1 = FakeAdapter(name="ym")
        a2 = FakeAdapter(name="spotify")
        registry.register(a1)
        registry.register(a2)

        await registry.close_all()

        assert a1.closed is True
        assert a2.closed is True

    def test_register_duplicate_raises(self):
        registry = PlatformRegistry()
        registry.register(FakeAdapter(name="ym"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(FakeAdapter(name="ym"))
```

**Step 2: Run test**

```bash
uv run pytest tests/mcp/platforms/test_registry.py -v
```

**Step 3: Implement**

```python
# app/mcp/platforms/registry.py
"""PlatformRegistry — manages adapter instances and lifecycle."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.mcp.platforms.protocol import MusicPlatform

logger = logging.getLogger(__name__)

class PlatformRegistry:
    """Registry for music platform adapters.

    Provides lookup by name, lists connected platforms,
    and handles lifecycle (close_all on shutdown).
    """

    def __init__(self) -> None:
        self._adapters: dict[str, MusicPlatform] = {}

    def register(self, adapter: MusicPlatform) -> None:
        """Register a platform adapter."""
        if adapter.name in self._adapters:
            msg = f"Platform '{adapter.name}' already registered"
            raise ValueError(msg)
        self._adapters[adapter.name] = adapter
        logger.info("Registered platform adapter: %s", adapter.name)

    def get(self, name: str) -> MusicPlatform:
        """Get adapter by platform name. Raises KeyError if not found."""
        if name not in self._adapters:
            raise KeyError(name)
        return self._adapters[name]

    def list_platforms(self) -> list[str]:
        """List all registered platform names."""
        return list(self._adapters.keys())

    async def close_all(self) -> None:
        """Close all adapters. Called on shutdown."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.close()
                logger.info("Closed adapter: %s", name)
            except Exception:
                logger.exception("Failed to close adapter: %s", name)
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/platforms/test_registry.py -v
uv run ruff check app/mcp/platforms/registry.py tests/mcp/platforms/test_registry.py
```

```bash
git add app/mcp/platforms/registry.py tests/mcp/platforms/test_registry.py
git commit -m "feat(mcp): add PlatformRegistry with lifecycle management

close_all() shuts down all adapters on MCP server shutdown."
```

---

## Task 3: YandexMusicAdapter (reads + writes)

**Files:**
- Create: `app/mcp/yandex_music/adapter.py`
- Test: `tests/mcp/yandex_music/test_adapter.py`

Критичное: адаптер РЕАЛИЗУЕТ playlist writes (create, add_tracks, remove_tracks) через YandexMusicClient. Не стаб.

**Step 1: Write the failing tests**

```python
# tests/mcp/yandex_music/__init__.py
```

```python
# tests/mcp/yandex_music/test_adapter.py
"""Tests for YandexMusicAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.platforms.protocol import PlatformCapability
from app.mcp.yandex_music.adapter import YandexMusicAdapter

@pytest.fixture
def mock_ym_client():
    client = AsyncMock()
    client.search_tracks.return_value = [
        {
            "id": "12345",
            "title": "Gravity",
            "artists": [{"name": "Boris Brejcha"}],
            "durationMs": 360000,
        }
    ]
    client.fetch_playlist_tracks.return_value = [
        {"id": "111", "title": "A", "artists": [{"name": "X"}]},
        {"id": "222", "title": "B", "artists": [{"name": "Y"}]},
    ]
    return client

@pytest.fixture
def adapter(mock_ym_client):
    return YandexMusicAdapter(client=mock_ym_client, user_id="250905515")

class TestAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "ym"

    def test_capabilities(self, adapter):
        caps = adapter.capabilities
        assert PlatformCapability.SEARCH in caps
        assert PlatformCapability.PLAYLIST_READ in caps
        assert PlatformCapability.PLAYLIST_WRITE in caps
        assert PlatformCapability.DOWNLOAD in caps

class TestSearch:
    async def test_search_tracks(self, adapter, mock_ym_client):
        results = await adapter.search_tracks("Gravity", limit=10)
        assert len(results) == 1
        assert results[0].platform_id == "12345"  # raw ID, no prefix
        assert results[0].title == "Gravity"
        mock_ym_client.search_tracks.assert_called_once_with("Gravity")

class TestPlaylistRead:
    async def test_get_playlist(self, adapter, mock_ym_client):
        playlist = await adapter.get_playlist("1003")  # kind only
        assert playlist.platform_id == "1003"
        assert len(playlist.track_ids) == 2
        assert playlist.track_ids == ["111", "222"]
        mock_ym_client.fetch_playlist_tracks.assert_called_once_with(
            "250905515", "1003"
        )

class TestPlaylistWrite:
    async def test_create_playlist(self, adapter, mock_ym_client):
        mock_ym_client.create_playlist = AsyncMock(return_value={"kind": 2001})
        result = await adapter.create_playlist("New Set", ["111", "222"])
        assert result == "2001"  # string kind

    async def test_add_tracks(self, adapter, mock_ym_client):
        mock_ym_client.change_playlist_tracks = AsyncMock()
        await adapter.add_tracks_to_playlist("1003", ["333", "444"])
        mock_ym_client.change_playlist_tracks.assert_called_once()

    async def test_remove_tracks(self, adapter, mock_ym_client):
        mock_ym_client.change_playlist_tracks = AsyncMock()
        await adapter.remove_tracks_from_playlist("1003", ["111"])
        mock_ym_client.change_playlist_tracks.assert_called_once()

class TestClose:
    async def test_close_delegates(self, adapter, mock_ym_client):
        await adapter.close()
        mock_ym_client.close.assert_called_once()
```

**Step 2: Run test**

```bash
uv run pytest tests/mcp/yandex_music/test_adapter.py -v
```

**Step 3: Implement**

```python
# app/mcp/yandex_music/adapter.py
"""YandexMusicAdapter — MusicPlatform implementation for Yandex Music.

Wraps YandexMusicClient with the common MusicPlatform interface.
Implements BOTH reads AND writes (not stubs).

Platform IDs are RAW strings (e.g. '12345'), no URN prefix.
Playlist IDs are 'kind' strings, adapter is bound to a user_id.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.mcp.platforms.protocol import (
    MusicPlatform,
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)

if TYPE_CHECKING:
    from app.services.yandex_music_client import YandexMusicClient

logger = logging.getLogger(__name__)

class YandexMusicAdapter:
    """Yandex Music platform adapter.

    Implements MusicPlatform protocol with full read + write support.
    """

    def __init__(self, client: YandexMusicClient, user_id: str) -> None:
        self._client = client
        self._user_id = user_id

    @property
    def name(self) -> str:
        return "ym"

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        return frozenset({
            PlatformCapability.SEARCH,
            PlatformCapability.DOWNLOAD,
            PlatformCapability.PLAYLIST_READ,
            PlatformCapability.PLAYLIST_WRITE,
        })

    # --- Read operations ---

    async def search_tracks(
        self, query: str, *, limit: int = 20
    ) -> list[PlatformTrack]:
        raw_results = await self._client.search_tracks(query)
        tracks = []
        for raw in raw_results[:limit]:
            artists = ", ".join(
                a.get("name", "") for a in raw.get("artists", [])
            )
            tracks.append(
                PlatformTrack(
                    platform_id=str(raw["id"]),
                    title=raw.get("title", ""),
                    artists=artists,
                    duration_ms=raw.get("durationMs"),
                    cover_uri=raw.get("coverUri"),
                )
            )
        return tracks

    async def get_track(self, platform_id: str) -> PlatformTrack:
        results = await self._client.fetch_tracks_metadata([platform_id])
        if not results:
            msg = f"Track {platform_id} not found on Yandex Music"
            raise ValueError(msg)
        raw = results[0]
        artists = ", ".join(a.get("name", "") for a in raw.get("artists", []))
        return PlatformTrack(
            platform_id=str(raw["id"]),
            title=raw.get("title", ""),
            artists=artists,
            duration_ms=raw.get("durationMs"),
        )

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        """Get playlist by kind (platform_id = kind string)."""
        tracks = await self._client.fetch_playlist_tracks(
            self._user_id, platform_id
        )
        track_ids = [str(t["id"]) for t in tracks]
        return PlatformPlaylist(
            platform_id=platform_id,
            name="",  # YM API returns tracks, not playlist name
            track_ids=track_ids,
            owner_id=self._user_id,
        )

    # --- Write operations (blocker #4: implemented, not stubs) ---

    async def create_playlist(
        self, name: str, track_ids: list[str]
    ) -> str:
        """Create a new YM playlist and return its kind as string."""
        result = await self._client.create_playlist(name)
        kind = str(result.get("kind", ""))
        if track_ids:
            await self.add_tracks_to_playlist(kind, track_ids)
        return kind

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        """Add tracks to a YM playlist using diff format."""
        # YM API uses diff-based track changes
        # Each track needs an insert operation
        diff = [
            {"op": "insert", "at": 0, "tracks": [{"id": tid, "albumId": "0"} for tid in track_ids]}
        ]
        await self._client.change_playlist_tracks(
            self._user_id, playlist_id, diff=diff
        )

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        """Remove tracks from a YM playlist using diff format.

        Fetches current playlist to find track indices, then removes.
        Re-fetches every ~10 deletions to keep indices fresh (YM gotcha).
        """
        to_remove = set(track_ids)
        removed = 0

        while to_remove:
            # Re-fetch playlist to get fresh indices
            current = await self.get_playlist(playlist_id)
            diff = []

            for idx, tid in enumerate(current.track_ids):
                if tid in to_remove:
                    diff.append({
                        "op": "delete",
                        "from": idx,
                        "to": idx + 1,
                    })
                    to_remove.discard(tid)
                    removed += 1

                    # Re-fetch every 10 deletions (YM 412 gotcha)
                    if removed % 10 == 0:
                        break

            if diff:
                await self._client.change_playlist_tracks(
                    self._user_id, playlist_id, diff=diff
                )
            else:
                # No more tracks found — remaining are undeletable
                if to_remove:
                    logger.warning(
                        "Could not remove %d tracks from playlist %s: %s",
                        len(to_remove), playlist_id, to_remove,
                    )
                break

    async def close(self) -> None:
        await self._client.close()
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/yandex_music/test_adapter.py -v
uv run ruff check app/mcp/yandex_music/adapter.py
```

```bash
git add app/mcp/yandex_music/adapter.py \
       tests/mcp/yandex_music/__init__.py tests/mcp/yandex_music/test_adapter.py
git commit -m "feat(mcp): add YandexMusicAdapter with full read + write support

Implements MusicPlatform protocol. Playlist writes use diff format.
remove_tracks re-fetches every 10 deletions (YM 412 gotcha)."
```

---

## Task 4: DbTrackMapper (local ↔ platform IDs)

**Files:**
- Create: `app/mcp/platforms/track_mapper.py`
- Test: `tests/mcp/platforms/test_track_mapper.py`

Маппит между local track_id и platform-specific IDs через таблицу `provider_track_ids`. Использует PlatformKey → provider_code для DB-запросов.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_track_mapper.py
"""Tests for DbTrackMapper."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.models.tracks import Track

class TestDbTrackMapper:
    async def test_get_platform_ids(self, session: AsyncSession):
        from app.mcp.platforms.track_mapper import DbTrackMapper

        # Seed data
        provider = Provider(provider_id=1, provider_code="yandex_music", name="YM")
        session.add(provider)
        track = Track(title="Test", title_sort="test", duration_ms=180000, status=0)
        session.add(track)
        await session.flush()

        mapping = ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider.provider_id,
            provider_track_id="12345",
        )
        session.add(mapping)
        await session.flush()

        mapper = DbTrackMapper(session)
        result = await mapper.get_platform_ids("ym", [track.track_id])

        assert result == {track.track_id: "12345"}

    async def test_get_local_ids(self, session: AsyncSession):
        from app.mcp.platforms.track_mapper import DbTrackMapper

        provider = Provider(provider_id=1, provider_code="yandex_music", name="YM")
        session.add(provider)
        track = Track(title="Test", title_sort="test", duration_ms=180000, status=0)
        session.add(track)
        await session.flush()

        mapping = ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider.provider_id,
            provider_track_id="12345",
        )
        session.add(mapping)
        await session.flush()

        mapper = DbTrackMapper(session)
        result = await mapper.get_local_ids("ym", ["12345"])

        assert result == {"12345": track.track_id}

    async def test_unmapped_returns_empty(self, session: AsyncSession):
        from app.mcp.platforms.track_mapper import DbTrackMapper

        mapper = DbTrackMapper(session)
        result = await mapper.get_platform_ids("ym", [99999])
        assert result == {}

    async def test_mapping_coverage(self, session: AsyncSession):
        from app.mcp.platforms.track_mapper import DbTrackMapper

        provider = Provider(provider_id=1, provider_code="yandex_music", name="YM")
        session.add(provider)
        t1 = Track(title="A", title_sort="a", duration_ms=180000, status=0)
        t2 = Track(title="B", title_sort="b", duration_ms=180000, status=0)
        session.add_all([t1, t2])
        await session.flush()

        # Only t1 has mapping
        session.add(ProviderTrackId(
            track_id=t1.track_id, provider_id=1, provider_track_id="111"
        ))
        await session.flush()

        mapper = DbTrackMapper(session)
        coverage = await mapper.mapping_coverage("ym", [t1.track_id, t2.track_id])
        assert coverage == 0.5  # 1 of 2 mapped
```

**Step 2: Run test**

```bash
uv run pytest tests/mcp/platforms/test_track_mapper.py -v
```

**Step 3: Implement**

```python
# app/mcp/platforms/track_mapper.py
"""DbTrackMapper — maps between local track_ids and platform IDs.

Uses PlatformKey → provider_code mapping from Phase 0.
Platform IDs are RAW strings (no URN prefix) matching provider_track_ids.provider_track_id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.mcp.platforms.keys import PlatformKey
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

class DbTrackMapper:
    """Maps between local track_id and platform-specific IDs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._provider_cache: dict[str, int] = {}

    async def _get_provider_id(self, platform_key: str) -> int | None:
        """Resolve platform key ('ym') → provider_id via PlatformKey enum."""
        if platform_key in self._provider_cache:
            return self._provider_cache[platform_key]

        pk = PlatformKey(platform_key)
        provider_code = pk.provider_code

        query = select(Provider.provider_id).where(
            Provider.provider_code == provider_code
        )
        result = await self._session.execute(query)
        provider_id = result.scalar_one_or_none()

        if provider_id is not None:
            self._provider_cache[platform_key] = provider_id
        return provider_id

    async def get_platform_ids(
        self, platform_key: str, track_ids: list[int]
    ) -> dict[int, str]:
        """Map local track_ids → platform IDs.

        Returns: {track_id: platform_track_id} for mapped tracks only.
        """
        provider_id = await self._get_provider_id(platform_key)
        if provider_id is None or not track_ids:
            return {}

        query = select(ProviderTrackId).where(
            ProviderTrackId.provider_id == provider_id,
            ProviderTrackId.track_id.in_(track_ids),
        )
        result = (await self._session.execute(query)).scalars().all()
        return {m.track_id: m.provider_track_id for m in result}

    async def get_local_ids(
        self, platform_key: str, platform_ids: list[str]
    ) -> dict[str, int]:
        """Map platform IDs → local track_ids.

        Returns: {platform_track_id: track_id} for mapped tracks only.
        """
        provider_id = await self._get_provider_id(platform_key)
        if provider_id is None or not platform_ids:
            return {}

        query = select(ProviderTrackId).where(
            ProviderTrackId.provider_id == provider_id,
            ProviderTrackId.provider_track_id.in_(platform_ids),
        )
        result = (await self._session.execute(query)).scalars().all()
        return {m.provider_track_id: m.track_id for m in result}

    async def mapping_coverage(
        self, platform_key: str, track_ids: list[int]
    ) -> float:
        """Fraction of track_ids that have a platform mapping. 0.0-1.0."""
        if not track_ids:
            return 1.0
        mapped = await self.get_platform_ids(platform_key, track_ids)
        return len(mapped) / len(track_ids)
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/platforms/test_track_mapper.py -v
uv run ruff check app/mcp/platforms/track_mapper.py
```

```bash
git add app/mcp/platforms/track_mapper.py tests/mcp/platforms/test_track_mapper.py
git commit -m "feat(mcp): add DbTrackMapper (local ↔ platform ID mapping)

Uses PlatformKey→provider_code resolution.
mapping_coverage() for sync safety checks."
```

---

## Task 5: SyncEngine — diff + apply

**Files:**
- Create: `app/mcp/platforms/sync_engine.py`
- Test: `tests/mcp/platforms/test_sync_engine.py`

SyncEngine считает diff между local и remote плейлистами и применяет изменения. **Safe-by-default**: НЕ удаляет remote треки при mapping coverage < 100% (blocker #5).

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_sync_engine.py
"""Tests for SyncEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.mcp.platforms.sync_engine import SyncDirection, SyncEngine, SyncResult

@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.name = "ym"
    return adapter

@pytest.fixture
def mock_mapper():
    mapper = AsyncMock()
    return mapper

class TestSyncDiff:
    async def test_local_to_remote_adds(self, mock_adapter, mock_mapper):
        """Tracks in local but not remote should be added."""
        # Local has tracks [1, 2, 3], remote has [111]
        mock_mapper.get_platform_ids.return_value = {1: "111", 2: "222", 3: "333"}
        mock_mapper.mapping_coverage.return_value = 1.0
        mock_adapter.get_playlist.return_value = AsyncMock(track_ids=["111"])

        engine = SyncEngine(mock_adapter, mock_mapper)
        result = await engine.sync(
            playlist_platform_id="1003",
            local_track_ids=[1, 2, 3],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert result.added_to_remote == 2  # 222 and 333
        mock_adapter.add_tracks_to_playlist.assert_called_once()

    async def test_local_to_remote_safe_no_delete(self, mock_adapter, mock_mapper):
        """Should NOT delete remote tracks by default."""
        mock_mapper.get_platform_ids.return_value = {1: "111"}
        mock_mapper.mapping_coverage.return_value = 1.0
        mock_adapter.get_playlist.return_value = AsyncMock(
            track_ids=["111", "999"]  # 999 not in local
        )

        engine = SyncEngine(mock_adapter, mock_mapper)
        result = await engine.sync(
            playlist_platform_id="1003",
            local_track_ids=[1],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert result.removed_from_remote == 0  # safe default
        mock_adapter.remove_tracks_from_playlist.assert_not_called()

    async def test_local_to_remote_prune_enabled(self, mock_adapter, mock_mapper):
        """With prune=True, should remove remote tracks not in local."""
        mock_mapper.get_platform_ids.return_value = {1: "111"}
        mock_mapper.mapping_coverage.return_value = 1.0
        mock_adapter.get_playlist.return_value = AsyncMock(
            track_ids=["111", "999"]
        )

        engine = SyncEngine(mock_adapter, mock_mapper)
        result = await engine.sync(
            playlist_platform_id="1003",
            local_track_ids=[1],
            direction=SyncDirection.LOCAL_TO_REMOTE,
            prune=True,
        )

        assert result.removed_from_remote == 1
        mock_adapter.remove_tracks_from_playlist.assert_called_once()

    async def test_incomplete_mapping_blocks_prune(self, mock_adapter, mock_mapper):
        """Prune should be blocked when mapping coverage < 100%."""
        mock_mapper.get_platform_ids.return_value = {1: "111"}  # only 1 of 2
        mock_mapper.mapping_coverage.return_value = 0.5
        mock_adapter.get_playlist.return_value = AsyncMock(
            track_ids=["111", "999"]
        )

        engine = SyncEngine(mock_adapter, mock_mapper)
        result = await engine.sync(
            playlist_platform_id="1003",
            local_track_ids=[1, 2],  # 2 has no mapping
            direction=SyncDirection.LOCAL_TO_REMOTE,
            prune=True,  # should be overridden
        )

        assert result.removed_from_remote == 0
        assert "coverage" in result.warnings[0].lower()

    async def test_remote_to_local(self, mock_adapter, mock_mapper):
        """Remote tracks not in local should be reported for import."""
        mock_mapper.get_local_ids.return_value = {"111": 1}  # only 111 mapped
        mock_adapter.get_playlist.return_value = AsyncMock(
            track_ids=["111", "999"]
        )

        engine = SyncEngine(mock_adapter, mock_mapper)
        result = await engine.sync(
            playlist_platform_id="1003",
            local_track_ids=[1],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )

        assert result.new_remote_tracks == ["999"]
```

**Step 2: Run test**

```bash
uv run pytest tests/mcp/platforms/test_sync_engine.py -v
```

**Step 3: Implement**

```python
# app/mcp/platforms/sync_engine.py
"""SyncEngine — bidirectional playlist sync between local and platform.

SAFE BY DEFAULT: does NOT remove remote tracks when mapping is incomplete.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.mcp.platforms.protocol import MusicPlatform
    from app.mcp.platforms.track_mapper import DbTrackMapper

logger = logging.getLogger(__name__)

class SyncDirection(Enum):
    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"
    BIDIRECTIONAL = "bidirectional"

class SyncResult(BaseModel):
    """Result of a sync operation."""

    direction: str
    added_to_remote: int = 0
    removed_from_remote: int = 0
    new_remote_tracks: list[str] = Field(default_factory=list)
    mapping_coverage: float = 0.0
    warnings: list[str] = Field(default_factory=list)

class SyncEngine:
    """Diffs local vs remote playlists and applies changes."""

    def __init__(
        self,
        adapter: MusicPlatform,
        mapper: DbTrackMapper,
    ) -> None:
        self._adapter = adapter
        self._mapper = mapper

    async def sync(
        self,
        *,
        playlist_platform_id: str,
        local_track_ids: list[int],
        direction: SyncDirection,
        prune: bool = False,
    ) -> SyncResult:
        """Sync a playlist between local DB and remote platform.

        Args:
            playlist_platform_id: Platform playlist ID (e.g. '1003' for YM kind)
            local_track_ids: Local track IDs in the playlist
            direction: Sync direction
            prune: If True, remove remote tracks not in local (requires 100% mapping)
        """
        result = SyncResult(direction=direction.value)

        # Get remote state
        remote_playlist = await self._adapter.get_playlist(playlist_platform_id)
        remote_ids = set(remote_playlist.track_ids)

        if direction in (SyncDirection.LOCAL_TO_REMOTE, SyncDirection.BIDIRECTIONAL):
            await self._sync_local_to_remote(
                playlist_platform_id,
                local_track_ids,
                remote_ids,
                prune,
                result,
            )

        if direction in (SyncDirection.REMOTE_TO_LOCAL, SyncDirection.BIDIRECTIONAL):
            await self._sync_remote_to_local(
                local_track_ids,
                remote_ids,
                result,
            )

        return result

    async def _sync_local_to_remote(
        self,
        playlist_id: str,
        local_track_ids: list[int],
        remote_ids: set[str],
        prune: bool,
        result: SyncResult,
    ) -> None:
        """Push local → remote: add missing tracks, optionally remove extras."""
        platform_key = self._adapter.name

        # Map local → platform IDs
        mapped = await self._mapper.get_platform_ids(platform_key, local_track_ids)
        coverage = await self._mapper.mapping_coverage(platform_key, local_track_ids)
        result.mapping_coverage = coverage

        local_platform_ids = set(mapped.values())

        # Add tracks that are in local but not remote
        to_add = local_platform_ids - remote_ids
        if to_add:
            await self._adapter.add_tracks_to_playlist(
                playlist_id, list(to_add)
            )
            result.added_to_remote = len(to_add)

        # Remove tracks that are in remote but not local
        to_remove = remote_ids - local_platform_ids
        if to_remove and prune:
            # Safety check: block prune if mapping is incomplete (blocker #5)
            if coverage < 1.0:
                result.warnings.append(
                    f"Prune blocked: mapping coverage is {coverage:.0%}. "
                    f"Would have removed {len(to_remove)} tracks."
                )
                logger.warning(
                    "Prune blocked: coverage %.0f%% for %s",
                    coverage * 100, playlist_id,
                )
            else:
                await self._adapter.remove_tracks_from_playlist(
                    playlist_id, list(to_remove)
                )
                result.removed_from_remote = len(to_remove)
        elif to_remove and not prune:
            result.warnings.append(
                f"{len(to_remove)} remote tracks not in local (prune=False, kept)."
            )

    async def _sync_remote_to_local(
        self,
        local_track_ids: list[int],
        remote_ids: set[str],
        result: SyncResult,
    ) -> None:
        """Pull remote → local: report new tracks for import."""
        platform_key = self._adapter.name
        local_mapped = await self._mapper.get_local_ids(
            platform_key, list(remote_ids)
        )

        local_mapped_ids = set(local_mapped.values())
        unmapped_remote = [
            rid for rid in remote_ids if rid not in local_mapped
        ]

        result.new_remote_tracks = unmapped_remote
```

**Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/platforms/test_sync_engine.py -v
uv run ruff check app/mcp/platforms/sync_engine.py
```

```bash
git add app/mcp/platforms/sync_engine.py tests/mcp/platforms/test_sync_engine.py
git commit -m "feat(mcp): add SyncEngine with safe-by-default behavior

prune=True removes remote extras only when mapping coverage == 100%.
Supports local→remote, remote→local, bidirectional sync."
```

---

## Task 6: DjPlaylist sync columns (migration)

**Files:**
- Modify: `app/models/dj.py` — add source_of_truth, platform_ids columns to DjPlaylist
- Create: Alembic migration
- Test: `tests/models/test_dj_sync_columns.py`

**Step 1: Write the failing test**

```python
# tests/models/test_dj_sync_columns.py
"""Test sync columns on DjPlaylist."""

from __future__ import annotations

from app.models.dj import DjPlaylist

class TestDjPlaylistSyncColumns:
    async def test_source_of_truth_default(self, session):
        playlist = DjPlaylist(name="Test")
        session.add(playlist)
        await session.flush()
        await session.refresh(playlist)

        assert playlist.source_of_truth == "local"

    async def test_platform_ids_default(self, session):
        playlist = DjPlaylist(name="Test")
        session.add(playlist)
        await session.flush()
        await session.refresh(playlist)

        assert playlist.platform_ids == {}

    async def test_platform_ids_set(self, session):
        playlist = DjPlaylist(name="Test", platform_ids={"ym": "1003"})
        session.add(playlist)
        await session.flush()
        await session.refresh(playlist)

        assert playlist.platform_ids == {"ym": "1003"}
```

**Step 2: Run test**

```bash
uv run pytest tests/models/test_dj_sync_columns.py -v
```

**Step 3: Add columns to DjPlaylist model**

В `app/models/dj.py`, добавить к `DjPlaylist`:

```python
from sqlalchemy import JSON, String, text

class DjPlaylist(Base):
    # ... existing columns ...

    source_of_truth: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'local'"),  # blocker #6: use text() for string defaults
        nullable=False,
    )
    platform_ids: Mapped[dict] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        nullable=False,
    )
```

**Step 4: Create migration**

```bash
uv run alembic revision --autogenerate -m "add sync columns to dj_playlists"
uv run alembic upgrade head
```

**Step 5: Run tests + commit**

```bash
uv run pytest tests/models/test_dj_sync_columns.py -v
```

```bash
git add app/models/dj.py alembic/versions/*.py tests/models/test_dj_sync_columns.py
git commit -m "feat(models): add source_of_truth + platform_ids to DjPlaylist

source_of_truth defaults to 'local' (using text() for SQL string default).
platform_ids is JSON dict mapping platform_key → playlist_id."
```

---

## Task 7: MCP sync tools with refs + envelope

**Files:**
- Create: `app/mcp/tools/sync.py` — sync_playlist, link_playlist, set_source_of_truth
- Test: `tests/mcp/tools/test_sync.py`

Заменяет 3 sync стаба рабочими реализациями. Используют refs + envelope (blocker #7).

**Step 1: Write the failing tests**

```python
# tests/mcp/tools/test_sync.py
"""Tests for sync tools."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

class TestLinkPlaylist:
    async def test_link_playlist_to_platform(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            playlists = await client.call_tool("list_playlists", {})
            ref = playlists.data.results[0].ref

            result = await client.call_tool("link_playlist", {
                "playlist_ref": ref,
                "platform": "ym",
                "platform_playlist_id": "1003",
            })

        assert result.data.success is True

class TestSetSourceOfTruth:
    async def test_set_source(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            playlists = await client.call_tool("list_playlists", {})
            ref = playlists.data.results[0].ref

            result = await client.call_tool("set_source_of_truth", {
                "playlist_ref": ref,
                "source": "local",
            })

        assert result.data.success is True

    async def test_invalid_source(self, tools_mcp, seeded_session):
        async with Client(tools_mcp) as client:
            playlists = await client.call_tool("list_playlists", {})
            ref = playlists.data.results[0].ref

            with pytest.raises(ToolError, match="source"):
                await client.call_tool("set_source_of_truth", {
                    "playlist_ref": ref,
                    "source": "invalid",
                })
```

**Step 2: Implement sync tools**

```python
# app/mcp/tools/sync.py
"""Sync tools — link_playlist, set_source_of_truth, sync_playlist.

Replaces 3 sync stubs with working implementations.
Uses refs + envelope (Phase 2 conventions).
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import Depends

from app.mcp.dependencies import get_session
from app.mcp.envelope import wrap_action
from app.mcp.resolvers import PlaylistResolver
from app.mcp.schemas import ActionResponse

VALID_SOURCES = {"local", "remote", "bidirectional"}

def register_sync_tools(mcp: FastMCP) -> None:
    """Register sync tools."""

    @mcp.tool()
    async def link_playlist(
        playlist_ref: str,
        platform: str,
        platform_playlist_id: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Link a local playlist to a platform playlist.

        Stores the platform playlist ID in DjPlaylist.platform_ids.
        """
        from app.mcp.platforms.keys import PlatformKey

        # Validate platform key
        try:
            PlatformKey(platform)
        except ValueError:
            raise ToolError(f"Unknown platform: {platform}") from None

        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        # Update platform_ids
        current = dict(playlist.platform_ids or {})
        current[platform] = platform_playlist_id
        playlist.platform_ids = current
        await session.flush()

        return await wrap_action(
            success=True,
            message=f"Playlist {playlist_ref} linked to {platform}:{platform_playlist_id}",
            session=session,
        )

    @mcp.tool()
    async def set_source_of_truth(
        playlist_ref: str,
        source: str,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Set the source of truth for a playlist (local, remote, bidirectional)."""
        if source not in VALID_SOURCES:
            raise ToolError(
                f"Invalid source '{source}'. Valid: {', '.join(sorted(VALID_SOURCES))}"
            )

        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        playlist.source_of_truth = source
        await session.flush()

        return await wrap_action(
            success=True,
            message=f"Source of truth for {playlist_ref} set to '{source}'",
            session=session,
        )

    @mcp.tool()
    async def sync_playlist(
        playlist_ref: str,
        platform: str = "ym",
        prune: bool = False,
        session=Depends(get_session),
    ) -> ActionResponse:
        """Sync a playlist between local DB and a music platform.

        Direction is determined by source_of_truth setting.
        prune=True removes remote tracks not in local (requires 100% mapping).
        """
        from app.mcp.platforms.keys import PlatformKey
        from app.mcp.platforms.registry import PlatformRegistry
        from app.mcp.platforms.sync_engine import SyncDirection, SyncEngine
        from app.mcp.platforms.track_mapper import DbTrackMapper
        from app.repositories.playlists import DjPlaylistItemRepository

        resolver = PlaylistResolver(session)
        playlist = await resolver.resolve_one(playlist_ref)

        # Validate platform
        try:
            PlatformKey(platform)
        except ValueError:
            raise ToolError(f"Unknown platform: {platform}") from None

        # Check playlist is linked
        platform_ids = playlist.platform_ids or {}
        platform_playlist_id = platform_ids.get(platform)
        if not platform_playlist_id:
            raise ToolError(
                f"Playlist {playlist_ref} is not linked to {platform}. "
                f"Use link_playlist first."
            )

        # Determine direction from source_of_truth
        sot = playlist.source_of_truth or "local"
        if sot == "local":
            direction = SyncDirection.LOCAL_TO_REMOTE
        elif sot == "remote":
            direction = SyncDirection.REMOTE_TO_LOCAL
        else:
            direction = SyncDirection.BIDIRECTIONAL

        # Get local track IDs
        item_repo = DjPlaylistItemRepository(session)
        items, _ = await item_repo.list_by_playlist(
            playlist.playlist_id, offset=0, limit=10000
        )
        local_track_ids = [item.track_id for item in items]

        # Get adapter from registry (must be registered at startup)
        # NOTE: In production, registry is populated in gateway lifespan
        try:
            from app.mcp.platforms import _registry

            adapter = _registry.get(platform)
        except (KeyError, AttributeError):
            raise ToolError(
                f"Platform adapter '{platform}' not available. "
                f"Ensure it's registered in the gateway."
            ) from None

        # Sync
        mapper = DbTrackMapper(session)
        engine = SyncEngine(adapter, mapper)
        sync_result = await engine.sync(
            playlist_platform_id=platform_playlist_id,
            local_track_ids=local_track_ids,
            direction=direction,
            prune=prune,
        )

        from pydantic import BaseModel

        class SyncSummary(BaseModel):
            direction: str
            added_to_remote: int
            removed_from_remote: int
            new_remote_tracks: int
            mapping_coverage: float
            warnings: list[str]

        summary = SyncSummary(
            direction=sync_result.direction,
            added_to_remote=sync_result.added_to_remote,
            removed_from_remote=sync_result.removed_from_remote,
            new_remote_tracks=len(sync_result.new_remote_tracks),
            mapping_coverage=sync_result.mapping_coverage,
            warnings=sync_result.warnings,
        )

        return await wrap_action(
            success=True,
            message=f"Sync complete: +{sync_result.added_to_remote} added, "
            f"-{sync_result.removed_from_remote} removed",
            session=session,
            result=summary,
        )
```

**Step 3: Run tests + lint + commit**

```bash
uv run pytest tests/mcp/tools/test_sync.py -v
uv run ruff check app/mcp/tools/sync.py
```

```bash
git add app/mcp/tools/sync.py tests/mcp/tools/test_sync.py
git commit -m "feat(mcp): add sync tools (link_playlist, set_source_of_truth, sync_playlist)

sync_playlist uses SyncEngine with safe-by-default behavior.
Direction determined by source_of_truth setting.
All tools use refs + envelope."
```

---

## Task 8: Registry lifecycle in gateway lifespan

**Files:**
- Modify: `app/mcp/platforms/__init__.py` — module-level registry
- Modify: `app/mcp/lifespan.py` — register adapters on startup, close on shutdown
- Test: `tests/mcp/platforms/test_lifecycle.py`

**Step 1: Write the failing test**

```python
# tests/mcp/platforms/test_lifecycle.py
"""Test registry lifecycle integration."""

from __future__ import annotations

from app.mcp.platforms import get_registry
from app.mcp.platforms.registry import PlatformRegistry

class TestRegistryLifecycle:
    def test_get_registry_returns_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
        assert isinstance(r1, PlatformRegistry)
```

**Step 2: Implement**

В `app/mcp/platforms/__init__.py`:

```python
"""Multi-platform abstraction layer."""

from app.mcp.platforms.keys import PlatformKey
from app.mcp.platforms.protocol import (
    MusicPlatform,
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.mcp.platforms.registry import PlatformRegistry

__all__ = [
    "MusicPlatform",
    "PlatformCapability",
    "PlatformKey",
    "PlatformPlaylist",
    "PlatformTrack",
    "get_registry",
]

_registry: PlatformRegistry | None = None

def get_registry() -> PlatformRegistry:
    """Get the global platform registry (singleton)."""
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = PlatformRegistry()
    return _registry
```

В `app/mcp/lifespan.py`, обновить lifespan:

```python
@lifespan
async def mcp_lifespan(server):
    from app.mcp.platforms import get_registry

    registry = get_registry()

    # Register YM adapter if token is configured
    from app.config import get_settings

    settings = get_settings()
    if settings.yandex_music_token:
        from app.mcp.yandex_music.adapter import YandexMusicAdapter
        from app.services.yandex_music_client import YandexMusicClient

        client = YandexMusicClient(
            token=settings.yandex_music_token,
            user_id=settings.yandex_music_user_id,
        )
        adapter = YandexMusicAdapter(client=client, user_id=settings.yandex_music_user_id)
        registry.register(adapter)

    started_at = datetime.now(tz=UTC).isoformat()
    logger.info("MCP server starting", extra={"server": server.name})

    try:
        yield {"started_at": started_at}
    finally:
        await registry.close_all()
        logger.info("MCP server shut down", extra={"server": server.name})
```

**Step 3: Run tests + commit**

```bash
uv run pytest tests/mcp/platforms/test_lifecycle.py -v
```

```bash
git add app/mcp/platforms/__init__.py app/mcp/lifespan.py \
       tests/mcp/platforms/test_lifecycle.py
git commit -m "feat(mcp): wire PlatformRegistry lifecycle into gateway lifespan

YM adapter registered on startup if token configured.
close_all() called on shutdown."
```

---

## Task 9: Integration tests + CI

**Files:**
- Create: `tests/mcp/platforms/test_integration.py`

**Step 1: Write integration test**

```python
# tests/mcp/platforms/test_integration.py
"""Integration tests for multi-platform sync."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.mcp.platforms.protocol import PlatformCapability, PlatformPlaylist
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.platforms.sync_engine import SyncDirection, SyncEngine
from app.mcp.platforms.track_mapper import DbTrackMapper
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.models.tracks import Track

class TestEndToEndSync:
    async def test_full_sync_cycle(self, session):
        """Full sync: seed data → map → diff → apply."""
        # Seed provider and tracks
        provider = Provider(provider_id=1, provider_code="yandex_music", name="YM")
        session.add(provider)

        t1 = Track(title="A", title_sort="a", duration_ms=180000, status=0)
        t2 = Track(title="B", title_sort="b", duration_ms=180000, status=0)
        session.add_all([t1, t2])
        await session.flush()

        # Map both tracks to platform
        session.add_all([
            ProviderTrackId(track_id=t1.track_id, provider_id=1, provider_track_id="111"),
            ProviderTrackId(track_id=t2.track_id, provider_id=1, provider_track_id="222"),
        ])
        await session.flush()

        # Mock adapter: remote has only track 111
        adapter = AsyncMock()
        adapter.name = "ym"
        adapter.get_playlist.return_value = PlatformPlaylist(
            platform_id="1003", name="Test", track_ids=["111"]
        )

        mapper = DbTrackMapper(session)
        engine = SyncEngine(adapter, mapper)

        result = await engine.sync(
            playlist_platform_id="1003",
            local_track_ids=[t1.track_id, t2.track_id],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert result.added_to_remote == 1  # 222 added
        assert result.mapping_coverage == 1.0
        adapter.add_tracks_to_playlist.assert_called_once_with("1003", ["222"])
```

**Step 2: Run all Phase 3 tests**

```bash
uv run pytest tests/mcp/platforms/ tests/mcp/yandex_music/test_adapter.py tests/mcp/tools/test_sync.py -v
```

**Step 3: Full CI check**

```bash
uv run ruff check app/mcp/platforms/ app/mcp/yandex_music/adapter.py app/mcp/tools/sync.py && \
uv run mypy app/mcp/platforms/ && \
uv run pytest tests/mcp/platforms/ tests/mcp/yandex_music/test_adapter.py -v
```

**Step 4: Commit**

```bash
git add tests/mcp/platforms/test_integration.py
git commit -m "test(mcp): add Phase 3 integration tests — full sync cycle

Seeds tracks + provider mappings, mocks adapter, verifies
SyncEngine adds missing tracks to remote playlist."
```

```bash
git commit --allow-empty -m "chore: Phase 3 complete — multi-platform sync

MusicPlatform Protocol + PlatformRegistry + YandexMusicAdapter
DbTrackMapper + SyncEngine (safe-by-default) + sync MCP tools
DjPlaylist sync columns + gateway lifecycle integration"
```
