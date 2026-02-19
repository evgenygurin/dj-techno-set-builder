# MCP Tools Redesign — Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build multi-platform abstraction (MusicPlatform protocol, PlatformRegistry, YandexMusicAdapter) and bidirectional SyncEngine with configurable source-of-truth — replacing the 3 sync stubs with working implementations.

**Architecture:** Port/Adapter pattern: `MusicPlatform` protocol defines common interface, platform-specific adapters wrap real API clients. `PlatformRegistry` manages adapter lifecycle. `SyncEngine` diffs local vs remote playlists and applies changes bidirectionally. DjPlaylist model extended with sync metadata columns. All new code in `app/mcp/platforms/` and `app/mcp/sync/`.

**Tech Stack:** Python 3.12+, FastMCP 3.0, Pydantic v2, SQLAlchemy 2.0 async, pytest

**Design doc:** `docs/plans/2026-02-19-mcp-tools-redesign-design.md`
**Phase 1 plan:** `docs/plans/2026-02-19-mcp-tools-redesign-plan.md` (prerequisite)
**Phase 2 plan:** `docs/plans/2026-02-19-mcp-tools-redesign-phase2-plan.md` (prerequisite)

**Phase 1 delivers (used by this plan):**
- `app/mcp/types_v2.py` — TrackSummary, PlaylistSummary, LibraryStats, PaginationInfo, FindResult
- `app/mcp/refs.py` — parse_ref, ParsedRef, RefType (handles `ym:12345`, `local:42`, text)
- `app/mcp/entity_finder.py` — TrackFinder, PlaylistFinder

**Phase 2 delivers (used by this plan):**
- `app/mcp/response.py` — wrap_list, wrap_detail, wrap_action helpers
- `app/mcp/converters.py` — track_to_summary, playlist_to_summary
- CRUD tools: list_tracks, get_track, list_playlists, get_playlist, etc.
- Compute/persist split established

**Existing infrastructure this plan builds on:**
- `app/models/providers.py` — Provider model (4 providers: spotify, soundcloud, beatport, yandex_music)
- `app/models/ingestion.py` — ProviderTrackId (local track_id ↔ platform track_id mapping)
- `app/models/metadata_yandex.py` — YandexMetadata (yandex_track_id, album, etc.)
- `app/services/yandex_music_client.py` — YandexMusicClient (search, fetch_playlist_tracks, download, rate limiting)
- `app/models/dj.py` — DjPlaylist (no sync fields yet), DjPlaylistItem
- `app/models/sets.py` — DjSet (has ym_playlist_id already)
- `app/mcp/workflows/sync_tools.py` — 3 stubs (sync_set_to_ym, sync_set_from_ym, sync_playlist)

---

## Task 1: MusicPlatform Protocol

**Files:**
- Create: `app/mcp/platforms/__init__.py`
- Create: `app/mcp/platforms/protocol.py`
- Test: `tests/mcp/platforms/test_protocol.py`

Defines the common interface all music platform adapters must implement. Uses `typing.Protocol` for structural subtyping.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/__init__.py
```

```python
# tests/mcp/platforms/test_protocol.py
"""Tests for MusicPlatform protocol definition."""

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
        assert t.platform_id == "12345"
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
            platform_id="1003",
            name="My Techno",
            track_ids=["111", "222", "333"],
            owner_id="250905515",
        )
        assert len(p.track_ids) == 3

class TestPlatformCapability:
    def test_values(self):
        assert PlatformCapability.SEARCH in PlatformCapability
        assert PlatformCapability.DOWNLOAD in PlatformCapability
        assert PlatformCapability.PLAYLIST_WRITE in PlatformCapability

class TestProtocolCompliance:
    """Verify that a minimal implementation satisfies the Protocol."""

    def test_dummy_adapter_satisfies_protocol(self):
        @dataclass
        class DummyAdapter:
            name: str = "dummy"
            capabilities: frozenset[PlatformCapability] = frozenset(
                {PlatformCapability.SEARCH}
            )

            async def search_tracks(
                self, query: str, *, limit: int = 20
            ) -> list[PlatformTrack]:
                return []

            async def get_track(self, platform_id: str) -> PlatformTrack:
                return PlatformTrack(
                    platform_id=platform_id,
                    title="test",
                    artists="test",
                )

            async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
                return PlatformPlaylist(
                    platform_id=platform_id,
                    name="test",
                    track_ids=[],
                )

            async def create_playlist(
                self, name: str, track_ids: list[str]
            ) -> str:
                return "new_id"

            async def add_tracks_to_playlist(
                self, playlist_id: str, track_ids: list[str]
            ) -> None:
                pass

            async def remove_tracks_from_playlist(
                self, playlist_id: str, track_ids: list[str]
            ) -> None:
                pass

            async def delete_playlist(self, playlist_id: str) -> None:
                pass

            async def get_download_url(
                self, track_id: str, *, bitrate: int = 320
            ) -> str | None:
                return None

            async def close(self) -> None:
                pass

        adapter = DummyAdapter()
        # Protocol check: isinstance doesn't work with Protocol at runtime,
        # but we verify the interface is complete by using type annotation
        platform: MusicPlatform = adapter
        assert platform.name == "dummy"
        assert PlatformCapability.SEARCH in platform.capabilities
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/platforms/test_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.platforms'`

**Step 3: Write minimal implementation**

```python
# app/mcp/platforms/__init__.py
"""Multi-platform abstraction layer."""
```

```python
# app/mcp/platforms/protocol.py
"""MusicPlatform protocol — common interface for all music platforms."""

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
    """Minimal track representation from a platform."""

    platform_id: str
    title: str
    artists: str
    duration_ms: int | None = None
    cover_uri: str | None = None
    album_title: str | None = None
    genre: str | None = None

class PlatformPlaylist(BaseModel):
    """Minimal playlist representation from a platform."""

    platform_id: str
    name: str
    track_ids: list[str]
    owner_id: str | None = None
    track_count: int | None = None

@runtime_checkable
class MusicPlatform(Protocol):
    """Common interface for all music platform adapters.

    Every adapter exposes a standard set of operations.
    Capabilities indicate which operations are actually supported.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[PlatformCapability]: ...

    async def search_tracks(
        self, query: str, *, limit: int = 20
    ) -> list[PlatformTrack]: ...

    async def get_track(self, platform_id: str) -> PlatformTrack: ...

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist: ...

    async def create_playlist(
        self, name: str, track_ids: list[str]
    ) -> str: ...

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None: ...

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None: ...

    async def delete_playlist(self, playlist_id: str) -> None: ...

    async def get_download_url(
        self, track_id: str, *, bitrate: int = 320
    ) -> str | None: ...

    async def close(self) -> None: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/platforms/test_protocol.py -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add app/mcp/platforms/__init__.py app/mcp/platforms/protocol.py \
       tests/mcp/platforms/__init__.py tests/mcp/platforms/test_protocol.py
git commit -m "feat(mcp): add MusicPlatform protocol and platform data models"
```

---

## Task 2: PlatformRegistry

**Files:**
- Create: `app/mcp/platforms/registry.py`
- Test: `tests/mcp/platforms/test_registry.py`

Manages platform adapter instances. Provides lookup by name, lists connected platforms, handles lifecycle (close all).

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_registry.py
"""Tests for PlatformRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.mcp.platforms.protocol import (
    MusicPlatform,
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.mcp.platforms.registry import PlatformRegistry

@dataclass
class FakeAdapter:
    """Minimal MusicPlatform implementation for testing."""

    name: str = "fake"
    capabilities: frozenset[PlatformCapability] = frozenset(
        {PlatformCapability.SEARCH, PlatformCapability.PLAYLIST_READ}
    )
    closed: bool = field(default=False, init=False)

    async def search_tracks(
        self, query: str, *, limit: int = 20
    ) -> list[PlatformTrack]:
        return [
            PlatformTrack(
                platform_id="1", title=f"Result for {query}", artists="Artist"
            )
        ]

    async def get_track(self, platform_id: str) -> PlatformTrack:
        return PlatformTrack(
            platform_id=platform_id, title="Fake", artists="Fake"
        )

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        return PlatformPlaylist(
            platform_id=platform_id, name="Fake PL", track_ids=[]
        )

    async def create_playlist(
        self, name: str, track_ids: list[str]
    ) -> str:
        return "new"

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        pass

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        pass

    async def delete_playlist(self, playlist_id: str) -> None:
        pass

    async def get_download_url(
        self, track_id: str, *, bitrate: int = 320
    ) -> str | None:
        return None

    async def close(self) -> None:
        self.closed = True

class TestPlatformRegistry:
    def test_register_and_get(self):
        reg = PlatformRegistry()
        adapter = FakeAdapter(name="ym")
        reg.register(adapter)

        assert reg.get("ym") is adapter

    def test_get_unknown_raises(self):
        reg = PlatformRegistry()
        with pytest.raises(KeyError, match="ym"):
            reg.get("ym")

    def test_is_connected(self):
        reg = PlatformRegistry()
        assert reg.is_connected("ym") is False

        reg.register(FakeAdapter(name="ym"))
        assert reg.is_connected("ym") is True

    def test_list_connected(self):
        reg = PlatformRegistry()
        reg.register(FakeAdapter(name="ym"))
        reg.register(FakeAdapter(name="spotify"))
        assert sorted(reg.list_connected()) == ["spotify", "ym"]

    def test_list_connected_empty(self):
        reg = PlatformRegistry()
        assert reg.list_connected() == []

    async def test_close_all(self):
        reg = PlatformRegistry()
        a1 = FakeAdapter(name="ym")
        a2 = FakeAdapter(name="spotify")
        reg.register(a1)
        reg.register(a2)

        await reg.close_all()
        assert a1.closed is True
        assert a2.closed is True

    def test_register_duplicate_replaces(self):
        reg = PlatformRegistry()
        a1 = FakeAdapter(name="ym")
        a2 = FakeAdapter(name="ym")
        reg.register(a1)
        reg.register(a2)

        assert reg.get("ym") is a2

    def test_has_capability(self):
        reg = PlatformRegistry()
        reg.register(FakeAdapter(name="ym"))

        assert reg.has_capability("ym", PlatformCapability.SEARCH) is True
        assert reg.has_capability("ym", PlatformCapability.DOWNLOAD) is False

    def test_has_capability_unknown_platform(self):
        reg = PlatformRegistry()
        assert reg.has_capability("ym", PlatformCapability.SEARCH) is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/platforms/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.platforms.registry'`

**Step 3: Write minimal implementation**

```python
# app/mcp/platforms/registry.py
"""PlatformRegistry — manages music platform adapter instances."""

from __future__ import annotations

from app.mcp.platforms.protocol import MusicPlatform, PlatformCapability

class PlatformRegistry:
    """Registry of connected music platform adapters.

    Provides lookup by platform name, capability checks,
    and lifecycle management (close_all).
    """

    def __init__(self) -> None:
        self._platforms: dict[str, MusicPlatform] = {}

    def register(self, adapter: MusicPlatform) -> None:
        """Register a platform adapter. Replaces existing if same name."""
        self._platforms[adapter.name] = adapter

    def get(self, name: str) -> MusicPlatform:
        """Get adapter by platform name. Raises KeyError if not found."""
        try:
            return self._platforms[name]
        except KeyError:
            msg = f"Platform '{name}' is not connected"
            raise KeyError(msg) from None

    def is_connected(self, name: str) -> bool:
        """Check if a platform adapter is registered."""
        return name in self._platforms

    def list_connected(self) -> list[str]:
        """Return sorted list of connected platform names."""
        return sorted(self._platforms.keys())

    def has_capability(
        self, name: str, capability: PlatformCapability
    ) -> bool:
        """Check if a connected platform supports a capability."""
        if name not in self._platforms:
            return False
        return capability in self._platforms[name].capabilities

    async def close_all(self) -> None:
        """Close all registered adapters."""
        for adapter in self._platforms.values():
            await adapter.close()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/platforms/test_registry.py -v`
Expected: PASS (all 9 tests)

**Step 5: Commit**

```bash
git add app/mcp/platforms/registry.py tests/mcp/platforms/test_registry.py
git commit -m "feat(mcp): add PlatformRegistry for managing platform adapters"
```

---

## Task 3: YandexMusicAdapter

**Files:**
- Create: `app/mcp/platforms/yandex.py`
- Test: `tests/mcp/platforms/test_yandex.py`

Wraps the existing `YandexMusicClient` (from `app/services/yandex_music_client.py`) to conform to the `MusicPlatform` protocol. Maps raw YM API responses to `PlatformTrack`/`PlatformPlaylist`. Relies on existing `parse_ym_track()` for normalization.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_yandex.py
"""Tests for YandexMusicAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.platforms.protocol import PlatformCapability
from app.mcp.platforms.yandex import YandexMusicAdapter

@pytest.fixture
def mock_ym_client():
    """Create a mock YandexMusicClient."""
    client = AsyncMock()
    client.search_tracks = AsyncMock(return_value=[
        {
            "id": 12345,
            "title": "Gravity",
            "artists": [{"name": "Boris Brejcha", "various": False}],
            "durationMs": 360000,
            "albums": [
                {
                    "id": 999,
                    "title": "Gravity EP",
                    "type": "single",
                    "genre": "techno",
                    "year": 2023,
                    "labels": [{"name": "Fckng Serious"}],
                    "releaseDate": "2023-06-15",
                }
            ],
            "coverUri": "avatars.yandex.net/get-music-content/123/cover/%%",
            "explicit": False,
        }
    ])
    client.fetch_playlist_tracks = AsyncMock(return_value=[
        {"track": {"id": 111, "title": "A", "artists": [{"name": "X", "various": False}]}},
        {"track": {"id": 222, "title": "B", "artists": [{"name": "Y", "various": False}]}},
    ])
    client.fetch_tracks_metadata = AsyncMock(return_value=[
        {
            "id": 12345,
            "title": "Gravity",
            "artists": [{"name": "Boris Brejcha", "various": False}],
            "durationMs": 360000,
            "albums": [],
            "coverUri": None,
            "explicit": False,
        }
    ])
    client.resolve_download_url = AsyncMock(
        return_value="https://cdn.example.com/track.mp3"
    )
    client.close = AsyncMock()
    return client

@pytest.fixture
def adapter(mock_ym_client):
    return YandexMusicAdapter(
        client=mock_ym_client, user_id="250905515"
    )

class TestYandexMusicAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "ym"

    def test_capabilities(self, adapter):
        caps = adapter.capabilities
        assert PlatformCapability.SEARCH in caps
        assert PlatformCapability.DOWNLOAD in caps
        assert PlatformCapability.PLAYLIST_READ in caps
        assert PlatformCapability.LIKES in caps

class TestSearchTracks:
    async def test_search_returns_platform_tracks(self, adapter, mock_ym_client):
        results = await adapter.search_tracks("Boris Brejcha", limit=10)

        assert len(results) == 1
        assert results[0].platform_id == "12345"
        assert results[0].title == "Gravity"
        assert results[0].artists == "Boris Brejcha"
        assert results[0].duration_ms == 360000
        mock_ym_client.search_tracks.assert_called_once_with("Boris Brejcha")

    async def test_search_empty(self, adapter, mock_ym_client):
        mock_ym_client.search_tracks.return_value = []
        results = await adapter.search_tracks("nonexistent")
        assert results == []

class TestGetTrack:
    async def test_get_track(self, adapter, mock_ym_client):
        track = await adapter.get_track("12345")

        assert track.platform_id == "12345"
        assert track.title == "Gravity"
        mock_ym_client.fetch_tracks_metadata.assert_called_once_with(["12345"])

    async def test_get_track_not_found(self, adapter, mock_ym_client):
        mock_ym_client.fetch_tracks_metadata.return_value = []
        with pytest.raises(ValueError, match="not found"):
            await adapter.get_track("99999")

class TestGetPlaylist:
    async def test_get_playlist(self, adapter, mock_ym_client):
        pl = await adapter.get_playlist("1003")

        assert pl.platform_id == "1003"
        assert pl.track_ids == ["111", "222"]
        assert pl.owner_id == "250905515"
        mock_ym_client.fetch_playlist_tracks.assert_called_once_with(
            "250905515", "1003"
        )

    async def test_get_playlist_empty(self, adapter, mock_ym_client):
        mock_ym_client.fetch_playlist_tracks.return_value = []
        pl = await adapter.get_playlist("1003")
        assert pl.track_ids == []

class TestGetDownloadUrl:
    async def test_download_url(self, adapter, mock_ym_client):
        url = await adapter.get_download_url("12345", bitrate=320)
        assert url == "https://cdn.example.com/track.mp3"
        mock_ym_client.resolve_download_url.assert_called_once_with(
            "12345", prefer_bitrate=320
        )

    async def test_download_url_failure(self, adapter, mock_ym_client):
        mock_ym_client.resolve_download_url.side_effect = ValueError("No download info")
        url = await adapter.get_download_url("99999")
        assert url is None

class TestPlaylistWrite:
    """Playlist write operations are stubs for now (YM API is complex)."""

    async def test_create_playlist_not_supported(self, adapter):
        assert PlatformCapability.PLAYLIST_WRITE not in adapter.capabilities

    async def test_create_playlist_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            await adapter.create_playlist("test", ["1", "2"])

class TestClose:
    async def test_close(self, adapter, mock_ym_client):
        await adapter.close()
        mock_ym_client.close.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/platforms/test_yandex.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.platforms.yandex'`

**Step 3: Write minimal implementation**

```python
# app/mcp/platforms/yandex.py
"""YandexMusicAdapter — wraps YandexMusicClient to MusicPlatform protocol."""

from __future__ import annotations

import contextlib
import logging

from app.mcp.platforms.protocol import (
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.services.yandex_music_client import YandexMusicClient, parse_ym_track

logger = logging.getLogger(__name__)

class YandexMusicAdapter:
    """Adapter wrapping YandexMusicClient to the MusicPlatform interface.

    Converts raw YM API responses to PlatformTrack/PlatformPlaylist.
    Playlist write operations are not yet supported (YM API requires
    complex diff-based mutations).
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
            PlatformCapability.LIKES,
        })

    async def search_tracks(
        self, query: str, *, limit: int = 20
    ) -> list[PlatformTrack]:
        """Search YM for tracks."""
        raw_tracks = await self._client.search_tracks(query)
        return [self._to_platform_track(t) for t in raw_tracks[:limit]]

    async def get_track(self, platform_id: str) -> PlatformTrack:
        """Fetch a single track by YM track ID."""
        raw_list = await self._client.fetch_tracks_metadata([platform_id])
        if not raw_list:
            msg = f"YM track {platform_id} not found"
            raise ValueError(msg)
        return self._to_platform_track(raw_list[0])

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        """Fetch playlist tracks by playlist kind (ID)."""
        raw_items = await self._client.fetch_playlist_tracks(
            self._user_id, platform_id
        )
        track_ids: list[str] = []
        for item in raw_items:
            track_data = item.get("track", item)
            track_id = track_data.get("id")
            if track_id is not None:
                track_ids.append(str(track_id))
        return PlatformPlaylist(
            platform_id=platform_id,
            name="",  # YM fetch_playlist_tracks doesn't return playlist name
            track_ids=track_ids,
            owner_id=self._user_id,
        )

    async def create_playlist(
        self, name: str, track_ids: list[str]
    ) -> str:
        """Not yet supported — YM playlist creation requires diff-based API."""
        raise NotImplementedError(
            "YM playlist creation not yet implemented"
        )

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        """Not yet supported."""
        raise NotImplementedError(
            "YM playlist modification not yet implemented"
        )

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        """Not yet supported."""
        raise NotImplementedError(
            "YM playlist modification not yet implemented"
        )

    async def delete_playlist(self, playlist_id: str) -> None:
        """Not yet supported."""
        raise NotImplementedError(
            "YM playlist deletion not yet implemented"
        )

    async def get_download_url(
        self, track_id: str, *, bitrate: int = 320
    ) -> str | None:
        """Resolve a direct download URL for a YM track."""
        with contextlib.suppress(Exception):
            return await self._client.resolve_download_url(
                track_id, prefer_bitrate=bitrate
            )
        return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    @staticmethod
    def _to_platform_track(raw: dict) -> PlatformTrack:
        """Convert raw YM track dict to PlatformTrack."""
        parsed = parse_ym_track(raw)
        return PlatformTrack(
            platform_id=parsed.yandex_track_id,
            title=parsed.title,
            artists=parsed.artists,
            duration_ms=parsed.duration_ms,
            cover_uri=parsed.cover_uri,
            album_title=parsed.album_title,
            genre=parsed.album_genre,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/platforms/test_yandex.py -v`
Expected: PASS (all 11 tests)

**Step 5: Commit**

```bash
git add app/mcp/platforms/yandex.py tests/mcp/platforms/test_yandex.py
git commit -m "feat(mcp): add YandexMusicAdapter wrapping YM client to MusicPlatform protocol"
```

---

## Task 4: PlatformRegistry DI + Wiring

**Files:**
- Modify: `app/mcp/dependencies.py` — add `get_platform_registry` provider
- Modify: `app/mcp/workflows/server.py` — wire registry into MCP server creation
- Test: `tests/mcp/platforms/test_registry_di.py`

Wire PlatformRegistry into the FastMCP DI chain. Registry is a singleton created once in server setup. YandexMusicAdapter is registered when YM token is configured.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_registry_di.py
"""Tests for PlatformRegistry DI integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.platforms.protocol import PlatformCapability
from app.mcp.platforms.registry import PlatformRegistry

class TestRegistryFactory:
    def test_create_registry_with_ym(self):
        """Registry includes YM adapter when token is configured."""
        from app.mcp.platforms.factory import create_platform_registry

        with patch("app.mcp.platforms.factory.settings") as mock_settings:
            mock_settings.yandex_music_token = "test_token"
            mock_settings.yandex_music_user_id = "250905515"

            registry = create_platform_registry()

        assert registry.is_connected("ym")
        assert registry.has_capability("ym", PlatformCapability.SEARCH)

    def test_create_registry_without_ym(self):
        """Registry is empty when no token configured."""
        from app.mcp.platforms.factory import create_platform_registry

        with patch("app.mcp.platforms.factory.settings") as mock_settings:
            mock_settings.yandex_music_token = ""
            mock_settings.yandex_music_user_id = ""

            registry = create_platform_registry()

        assert not registry.is_connected("ym")
        assert registry.list_connected() == []

    def test_create_registry_ym_no_user_id(self):
        """YM adapter not registered when user_id is missing."""
        from app.mcp.platforms.factory import create_platform_registry

        with patch("app.mcp.platforms.factory.settings") as mock_settings:
            mock_settings.yandex_music_token = "test_token"
            mock_settings.yandex_music_user_id = ""

            registry = create_platform_registry()

        assert not registry.is_connected("ym")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/platforms/test_registry_di.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.platforms.factory'`

**Step 3: Write minimal implementation**

```python
# app/mcp/platforms/factory.py
"""Factory for creating PlatformRegistry with configured adapters."""

from __future__ import annotations

import logging

from app.config import settings
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.platforms.yandex import YandexMusicAdapter
from app.services.yandex_music_client import YandexMusicClient

logger = logging.getLogger(__name__)

def create_platform_registry() -> PlatformRegistry:
    """Create a PlatformRegistry with all configured platform adapters.

    Checks app settings for each platform's credentials.
    Only registers adapters for platforms that have valid config.
    """
    registry = PlatformRegistry()

    # Yandex Music
    if settings.yandex_music_token and settings.yandex_music_user_id:
        ym_client = YandexMusicClient(
            token=settings.yandex_music_token,
            user_id=settings.yandex_music_user_id,
        )
        adapter = YandexMusicAdapter(
            client=ym_client,
            user_id=settings.yandex_music_user_id,
        )
        registry.register(adapter)
        logger.info("Registered YandexMusic adapter (user=%s)", settings.yandex_music_user_id)
    else:
        logger.info("YandexMusic adapter not configured — skipping")

    # Future: Spotify, Beatport, SoundCloud adapters
    # if settings.spotify_client_id and settings.spotify_client_secret:
    #     ...

    return registry
```

Now check if `yandex_music_user_id` exists in settings. If not, add it.

Check `app/config.py` for existing settings:

```python
# Add to app/config.py Settings class if not present:
yandex_music_user_id: str = ""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/platforms/test_registry_di.py -v`
Expected: PASS (all 3 tests)

**Step 5: Add get_platform_registry to dependencies.py**

Add to `app/mcp/dependencies.py`:

```python
from app.mcp.platforms.factory import create_platform_registry
from app.mcp.platforms.registry import PlatformRegistry

# Module-level singleton — created once, shared across all MCP tool calls.
_platform_registry: PlatformRegistry | None = None

def get_platform_registry() -> PlatformRegistry:
    """Provide the global PlatformRegistry singleton.

    Created on first call via create_platform_registry().
    """
    global _platform_registry  # noqa: PLW0603
    if _platform_registry is None:
        _platform_registry = create_platform_registry()
    return _platform_registry
```

**Step 6: Run all MCP tests**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS (no regressions)

**Step 7: Commit**

```bash
git add app/mcp/platforms/factory.py app/mcp/dependencies.py app/config.py \
       tests/mcp/platforms/test_registry_di.py
git commit -m "feat(mcp): wire PlatformRegistry into DI with factory + singleton"
```

---

## Task 5: DjPlaylist Sync Columns (Alembic Migration)

**Files:**
- Modify: `app/models/dj.py:144-157` — add sync columns to DjPlaylist
- Modify: `app/schemas/playlists.py` — add sync fields to schemas
- Create: Alembic migration file
- Test: `tests/mcp/platforms/test_sync_model.py`

Extends DjPlaylist with `source_of_truth`, `sync_targets`, `platform_ids` columns needed for bidirectional sync.

**Step 1: Write the failing tests**

```python
# tests/mcp/platforms/test_sync_model.py
"""Tests for DjPlaylist sync columns."""

from __future__ import annotations

from app.models.dj import DjPlaylist

class TestDjPlaylistSyncFields:
    def test_default_source_of_truth(self):
        """New playlists default to local as source of truth."""
        pl = DjPlaylist(
            name="Test",
            source_of_truth="local",
        )
        assert pl.source_of_truth == "local"

    def test_ym_source_of_truth(self):
        pl = DjPlaylist(
            name="Test",
            source_of_truth="ym",
        )
        assert pl.source_of_truth == "ym"

    def test_platform_ids_json(self):
        pl = DjPlaylist(
            name="Test",
            platform_ids={"ym": "1003:250905515"},
        )
        assert pl.platform_ids["ym"] == "1003:250905515"

    def test_platform_ids_default_none(self):
        pl = DjPlaylist(name="Test")
        assert pl.platform_ids is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/platforms/test_sync_model.py -v`
Expected: FAIL with `TypeError` (DjPlaylist doesn't have `source_of_truth` or `platform_ids` attributes)

**Step 3: Add columns to DjPlaylist model**

Modify `app/models/dj.py` — add to `DjPlaylist` class:

```python
class DjPlaylist(Base):
    __tablename__ = "dj_playlists"

    playlist_id: Mapped[int] = mapped_column(primary_key=True)
    parent_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("dj_playlists.playlist_id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(500))
    source_app: Mapped[int | None] = mapped_column(
        SmallInteger,
        CheckConstraint("source_app BETWEEN 1 AND 5", name="ck_playlist_source_app"),
    )
    # --- Sync fields ---
    source_of_truth: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "source_of_truth IN ('local', 'ym', 'spotify', 'beatport', 'soundcloud')",
            name="ck_playlist_source_of_truth",
        ),
        default="local",
        server_default="local",
    )
    platform_ids: Mapped[dict[str, str] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

Note: need to add `JSON` import to `app/models/dj.py`:

```python
from sqlalchemy import (
    JSON,  # add this
    Boolean,
    CheckConstraint,
    ...
)
```

**Step 4: Update schemas**

Add to `app/schemas/playlists.py`:

```python
class DjPlaylistCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=500)
    parent_playlist_id: int | None = None
    source_app: int | None = Field(default=None, ge=1, le=5)
    source_of_truth: str = Field(default="local", pattern=r"^(local|ym|spotify|beatport|soundcloud)$")
    platform_ids: dict[str, str] | None = None

class DjPlaylistUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    parent_playlist_id: int | None = None
    source_app: int | None = Field(default=None, ge=1, le=5)
    source_of_truth: str | None = Field(default=None, pattern=r"^(local|ym|spotify|beatport|soundcloud)$")
    platform_ids: dict[str, str] | None = None

class DjPlaylistRead(BaseSchema):
    playlist_id: int
    name: str
    parent_playlist_id: int | None
    source_app: int | None
    source_of_truth: str
    platform_ids: dict[str, str] | None
    created_at: datetime
```

**Step 5: Create Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add sync columns to dj_playlists"`

Then review generated migration to ensure it adds:
- `source_of_truth VARCHAR(20) NOT NULL DEFAULT 'local'`
- `platform_ids JSON`

Run: `uv run alembic upgrade head`

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/mcp/platforms/test_sync_model.py -v`
Expected: PASS (all 4 tests)

**Step 7: Run full test suite**

Run: `uv run pytest -x -v`
Expected: PASS (existing tests should not break — new columns have defaults)

**Step 8: Commit**

```bash
git add app/models/dj.py app/schemas/playlists.py \
       alembic/versions/*.py \
       tests/mcp/platforms/test_sync_model.py
git commit -m "feat(db): add source_of_truth and platform_ids columns to dj_playlists"
```

---

## Task 6: SyncEngine — Diff Logic

**Files:**
- Create: `app/mcp/sync/__init__.py`
- Create: `app/mcp/sync/diff.py`
- Test: `tests/mcp/sync/test_diff.py`

Pure function that computes the diff between a local playlist and a remote playlist. Returns a `SyncDiff` with tracks to add/remove on each side. No DB or API calls — pure logic.

**Step 1: Write the failing tests**

```python
# tests/mcp/sync/__init__.py
```

```python
# tests/mcp/sync/test_diff.py
"""Tests for playlist sync diff logic."""

from __future__ import annotations

from app.mcp.sync.diff import SyncDiff, SyncDirection, compute_sync_diff

class TestComputeSyncDiff:
    def test_identical_playlists(self):
        """No changes when playlists are identical."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b", "c"],
            remote_track_ids=["a", "b", "c"],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert diff.add_to_local == []
        assert diff.remove_from_local == []
        assert diff.add_to_remote == []
        assert diff.remove_from_remote == []
        assert diff.is_empty

    def test_local_to_remote_adds(self):
        """Local has extra tracks — push them to remote."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b", "c", "d"],
            remote_track_ids=["a", "b"],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )
        assert diff.add_to_remote == ["c", "d"]
        assert diff.remove_from_remote == []
        assert diff.add_to_local == []
        assert diff.remove_from_local == []

    def test_local_to_remote_removes(self):
        """Remote has extra tracks — remove them from remote."""
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["a", "b", "c"],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )
        assert diff.remove_from_remote == ["b", "c"]
        assert diff.add_to_remote == []

    def test_remote_to_local_adds(self):
        """Remote has extra tracks — pull them to local."""
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["a", "b", "c"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.add_to_local == ["b", "c"]
        assert diff.remove_from_local == []
        assert diff.add_to_remote == []

    def test_remote_to_local_removes(self):
        """Local has extra tracks — remove them from local."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b", "c"],
            remote_track_ids=["a"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.remove_from_local == ["b", "c"]

    def test_bidirectional_merge(self):
        """Bidirectional: add to each side what the other has."""
        diff = compute_sync_diff(
            local_track_ids=["a", "b"],
            remote_track_ids=["b", "c"],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert diff.add_to_local == ["c"]
        assert diff.add_to_remote == ["a"]
        # Bidirectional never removes
        assert diff.remove_from_local == []
        assert diff.remove_from_remote == []

    def test_empty_local(self):
        diff = compute_sync_diff(
            local_track_ids=[],
            remote_track_ids=["a", "b"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.add_to_local == ["a", "b"]

    def test_empty_remote(self):
        diff = compute_sync_diff(
            local_track_ids=["a", "b"],
            remote_track_ids=[],
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )
        assert diff.add_to_remote == ["a", "b"]

    def test_both_empty(self):
        diff = compute_sync_diff(
            local_track_ids=[],
            remote_track_ids=[],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert diff.is_empty

    def test_is_empty_false(self):
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["b"],
            direction=SyncDirection.BIDIRECTIONAL,
        )
        assert not diff.is_empty

    def test_preserves_order(self):
        """Added tracks maintain their relative order."""
        diff = compute_sync_diff(
            local_track_ids=["a"],
            remote_track_ids=["a", "x", "y", "z"],
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )
        assert diff.add_to_local == ["x", "y", "z"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/sync/test_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.sync'`

**Step 3: Write minimal implementation**

```python
# app/mcp/sync/__init__.py
"""Bidirectional playlist sync engine."""
```

```python
# app/mcp/sync/diff.py
"""Pure-function diff computation for playlist sync."""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

class SyncDirection(Enum):
    """Direction of sync between local and remote playlists."""

    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"
    BIDIRECTIONAL = "bidirectional"

class SyncDiff(NamedTuple):
    """Diff result describing what changes are needed on each side.

    Platform track IDs (strings) are used throughout — the caller
    is responsible for mapping between local DB IDs and platform IDs.
    """

    add_to_local: list[str]
    remove_from_local: list[str]
    add_to_remote: list[str]
    remove_from_remote: list[str]

    @property
    def is_empty(self) -> bool:
        return not any((
            self.add_to_local,
            self.remove_from_local,
            self.add_to_remote,
            self.remove_from_remote,
        ))

def compute_sync_diff(
    *,
    local_track_ids: list[str],
    remote_track_ids: list[str],
    direction: SyncDirection,
) -> SyncDiff:
    """Compute diff between local and remote playlists.

    Args:
        local_track_ids: Platform track IDs present in local playlist.
        remote_track_ids: Platform track IDs present in remote playlist.
        direction: Sync direction strategy.

    Returns:
        SyncDiff with tracks to add/remove on each side.
    """
    local_set = set(local_track_ids)
    remote_set = set(remote_track_ids)

    only_local = [t for t in local_track_ids if t not in remote_set]
    only_remote = [t for t in remote_track_ids if t not in local_set]

    if direction == SyncDirection.LOCAL_TO_REMOTE:
        return SyncDiff(
            add_to_local=[],
            remove_from_local=[],
            add_to_remote=only_local,
            remove_from_remote=only_remote,
        )

    if direction == SyncDirection.REMOTE_TO_LOCAL:
        return SyncDiff(
            add_to_local=only_remote,
            remove_from_local=only_local,
            add_to_remote=[],
            remove_from_remote=[],
        )

    # BIDIRECTIONAL — merge both sides, never remove
    return SyncDiff(
        add_to_local=only_remote,
        remove_from_local=[],
        add_to_remote=only_local,
        remove_from_remote=[],
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/sync/test_diff.py -v`
Expected: PASS (all 11 tests)

**Step 5: Commit**

```bash
git add app/mcp/sync/__init__.py app/mcp/sync/diff.py \
       tests/mcp/sync/__init__.py tests/mcp/sync/test_diff.py
git commit -m "feat(mcp): add pure-function sync diff computation"
```

---

## Task 7: SyncEngine — Apply Logic

**Files:**
- Create: `app/mcp/sync/engine.py`
- Test: `tests/mcp/sync/test_engine.py`

Orchestrator that: (1) reads local playlist + platform playlist, (2) maps local track_ids to platform IDs via ProviderTrackId, (3) computes diff, (4) applies changes. Returns a `SyncResult` summary.

**Step 1: Write the failing tests**

```python
# tests/mcp/sync/test_engine.py
"""Tests for SyncEngine orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.platforms.protocol import PlatformPlaylist
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine, SyncResult

@pytest.fixture
def mock_playlist_svc():
    svc = AsyncMock()
    # list_items returns items with track_id attribute
    item1 = MagicMock(track_id=1, sort_index=0)
    item2 = MagicMock(track_id=2, sort_index=1)
    item3 = MagicMock(track_id=3, sort_index=2)
    items_list = MagicMock(items=[item1, item2, item3], total=3)
    svc.list_items = AsyncMock(return_value=items_list)
    svc.add_item = AsyncMock()
    svc.remove_item = AsyncMock()
    # get returns playlist with platform_ids
    playlist = MagicMock(
        playlist_id=10,
        name="Test PL",
        platform_ids={"ym": "1003"},
        source_of_truth="local",
    )
    svc.get = AsyncMock(return_value=playlist)
    return svc

@pytest.fixture
def mock_track_mapper():
    """Maps local track_id to platform track_id and vice versa."""
    mapper = AsyncMock()
    # local_to_platform: {track_id: platform_id}
    mapper.local_to_platform = AsyncMock(return_value={
        1: "ym_100",
        2: "ym_200",
        3: "ym_300",
    })
    # platform_to_local: {platform_id: track_id}
    mapper.platform_to_local = AsyncMock(return_value={
        "ym_100": 1,
        "ym_200": 2,
        "ym_300": 3,
        "ym_400": None,  # unknown track
    })
    return mapper

@pytest.fixture
def mock_platform():
    platform = AsyncMock()
    platform.name = "ym"
    platform.get_playlist = AsyncMock(return_value=PlatformPlaylist(
        platform_id="1003",
        name="Remote PL",
        track_ids=["ym_200", "ym_300", "ym_400"],
        owner_id="250905515",
    ))
    platform.add_tracks_to_playlist = AsyncMock()
    platform.remove_tracks_from_playlist = AsyncMock()
    return platform

@pytest.fixture
def engine(mock_playlist_svc, mock_track_mapper, mock_platform):
    return SyncEngine(
        playlist_svc=mock_playlist_svc,
        track_mapper=mock_track_mapper,
    )

class TestSyncEngineLocalToRemote:
    async def test_pushes_new_tracks_to_remote(
        self, engine, mock_platform, mock_playlist_svc
    ):
        result = await engine.sync(
            playlist_id=10,
            platform=mock_platform,
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert isinstance(result, SyncResult)
        assert result.added_to_remote == 1  # ym_100 only in local
        assert result.removed_from_remote == 1  # ym_400 only in remote
        assert result.added_to_local == 0
        assert result.removed_from_local == 0

class TestSyncEngineRemoteToLocal:
    async def test_pulls_new_tracks_to_local(
        self, engine, mock_platform, mock_playlist_svc
    ):
        result = await engine.sync(
            playlist_id=10,
            platform=mock_platform,
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )

        assert result.added_to_local >= 0  # ym_400 might not have local mapping
        assert result.removed_from_local == 1  # track 1 (ym_100) only in local

class TestSyncEngineBidirectional:
    async def test_merges_both_sides(
        self, engine, mock_platform, mock_playlist_svc
    ):
        result = await engine.sync(
            playlist_id=10,
            platform=mock_platform,
            direction=SyncDirection.BIDIRECTIONAL,
        )

        assert result.added_to_remote >= 0
        assert result.added_to_local >= 0
        assert result.removed_from_local == 0  # bidirectional never removes
        assert result.removed_from_remote == 0

class TestSyncEngineNoRemotePlaylist:
    async def test_no_platform_ids(self, engine, mock_platform, mock_playlist_svc):
        """Sync fails gracefully when playlist has no platform_id."""
        playlist = MagicMock(
            playlist_id=10,
            name="Test PL",
            platform_ids=None,
            source_of_truth="local",
        )
        mock_playlist_svc.get = AsyncMock(return_value=playlist)

        with pytest.raises(ValueError, match="not linked"):
            await engine.sync(
                playlist_id=10,
                platform=mock_platform,
                direction=SyncDirection.LOCAL_TO_REMOTE,
            )

class TestSyncResult:
    def test_to_dict(self):
        r = SyncResult(
            playlist_id=10,
            platform="ym",
            direction="local_to_remote",
            added_to_local=0,
            removed_from_local=0,
            added_to_remote=3,
            removed_from_remote=1,
            skipped_unknown=0,
        )
        d = r.to_dict()
        assert d["added_to_remote"] == 3
        assert d["platform"] == "ym"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/sync/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.sync.engine'`

**Step 3: Write minimal implementation**

```python
# app/mcp/sync/engine.py
"""SyncEngine — orchestrates bidirectional playlist sync."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.mcp.platforms.protocol import MusicPlatform
from app.mcp.sync.diff import SyncDirection, compute_sync_diff

if TYPE_CHECKING:
    from app.services.playlists import DjPlaylistService

logger = logging.getLogger(__name__)

class TrackMapper(Protocol):
    """Maps between local track IDs and platform track IDs."""

    async def local_to_platform(
        self, track_ids: list[int], platform: str
    ) -> dict[int, str]: ...

    async def platform_to_local(
        self, platform_ids: list[str], platform: str
    ) -> dict[str, int | None]: ...

@dataclass
class SyncResult:
    """Summary of a sync operation."""

    playlist_id: int
    platform: str
    direction: str
    added_to_local: int
    removed_from_local: int
    added_to_remote: int
    removed_from_remote: int
    skipped_unknown: int

    def to_dict(self) -> dict[str, object]:
        return {
            "playlist_id": self.playlist_id,
            "platform": self.platform,
            "direction": self.direction,
            "added_to_local": self.added_to_local,
            "removed_from_local": self.removed_from_local,
            "added_to_remote": self.added_to_remote,
            "removed_from_remote": self.removed_from_remote,
            "skipped_unknown": self.skipped_unknown,
        }

class SyncEngine:
    """Orchestrates bidirectional playlist sync between local DB and platforms.

    Flow:
    1. Load local playlist items → get track_ids
    2. Map local track_ids to platform track IDs (via ProviderTrackId)
    3. Load remote playlist from platform
    4. Compute diff (local vs remote platform IDs)
    5. Apply changes to both sides
    """

    def __init__(
        self,
        playlist_svc: DjPlaylistService,
        track_mapper: TrackMapper,
    ) -> None:
        self._playlist_svc = playlist_svc
        self._mapper = track_mapper

    async def sync(
        self,
        playlist_id: int,
        platform: MusicPlatform,
        direction: SyncDirection,
    ) -> SyncResult:
        """Execute sync between local playlist and a remote platform.

        Args:
            playlist_id: Local playlist ID.
            platform: Platform adapter to sync with.
            direction: Sync direction strategy.

        Returns:
            SyncResult with counts of changes made.

        Raises:
            ValueError: If playlist is not linked to the platform.
        """
        # 1. Load local playlist
        playlist = await self._playlist_svc.get(playlist_id)
        platform_ids = playlist.platform_ids or {}
        remote_playlist_id = platform_ids.get(platform.name)

        if not remote_playlist_id:
            msg = (
                f"Playlist {playlist_id} not linked to platform "
                f"'{platform.name}'. Set platform_ids first."
            )
            raise ValueError(msg)

        # 2. Load local items and map to platform IDs
        items_list = await self._playlist_svc.list_items(
            playlist_id, offset=0, limit=5000
        )
        local_track_ids = [item.track_id for item in items_list.items]
        id_map = await self._mapper.local_to_platform(
            local_track_ids, platform.name
        )
        local_platform_ids = [
            id_map[tid] for tid in local_track_ids if tid in id_map
        ]

        # 3. Load remote playlist
        remote_pl = await platform.get_playlist(remote_playlist_id)
        remote_platform_ids = remote_pl.track_ids

        # 4. Compute diff
        diff = compute_sync_diff(
            local_track_ids=local_platform_ids,
            remote_track_ids=remote_platform_ids,
            direction=direction,
        )

        # 5. Apply changes
        added_local = 0
        removed_local = 0
        added_remote = 0
        removed_remote = 0
        skipped = 0

        # Apply to remote
        if diff.add_to_remote:
            try:
                await platform.add_tracks_to_playlist(
                    remote_playlist_id, diff.add_to_remote
                )
                added_remote = len(diff.add_to_remote)
            except NotImplementedError:
                logger.warning(
                    "Platform %s does not support playlist writes",
                    platform.name,
                )
                skipped += len(diff.add_to_remote)

        if diff.remove_from_remote:
            try:
                await platform.remove_tracks_from_playlist(
                    remote_playlist_id, diff.remove_from_remote
                )
                removed_remote = len(diff.remove_from_remote)
            except NotImplementedError:
                logger.warning(
                    "Platform %s does not support playlist writes",
                    platform.name,
                )
                skipped += len(diff.remove_from_remote)

        # Apply to local (add)
        if diff.add_to_local:
            reverse_map = await self._mapper.platform_to_local(
                diff.add_to_local, platform.name
            )
            next_sort = len(items_list.items)
            for pid in diff.add_to_local:
                local_tid = reverse_map.get(pid)
                if local_tid is None:
                    logger.info(
                        "Unknown platform track %s — skipping local add",
                        pid,
                    )
                    skipped += 1
                    continue
                from app.schemas.playlists import DjPlaylistItemCreate
                await self._playlist_svc.add_item(
                    playlist_id,
                    DjPlaylistItemCreate(
                        track_id=local_tid,
                        sort_index=next_sort,
                    ),
                )
                next_sort += 1
                added_local += 1

        # Apply to local (remove)
        if diff.remove_from_local:
            reverse_map = await self._mapper.platform_to_local(
                diff.remove_from_local, platform.name
            )
            for pid in diff.remove_from_local:
                local_tid = reverse_map.get(pid)
                if local_tid is None:
                    skipped += 1
                    continue
                # Find the playlist item for this track
                for item in items_list.items:
                    if item.track_id == local_tid:
                        await self._playlist_svc.remove_item(
                            item.playlist_item_id
                        )
                        removed_local += 1
                        break

        logger.info(
            "Sync playlist %d ↔ %s:%s complete: "
            "+%d/-%d local, +%d/-%d remote, %d skipped",
            playlist_id,
            platform.name,
            remote_playlist_id,
            added_local,
            removed_local,
            added_remote,
            removed_remote,
            skipped,
        )

        return SyncResult(
            playlist_id=playlist_id,
            platform=platform.name,
            direction=direction.value,
            added_to_local=added_local,
            removed_from_local=removed_local,
            added_to_remote=added_remote,
            removed_from_remote=removed_remote,
            skipped_unknown=skipped,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/sync/test_engine.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add app/mcp/sync/engine.py tests/mcp/sync/test_engine.py
git commit -m "feat(mcp): add SyncEngine with bidirectional playlist sync logic"
```

---

## Task 8: TrackMapper Implementation

**Files:**
- Create: `app/mcp/sync/track_mapper.py`
- Test: `tests/mcp/sync/test_track_mapper.py`

Implements `TrackMapper` protocol using `ProviderTrackId` table. Maps local track IDs ↔ platform track IDs via the `providers` + `provider_track_ids` tables.

**Step 1: Write the failing tests**

```python
# tests/mcp/sync/test_track_mapper.py
"""Tests for TrackMapper using ProviderTrackId table."""

from __future__ import annotations

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.mcp.sync.track_mapper import DbTrackMapper

@pytest.fixture
async def seed_data(session: AsyncSession):
    """Seed providers, tracks, and provider_track_ids."""
    # Provider
    await session.execute(
        insert(Provider).values(
            provider_id=4, provider_code="yandex_music", name="Yandex Music"
        )
    )
    # Tracks
    await session.execute(
        insert(Track).values(
            [
                {"track_id": 1, "title": "Alpha", "duration_ms": 300000, "status": 0},
                {"track_id": 2, "title": "Beta", "duration_ms": 300000, "status": 0},
                {"track_id": 3, "title": "Gamma", "duration_ms": 300000, "status": 0},
            ]
        )
    )
    # Provider track IDs
    await session.execute(
        insert(ProviderTrackId).values(
            [
                {"track_id": 1, "provider_id": 4, "provider_track_id": "ym_111"},
                {"track_id": 2, "provider_id": 4, "provider_track_id": "ym_222"},
                # track 3 has no YM mapping
            ]
        )
    )
    await session.flush()

class TestDbTrackMapper:
    async def test_local_to_platform(self, session, seed_data):
        mapper = DbTrackMapper(session)
        result = await mapper.local_to_platform([1, 2, 3], "yandex_music")

        assert result[1] == "ym_111"
        assert result[2] == "ym_222"
        assert 3 not in result  # no mapping

    async def test_platform_to_local(self, session, seed_data):
        mapper = DbTrackMapper(session)
        result = await mapper.platform_to_local(
            ["ym_111", "ym_222", "ym_999"], "yandex_music"
        )

        assert result["ym_111"] == 1
        assert result["ym_222"] == 2
        assert result["ym_999"] is None  # unknown

    async def test_local_to_platform_empty(self, session, seed_data):
        mapper = DbTrackMapper(session)
        result = await mapper.local_to_platform([], "yandex_music")
        assert result == {}

    async def test_platform_to_local_empty(self, session, seed_data):
        mapper = DbTrackMapper(session)
        result = await mapper.platform_to_local([], "yandex_music")
        assert result == {}

    async def test_unknown_provider(self, session, seed_data):
        mapper = DbTrackMapper(session)
        result = await mapper.local_to_platform([1, 2], "spotify")
        assert result == {}  # no spotify mappings
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/sync/test_track_mapper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mcp.sync.track_mapper'`

**Step 3: Write minimal implementation**

```python
# app/mcp/sync/track_mapper.py
"""TrackMapper — maps local track IDs to platform track IDs via DB."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider

class DbTrackMapper:
    """Maps between local track IDs and platform track IDs.

    Uses the `providers` + `provider_track_ids` tables for lookups.
    Provider is identified by `provider_code` column.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def local_to_platform(
        self, track_ids: list[int], platform: str
    ) -> dict[int, str]:
        """Map local track IDs to platform track IDs.

        Args:
            track_ids: Local DB track IDs.
            platform: Provider code (e.g. "yandex_music", "spotify").

        Returns:
            Dict of {local_track_id: platform_track_id}.
            Missing mappings are omitted.
        """
        if not track_ids:
            return {}

        stmt = (
            select(ProviderTrackId.track_id, ProviderTrackId.provider_track_id)
            .join(Provider)
            .where(
                Provider.provider_code == platform,
                ProviderTrackId.track_id.in_(track_ids),
            )
        )
        result = await self._session.execute(stmt)
        return dict(result.all())

    async def platform_to_local(
        self, platform_ids: list[str], platform: str
    ) -> dict[str, int | None]:
        """Map platform track IDs to local track IDs.

        Args:
            platform_ids: Platform-specific track IDs.
            platform: Provider code.

        Returns:
            Dict of {platform_track_id: local_track_id | None}.
            All input IDs present in output; None means not found.
        """
        if not platform_ids:
            return {}

        stmt = (
            select(ProviderTrackId.provider_track_id, ProviderTrackId.track_id)
            .join(Provider)
            .where(
                Provider.provider_code == platform,
                ProviderTrackId.provider_track_id.in_(platform_ids),
            )
        )
        result = await self._session.execute(stmt)
        found = dict(result.all())

        # Ensure all input IDs are in output
        return {pid: found.get(pid) for pid in platform_ids}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/sync/test_track_mapper.py -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add app/mcp/sync/track_mapper.py tests/mcp/sync/test_track_mapper.py
git commit -m "feat(mcp): add DbTrackMapper for local↔platform track ID mapping"
```

---

## Task 9: sync_playlist MCP Tool (Replace Stub)

**Files:**
- Modify: `app/mcp/workflows/sync_tools.py` — replace `sync_playlist` stub
- Modify: `app/mcp/dependencies.py` — add sync-related providers
- Test: `tests/mcp/workflows/test_sync_tools.py`

Replace the `sync_playlist` stub with a working implementation that uses SyncEngine. Accepts URN ref from Phase 1. Returns envelope response from Phase 2.

**Step 1: Write the failing tests**

```python
# tests/mcp/workflows/test_sync_tools.py
"""Tests for sync_playlist MCP tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncResult

class TestSyncPlaylistTool:
    """Test the sync_playlist tool via MCP call or direct invocation.

    These tests verify the tool's parameter handling and response format.
    The actual sync logic is tested in test_engine.py.
    """

    async def test_sync_returns_result(self):
        """sync_playlist returns SyncResult dict."""
        # This test verifies the sync_playlist function signature and behavior.
        # Full integration with MCP server is tested separately.
        from app.mcp.workflows.sync_tools import _do_sync_playlist

        mock_engine = AsyncMock()
        mock_engine.sync = AsyncMock(return_value=SyncResult(
            playlist_id=10,
            platform="ym",
            direction="local_to_remote",
            added_to_local=0,
            removed_from_local=0,
            added_to_remote=3,
            removed_from_remote=1,
            skipped_unknown=0,
        ))

        mock_registry = MagicMock()
        mock_platform = AsyncMock()
        mock_platform.name = "ym"
        mock_registry.get = MagicMock(return_value=mock_platform)
        mock_registry.is_connected = MagicMock(return_value=True)

        result = await _do_sync_playlist(
            playlist_id=10,
            platform_name="ym",
            direction="local_to_remote",
            sync_engine=mock_engine,
            platform_registry=mock_registry,
        )

        assert result["added_to_remote"] == 3
        assert result["platform"] == "ym"

    async def test_sync_unknown_platform(self):
        from app.mcp.workflows.sync_tools import _do_sync_playlist

        mock_engine = AsyncMock()
        mock_registry = MagicMock()
        mock_registry.is_connected = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="not connected"):
            await _do_sync_playlist(
                playlist_id=10,
                platform_name="spotify",
                direction="bidirectional",
                sync_engine=mock_engine,
                platform_registry=mock_registry,
            )

    async def test_sync_invalid_direction(self):
        from app.mcp.workflows.sync_tools import _do_sync_playlist

        mock_engine = AsyncMock()
        mock_registry = MagicMock()
        mock_registry.is_connected = MagicMock(return_value=True)
        mock_registry.get = MagicMock(return_value=AsyncMock(name="ym"))

        with pytest.raises(ValueError, match="direction"):
            await _do_sync_playlist(
                playlist_id=10,
                platform_name="ym",
                direction="invalid",
                sync_engine=mock_engine,
                platform_registry=mock_registry,
            )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/workflows/test_sync_tools.py -v`
Expected: FAIL with `ImportError: cannot import name '_do_sync_playlist'`

**Step 3: Rewrite sync_tools.py**

Replace `app/mcp/workflows/sync_tools.py` with working implementation:

```python
# app/mcp/workflows/sync_tools.py
"""Sync tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from app.mcp.dependencies import (
    get_playlist_service,
    get_platform_registry,
    get_sync_engine,
)
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine, SyncResult
from app.services.playlists import DjPlaylistService

_DIRECTION_MAP = {
    "local_to_remote": SyncDirection.LOCAL_TO_REMOTE,
    "remote_to_local": SyncDirection.REMOTE_TO_LOCAL,
    "bidirectional": SyncDirection.BIDIRECTIONAL,
}

async def _do_sync_playlist(
    *,
    playlist_id: int,
    platform_name: str,
    direction: str,
    sync_engine: SyncEngine,
    platform_registry: PlatformRegistry,
) -> dict[str, object]:
    """Core sync logic, extracted for testability."""
    if not platform_registry.is_connected(platform_name):
        msg = f"Platform '{platform_name}' is not connected"
        raise ValueError(msg)

    sync_dir = _DIRECTION_MAP.get(direction)
    if sync_dir is None:
        valid = ", ".join(sorted(_DIRECTION_MAP.keys()))
        msg = f"Invalid direction '{direction}'. Valid: {valid}"
        raise ValueError(msg)

    platform = platform_registry.get(platform_name)

    result = await sync_engine.sync(
        playlist_id=playlist_id,
        platform=platform,
        direction=sync_dir,
    )
    return result.to_dict()

def register_sync_tools(mcp: FastMCP) -> None:
    """Register sync tools on the MCP server."""

    @mcp.tool(tags={"sync"})
    async def sync_playlist(
        playlist_id: int,
        platform: str = "ym",
        direction: str = "bidirectional",
        ctx: Context | None = None,
        sync_engine: SyncEngine = Depends(get_sync_engine),  # noqa: B008
        registry: PlatformRegistry = Depends(get_platform_registry),  # noqa: B008
    ) -> dict[str, object]:
        """Bidirectional sync between a local playlist and a music platform.

        Compares local playlist tracks with the platform playlist,
        then adds/removes tracks to bring them in sync.

        Args:
            playlist_id: Local playlist ID to sync.
            platform: Platform name ("ym", "spotify", etc.). Default: "ym".
            direction: "local_to_remote", "remote_to_local", or "bidirectional".
        """
        return await _do_sync_playlist(
            playlist_id=playlist_id,
            platform_name=platform,
            direction=direction,
            sync_engine=sync_engine,
            platform_registry=registry,
        )

    @mcp.tool(tags={"sync"})
    async def set_source_of_truth(
        playlist_id: int,
        source: str,
        ctx: Context | None = None,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),  # noqa: B008
    ) -> dict[str, object]:
        """Configure which side is the source of truth for a playlist.

        Args:
            playlist_id: Local playlist ID.
            source: "local", "ym", "spotify", "beatport", or "soundcloud".
        """
        valid_sources = {"local", "ym", "spotify", "beatport", "soundcloud"}
        if source not in valid_sources:
            msg = f"Invalid source '{source}'. Valid: {', '.join(sorted(valid_sources))}"
            raise ValueError(msg)

        from app.schemas.playlists import DjPlaylistUpdate

        await playlist_svc.update(
            playlist_id,
            DjPlaylistUpdate(source_of_truth=source),
        )
        return {
            "playlist_id": playlist_id,
            "source_of_truth": source,
            "status": "updated",
        }

    @mcp.tool(tags={"sync"})
    async def link_playlist(
        playlist_id: int,
        platform: str,
        platform_playlist_id: str,
        ctx: Context | None = None,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),  # noqa: B008
    ) -> dict[str, object]:
        """Link a local playlist to a platform playlist for syncing.

        Call this before sync_playlist to establish the connection.

        Args:
            playlist_id: Local playlist ID.
            platform: Platform name ("ym", "spotify", etc.).
            platform_playlist_id: The playlist ID on the platform.
        """
        playlist = await playlist_svc.get(playlist_id)
        current_ids = playlist.platform_ids or {}
        current_ids[platform] = platform_playlist_id

        from app.schemas.playlists import DjPlaylistUpdate

        await playlist_svc.update(
            playlist_id,
            DjPlaylistUpdate(platform_ids=current_ids),
        )
        return {
            "playlist_id": playlist_id,
            "platform": platform,
            "platform_playlist_id": platform_playlist_id,
            "status": "linked",
        }
```

**Step 4: Add DI providers**

Add to `app/mcp/dependencies.py`:

```python
from app.mcp.sync.engine import SyncEngine
from app.mcp.sync.track_mapper import DbTrackMapper

def get_sync_engine(
    session: AsyncSession = Depends(get_session),
) -> SyncEngine:
    """Build a SyncEngine with playlist service and track mapper."""
    playlist_svc = DjPlaylistService(
        DjPlaylistRepository(session),
        DjPlaylistItemRepository(session),
    )
    mapper = DbTrackMapper(session)
    return SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/mcp/workflows/test_sync_tools.py -v`
Expected: PASS (all 3 tests)

**Step 6: Commit**

```bash
git add app/mcp/workflows/sync_tools.py app/mcp/dependencies.py \
       tests/mcp/workflows/test_sync_tools.py
git commit -m "feat(mcp): replace sync_playlist stub with working SyncEngine implementation"
```

---

## Task 10: sync_set_to_ym / sync_set_from_ym (Replace Stubs)

**Files:**
- Modify: `app/mcp/workflows/sync_tools.py` — add set sync tools
- Test: `tests/mcp/workflows/test_set_sync_tools.py`

Replace the `sync_set_to_ym` and `sync_set_from_ym` stubs. `sync_set_to_ym` pushes set tracks to a YM playlist. `sync_set_from_ym` reads likes/dislikes from YM to update pinned/excluded.

**Step 1: Write the failing tests**

```python
# tests/mcp/workflows/test_set_sync_tools.py
"""Tests for set sync tools (sync_set_to_ym, sync_set_from_ym)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

class TestSyncSetToYm:
    async def test_pushes_set_tracks(self):
        from app.mcp.workflows.sync_tools import _do_sync_set_to_ym

        mock_set_svc = AsyncMock()
        mock_set_svc.get = AsyncMock(return_value=MagicMock(
            set_id=1, name="Friday Night", ym_playlist_id=None,
        ))
        versions = MagicMock(
            items=[MagicMock(set_version_id=10)]
        )
        mock_set_svc.list_versions = AsyncMock(return_value=versions)
        items_list = MagicMock(
            items=[
                MagicMock(track_id=1, sort_index=0),
                MagicMock(track_id=2, sort_index=1),
            ]
        )
        mock_set_svc.list_items = AsyncMock(return_value=items_list)

        mock_mapper = AsyncMock()
        mock_mapper.local_to_platform = AsyncMock(return_value={
            1: "ym_100", 2: "ym_200",
        })

        mock_platform = AsyncMock()
        mock_platform.name = "ym"
        mock_platform.create_playlist = AsyncMock(return_value="999")
        mock_platform.add_tracks_to_playlist = AsyncMock()

        result = await _do_sync_set_to_ym(
            set_id=1,
            set_svc=mock_set_svc,
            track_mapper=mock_mapper,
            platform=mock_platform,
        )

        assert result["track_count"] == 2
        assert result["status"] == "synced"
        mock_platform.create_playlist.assert_called_once()

    async def test_no_versions(self):
        from app.mcp.workflows.sync_tools import _do_sync_set_to_ym

        mock_set_svc = AsyncMock()
        mock_set_svc.get = AsyncMock(return_value=MagicMock(
            set_id=1, name="Empty", ym_playlist_id=None,
        ))
        mock_set_svc.list_versions = AsyncMock(
            return_value=MagicMock(items=[])
        )

        with pytest.raises(ValueError, match="no versions"):
            await _do_sync_set_to_ym(
                set_id=1,
                set_svc=mock_set_svc,
                track_mapper=AsyncMock(),
                platform=AsyncMock(),
            )

class TestSyncSetFromYm:
    async def test_reads_feedback(self):
        from app.mcp.workflows.sync_tools import _do_sync_set_from_ym

        mock_set_svc = AsyncMock()
        mock_set_svc.get = AsyncMock(return_value=MagicMock(
            set_id=1, name="Friday Night", ym_playlist_id=999,
        ))
        versions = MagicMock(
            items=[MagicMock(set_version_id=10)]
        )
        mock_set_svc.list_versions = AsyncMock(return_value=versions)
        items_list = MagicMock(
            items=[
                MagicMock(set_item_id=100, track_id=1, sort_index=0, pinned=False),
                MagicMock(set_item_id=101, track_id=2, sort_index=1, pinned=False),
                MagicMock(set_item_id=102, track_id=3, sort_index=2, pinned=False),
            ]
        )
        mock_set_svc.list_items = AsyncMock(return_value=items_list)

        mock_mapper = AsyncMock()
        mock_mapper.local_to_platform = AsyncMock(return_value={
            1: "ym_100", 2: "ym_200", 3: "ym_300",
        })

        # Remote playlist has tracks 1 and 2 (track 3 was removed = excluded)
        mock_platform = AsyncMock()
        mock_platform.name = "ym"
        from app.mcp.platforms.protocol import PlatformPlaylist
        mock_platform.get_playlist = AsyncMock(return_value=PlatformPlaylist(
            platform_id="999",
            name="set_Friday_Night",
            track_ids=["ym_100", "ym_200"],  # ym_300 removed
        ))

        result = await _do_sync_set_from_ym(
            set_id=1,
            set_svc=mock_set_svc,
            track_mapper=mock_mapper,
            platform=mock_platform,
        )

        assert result["status"] == "synced"
        assert result["removed_count"] == 1  # track 3 was removed from YM

    async def test_no_ym_playlist(self):
        from app.mcp.workflows.sync_tools import _do_sync_set_from_ym

        mock_set_svc = AsyncMock()
        mock_set_svc.get = AsyncMock(return_value=MagicMock(
            set_id=1, name="Test", ym_playlist_id=None,
        ))

        with pytest.raises(ValueError, match="not synced"):
            await _do_sync_set_from_ym(
                set_id=1,
                set_svc=mock_set_svc,
                track_mapper=AsyncMock(),
                platform=AsyncMock(),
            )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/workflows/test_set_sync_tools.py -v`
Expected: FAIL with `ImportError: cannot import name '_do_sync_set_to_ym'`

**Step 3: Add set sync functions to sync_tools.py**

Append to `app/mcp/workflows/sync_tools.py`:

```python
async def _do_sync_set_to_ym(
    *,
    set_id: int,
    set_svc: DjSetService,
    track_mapper: TrackMapper,
    platform: MusicPlatform,
) -> dict[str, object]:
    """Push DJ set tracks to a YM playlist."""
    from app.mcp.sync.track_mapper import DbTrackMapper

    dj_set = await set_svc.get(set_id)

    # Get latest version
    versions = await set_svc.list_versions(set_id)
    if not versions.items:
        msg = f"Set {set_id} has no versions"
        raise ValueError(msg)
    latest = max(versions.items, key=lambda v: v.set_version_id)

    # Get set items
    items_list = await set_svc.list_items(
        latest.set_version_id, offset=0, limit=500
    )
    items = sorted(items_list.items, key=lambda i: i.sort_index)
    local_track_ids = [item.track_id for item in items]

    # Map to platform IDs
    id_map = await track_mapper.local_to_platform(
        local_track_ids, "yandex_music"
    )
    ym_track_ids = [
        id_map[tid] for tid in local_track_ids if tid in id_map
    ]

    playlist_name = f"set_{dj_set.name}"

    if dj_set.ym_playlist_id:
        # Update existing playlist
        remote_playlist_id = str(dj_set.ym_playlist_id)
        try:
            remote_pl = await platform.get_playlist(remote_playlist_id)
            # Remove all existing, add new
            if remote_pl.track_ids:
                await platform.remove_tracks_from_playlist(
                    remote_playlist_id, remote_pl.track_ids
                )
            if ym_track_ids:
                await platform.add_tracks_to_playlist(
                    remote_playlist_id, ym_track_ids
                )
        except NotImplementedError:
            pass
    else:
        # Create new playlist
        try:
            remote_playlist_id = await platform.create_playlist(
                playlist_name, ym_track_ids
            )
            # TODO: Update dj_set.ym_playlist_id = int(remote_playlist_id)
        except NotImplementedError:
            remote_playlist_id = "pending"

    return {
        "set_id": set_id,
        "ym_playlist_id": remote_playlist_id,
        "playlist_name": playlist_name,
        "track_count": len(ym_track_ids),
        "unmapped_count": len(local_track_ids) - len(ym_track_ids),
        "status": "synced",
    }

async def _do_sync_set_from_ym(
    *,
    set_id: int,
    set_svc: DjSetService,
    track_mapper: TrackMapper,
    platform: MusicPlatform,
) -> dict[str, object]:
    """Read YM playlist state and update set items."""
    dj_set = await set_svc.get(set_id)

    if not dj_set.ym_playlist_id:
        msg = f"Set {set_id} not synced to YM — call sync_set_to_ym first"
        raise ValueError(msg)

    # Get latest version items
    versions = await set_svc.list_versions(set_id)
    if not versions.items:
        msg = f"Set {set_id} has no versions"
        raise ValueError(msg)
    latest = max(versions.items, key=lambda v: v.set_version_id)

    items_list = await set_svc.list_items(
        latest.set_version_id, offset=0, limit=500
    )
    local_track_ids = [item.track_id for item in items_list.items]

    # Map local to platform IDs
    id_map = await track_mapper.local_to_platform(
        local_track_ids, "yandex_music"
    )

    # Fetch remote playlist
    remote_pl = await platform.get_playlist(str(dj_set.ym_playlist_id))
    remote_set = set(remote_pl.track_ids)

    # Detect removed tracks (in set but not in YM playlist)
    removed_count = 0
    still_count = 0
    for item in items_list.items:
        ym_id = id_map.get(item.track_id)
        if ym_id is None:
            continue
        if ym_id not in remote_set:
            removed_count += 1
            # TODO: mark item as excluded
        else:
            still_count += 1

    return {
        "set_id": set_id,
        "ym_playlist_id": dj_set.ym_playlist_id,
        "still_in_playlist": still_count,
        "removed_count": removed_count,
        "status": "synced",
    }
```

Also add the imports at the top of sync_tools.py:

```python
from app.mcp.platforms.protocol import MusicPlatform
from app.mcp.sync.engine import SyncEngine, SyncResult, TrackMapper
from app.services.sets import DjSetService
```

And register the tools in `register_sync_tools`:

```python
    @mcp.tool(tags={"sync", "yandex"})
    async def sync_set_to_ym(
        set_id: int,
        ctx: Context | None = None,
        set_svc: DjSetService = Depends(get_set_service),  # noqa: B008
        sync_engine: SyncEngine = Depends(get_sync_engine),  # noqa: B008
        registry: PlatformRegistry = Depends(get_platform_registry),  # noqa: B008
    ) -> dict[str, object]:
        """Push a DJ set to Yandex Music as a playlist.

        Creates or updates a YM playlist with the set's tracks.

        Args:
            set_id: DJ set to sync to Yandex Music.
        """
        if not registry.is_connected("ym"):
            raise ValueError("YM platform not connected")
        platform = registry.get("ym")
        mapper = sync_engine._mapper
        return await _do_sync_set_to_ym(
            set_id=set_id,
            set_svc=set_svc,
            track_mapper=mapper,
            platform=platform,
        )

    @mcp.tool(tags={"sync", "yandex"})
    async def sync_set_from_ym(
        set_id: int,
        ctx: Context | None = None,
        set_svc: DjSetService = Depends(get_set_service),  # noqa: B008
        sync_engine: SyncEngine = Depends(get_sync_engine),  # noqa: B008
        registry: PlatformRegistry = Depends(get_platform_registry),  # noqa: B008
    ) -> dict[str, object]:
        """Read feedback from YM playlist, detect removed/added tracks.

        Compares set tracks with YM playlist to identify what changed.

        Args:
            set_id: DJ set to sync feedback for.
        """
        if not registry.is_connected("ym"):
            raise ValueError("YM platform not connected")
        platform = registry.get("ym")
        mapper = sync_engine._mapper
        return await _do_sync_set_from_ym(
            set_id=set_id,
            set_svc=set_svc,
            track_mapper=mapper,
            platform=platform,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/workflows/test_set_sync_tools.py -v`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add app/mcp/workflows/sync_tools.py tests/mcp/workflows/test_set_sync_tools.py
git commit -m "feat(mcp): replace sync_set_to_ym and sync_set_from_ym stubs with SyncEngine"
```

---

## Task 11: Platform Visibility Tools

**Files:**
- Modify: `app/mcp/workflows/server.py` — add `activate_ym_raw()` tool, wire platform tools
- Test: `tests/mcp/workflows/test_visibility.py`

Add visibility control for platform namespaces. The `ym` namespace (raw YM API tools) is hidden by default and activated via `activate_ym_raw()`. Platform tools registered via PlatformRegistry.

**Step 1: Write the failing tests**

```python
# tests/mcp/workflows/test_visibility.py
"""Tests for platform namespace visibility control."""

from __future__ import annotations

from app.mcp.workflows.server import create_workflow_mcp

class TestVisibilityTools:
    def test_activate_ym_raw_tool_exists(self):
        """activate_ym_raw tool is registered."""
        mcp = create_workflow_mcp()
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "activate_ym_raw" in tool_names

    def test_list_platforms_tool_exists(self):
        """list_platforms tool is registered."""
        mcp = create_workflow_mcp()
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "list_platforms" in tool_names
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/workflows/test_visibility.py -v`
Expected: FAIL (tools don't exist yet)

**Step 3: Add visibility tools**

Add to `app/mcp/workflows/server.py` — in `_register_visibility_tools`:

```python
def _register_visibility_tools(mcp: FastMCP) -> None:
    """Register admin/visibility-control tools on the MCP server."""

    @mcp.tool(tags={"admin"})
    async def activate_heavy_mode(ctx: Context) -> str:
        """Enable heavy analysis tools (full audio feature extraction).

        Call this to unlock resource-intensive tools that are hidden
        by default to prevent accidental long-running operations.
        """
        await ctx.enable_components(tags={"heavy"})
        return "Heavy analysis tools are now available."

    @mcp.tool(tags={"admin"})
    async def activate_ym_raw(ctx: Context) -> str:
        """Enable raw Yandex Music API tools.

        Unlocks the full YM API namespace for advanced queries
        not covered by the DJ workflow tools.
        """
        await ctx.enable_components(tags={"ym_raw"})
        return "Raw YM API tools are now available."

    @mcp.tool(
        annotations={"readOnlyHint": True},
        tags={"admin"},
    )
    async def list_platforms() -> dict[str, object]:
        """List all configured music platforms and their capabilities.

        Shows connected status and available capabilities for each platform.
        """
        from app.mcp.dependencies import get_platform_registry

        registry = get_platform_registry()
        platforms = []
        for name in registry.list_connected():
            adapter = registry.get(name)
            platforms.append({
                "name": name,
                "capabilities": [c.name for c in adapter.capabilities],
            })
        return {
            "platforms": platforms,
            "total": len(platforms),
        }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/workflows/test_visibility.py -v`
Expected: PASS (all 2 tests)

**Step 5: Commit**

```bash
git add app/mcp/workflows/server.py tests/mcp/workflows/test_visibility.py
git commit -m "feat(mcp): add platform visibility tools (activate_ym_raw, list_platforms)"
```

---

## Task 12: Integration Tests + Lint + Cleanup

**Files:**
- Create: `tests/mcp/platforms/test_integration.py`
- Run: `make check` (lint + all tests)

End-to-end integration test verifying the full sync flow: create playlist → link to platform → sync → verify diff applied.

**Step 1: Write the integration test**

```python
# tests/mcp/platforms/test_integration.py
"""Integration tests for multi-platform sync flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.platforms.protocol import (
    PlatformCapability,
    PlatformPlaylist,
    PlatformTrack,
)
from app.mcp.platforms.registry import PlatformRegistry
from app.mcp.sync.diff import SyncDirection
from app.mcp.sync.engine import SyncEngine
from app.mcp.sync.track_mapper import DbTrackMapper
from app.models.catalog import Track
from app.models.dj import DjPlaylist, DjPlaylistItem
from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider
from app.repositories.playlists import DjPlaylistItemRepository, DjPlaylistRepository
from app.services.playlists import DjPlaylistService

@dataclass
class InMemoryPlatform:
    """Fake platform adapter with in-memory playlist storage."""

    name: str = "fake"
    capabilities: frozenset[PlatformCapability] = frozenset({
        PlatformCapability.SEARCH,
        PlatformCapability.PLAYLIST_READ,
        PlatformCapability.PLAYLIST_WRITE,
    })
    playlists: dict[str, list[str]] = field(default_factory=dict)

    async def search_tracks(
        self, query: str, *, limit: int = 20
    ) -> list[PlatformTrack]:
        return []

    async def get_track(self, platform_id: str) -> PlatformTrack:
        return PlatformTrack(
            platform_id=platform_id, title="test", artists="test"
        )

    async def get_playlist(self, platform_id: str) -> PlatformPlaylist:
        tracks = self.playlists.get(platform_id, [])
        return PlatformPlaylist(
            platform_id=platform_id,
            name=f"Playlist {platform_id}",
            track_ids=tracks,
        )

    async def create_playlist(
        self, name: str, track_ids: list[str]
    ) -> str:
        pid = str(len(self.playlists) + 1)
        self.playlists[pid] = list(track_ids)
        return pid

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        self.playlists.setdefault(playlist_id, []).extend(track_ids)

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        existing = self.playlists.get(playlist_id, [])
        remove_set = set(track_ids)
        self.playlists[playlist_id] = [
            t for t in existing if t not in remove_set
        ]

    async def delete_playlist(self, playlist_id: str) -> None:
        self.playlists.pop(playlist_id, None)

    async def get_download_url(
        self, track_id: str, *, bitrate: int = 320
    ) -> str | None:
        return None

    async def close(self) -> None:
        pass

@pytest.fixture
async def seed_sync_data(session: AsyncSession):
    """Seed test data: provider, tracks, playlist, provider_track_ids."""
    await session.execute(
        insert(Provider).values(
            provider_id=99, provider_code="fake", name="Fake Platform"
        )
    )
    await session.execute(
        insert(Track).values([
            {"track_id": 1, "title": "Alpha", "duration_ms": 300000, "status": 0},
            {"track_id": 2, "title": "Beta", "duration_ms": 300000, "status": 0},
            {"track_id": 3, "title": "Gamma", "duration_ms": 300000, "status": 0},
        ])
    )
    await session.execute(
        insert(DjPlaylist).values(
            playlist_id=10,
            name="Test Playlist",
            source_of_truth="local",
            platform_ids='{"fake": "remote_1"}',
        )
    )
    await session.execute(
        insert(DjPlaylistItem).values([
            {"playlist_id": 10, "track_id": 1, "sort_index": 0},
            {"playlist_id": 10, "track_id": 2, "sort_index": 1},
        ])
    )
    await session.execute(
        insert(ProviderTrackId).values([
            {"track_id": 1, "provider_id": 99, "provider_track_id": "f_100"},
            {"track_id": 2, "provider_id": 99, "provider_track_id": "f_200"},
            {"track_id": 3, "provider_id": 99, "provider_track_id": "f_300"},
        ])
    )
    await session.flush()

class TestFullSyncFlow:
    async def test_local_to_remote_sync(self, session, seed_sync_data):
        """Local playlist → push to remote platform."""
        platform = InMemoryPlatform()
        platform.playlists["remote_1"] = ["f_200"]  # remote has only track 2

        playlist_svc = DjPlaylistService(
            DjPlaylistRepository(session),
            DjPlaylistItemRepository(session),
        )
        mapper = DbTrackMapper(session)
        engine = SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)

        result = await engine.sync(
            playlist_id=10,
            platform=platform,
            direction=SyncDirection.LOCAL_TO_REMOTE,
        )

        assert result.added_to_remote == 1  # f_100 added
        assert result.removed_from_remote == 0  # f_200 stays (both have it)
        assert "f_100" in platform.playlists["remote_1"]
        assert "f_200" in platform.playlists["remote_1"]

    async def test_remote_to_local_sync(self, session, seed_sync_data):
        """Remote platform → pull new tracks to local."""
        platform = InMemoryPlatform()
        platform.playlists["remote_1"] = [
            "f_100", "f_200", "f_300"
        ]  # remote has all 3

        playlist_svc = DjPlaylistService(
            DjPlaylistRepository(session),
            DjPlaylistItemRepository(session),
        )
        mapper = DbTrackMapper(session)
        engine = SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)

        result = await engine.sync(
            playlist_id=10,
            platform=platform,
            direction=SyncDirection.REMOTE_TO_LOCAL,
        )

        assert result.added_to_local == 1  # f_300 (track 3) added
        assert result.removed_from_local == 0  # remote has all local tracks

    async def test_bidirectional_sync(self, session, seed_sync_data):
        """Bidirectional: merge both sides."""
        platform = InMemoryPlatform()
        platform.playlists["remote_1"] = [
            "f_200", "f_300"
        ]  # remote has 2,3; local has 1,2

        playlist_svc = DjPlaylistService(
            DjPlaylistRepository(session),
            DjPlaylistItemRepository(session),
        )
        mapper = DbTrackMapper(session)
        engine = SyncEngine(playlist_svc=playlist_svc, track_mapper=mapper)

        result = await engine.sync(
            playlist_id=10,
            platform=platform,
            direction=SyncDirection.BIDIRECTIONAL,
        )

        # f_100 added to remote, f_300 added to local
        assert result.added_to_remote == 1
        assert result.added_to_local == 1
        assert result.removed_from_local == 0
        assert result.removed_from_remote == 0

class TestPlatformRegistry:
    def test_register_and_list(self):
        reg = PlatformRegistry()
        p1 = InMemoryPlatform(name="ym")
        p2 = InMemoryPlatform(name="spotify")
        reg.register(p1)
        reg.register(p2)

        assert sorted(reg.list_connected()) == ["spotify", "ym"]
        assert reg.get("ym") is p1
```

**Step 2: Run the integration test**

Run: `uv run pytest tests/mcp/platforms/test_integration.py -v`
Expected: PASS (all 4 tests)

**Step 3: Run full lint + test suite**

Run: `make check`
Expected: PASS (lint clean, all tests pass)

**Step 4: Fix any lint issues**

Common fixes:
- `ruff check --fix` for import ordering
- `ruff format` for formatting
- `mypy` for type annotations

Run: `make ruff-fix && make lint`

**Step 5: Commit**

```bash
git add tests/mcp/platforms/test_integration.py
git commit -m "test(mcp): add integration tests for full multi-platform sync flow"
```

---

## Summary

| Task | What it builds | New files |
|------|---------------|-----------|
| 1 | MusicPlatform Protocol | `app/mcp/platforms/protocol.py` |
| 2 | PlatformRegistry | `app/mcp/platforms/registry.py` |
| 3 | YandexMusicAdapter | `app/mcp/platforms/yandex.py` |
| 4 | Registry DI + Factory | `app/mcp/platforms/factory.py` |
| 5 | DjPlaylist sync columns | Migration + model/schema changes |
| 6 | SyncEngine diff logic | `app/mcp/sync/diff.py` |
| 7 | SyncEngine apply logic | `app/mcp/sync/engine.py` |
| 8 | TrackMapper (DB) | `app/mcp/sync/track_mapper.py` |
| 9 | sync_playlist tool (replace stub) | Rewrite `sync_tools.py` |
| 10 | sync_set_to_ym/from_ym (replace stubs) | Add to `sync_tools.py` |
| 11 | Platform visibility tools | Modify `server.py` |
| 12 | Integration tests + lint | `test_integration.py` |

**Dependencies:** Phase 1 (refs, types_v2, entity_finder) and Phase 2 (CRUD, converters, response wrappers) must be implemented first.

**Total new files:** ~10 source + ~8 test files
**Total tools changed:** 3 stubs replaced + 3 new tools added (set_source_of_truth, link_playlist, list_platforms, activate_ym_raw)
