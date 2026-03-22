# Yandex Music API Endpoints — Implementation Plan v2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Полноценная интеграция с Yandex Music через REST API — поиск, линковка, обогащение метаданных (жанр, артисты, лейбл, релиз), пакетный импорт.

**Architecture:** Новый HTTP-клиент `YandexMusicClient` в `app/clients/`, сервис-оркестратор `YandexMusicEnrichmentService` (multi-repo pattern), роутер `/api/v1/yandex-music/`. Всё по паттерну Router → Service → Repository → Model.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, httpx, Pydantic v2. Существующие модели catalog (Artist, Genre, Label, Release, Track*).

---

## Проблемы из реального рабочего процесса

Обогащение 118 треков через ad-hoc скрипт выявило:

| # | Проблема | Где упало | Исправление в плане |
|---|----------|-----------|---------------------|
| 1 | MCP сервер `ym_search` → "Authentication failed" | MCP `env_file=".env"` от CWD=`/` | Task 1: фикс config.py |
| 2 | `providers.provider_id` — SMALLINT без autoincrement | `INSERT INTO providers` без ID | Task 2: seed provider + repo с явным ID |
| 3 | `track_artists.role` — SMALLINT enum (0-2), не текст | `CHECK constraint failed: ck_track_artists_role` | Task 5: использовать `ArtistRole.PRIMARY = 0` |
| 4 | Пустой `album.labels: []` у некоторых треков | `IndexError: list index out of range` | Task 5: null-safe парсинг |
| 5 | SQLite `database is locked` при параллельных записях | Анализ + обогащение одновременно | Task 7: документировать ограничение, sequential |
| 6 | Нет эндпоинтов для обогащения — только ad-hoc скрипты | Весь workflow через `/tmp/*.py` | Tasks 4-7: полноценные API endpoints |
| 7 | `AnalysisRequest.audio_path` обязателен, но нигде не хранится | `422 Field required` при curl без body | Task 8: endpoint для поиска audio_path |

---

## Task 1: Fix MCP Server Auth

**Files:**
- Modify: `yandex_music_mcp/yandex_music_mcp/config.py`

**Step 1: Write the fix**

```python
# yandex_music_mcp/yandex_music_mcp/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from project root, not CWD
_PKG_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PKG_DIR.parent.parent  # yandex_music_mcp/ → project root
_ENV_FILE = _PROJECT_ROOT / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YANDEX_MUSIC_",
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    token: str = ""
    user_id: str = ""
    base_url: str = "https://api.music.yandex.net:443"
    timeout: int = 30
    language: str = "ru"
```

**Step 2: Verify from arbitrary CWD**

Run: `cd / && uv run python -c "from yandex_music_mcp.config import Settings; s=Settings(); print(bool(s.token))"`
Expected: `True`

**Step 3: Commit**

```bash
git add yandex_music_mcp/yandex_music_mcp/config.py
git commit -m "fix(mcp): resolve .env from package dir, not CWD"
```

---

## Task 2: App Config + Yandex Provider Seed

**Files:**
- Modify: `app/config.py` — add `yandex_music_token`, `yandex_music_base_url`
- Create: `app/repositories/providers.py` — ProviderRepository
- Test: `tests/test_providers_repo.py`

**Step 1: Write the failing test**

```python
# tests/test_providers_repo.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.providers import ProviderRepository

async def test_get_or_create_provider(session: AsyncSession) -> None:
    repo = ProviderRepository(session)
    p = await repo.get_or_create(provider_id=4, code="yandex_music", name="Yandex Music")
    assert p.provider_id == 4
    assert p.provider_code == "yandex_music"

    # Idempotent — second call returns same
    p2 = await repo.get_or_create(provider_id=4, code="yandex_music", name="Yandex Music")
    assert p2.provider_id == p.provider_id
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_providers_repo.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# app/repositories/providers.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.providers import Provider

class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_code(self, code: str) -> Provider | None:
        stmt = select(Provider).where(Provider.provider_code == code)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(
        self, *, provider_id: int, code: str, name: str
    ) -> Provider:
        existing = await self.get_by_code(code)
        if existing:
            return existing
        p = Provider(provider_id=provider_id, provider_code=code, name=name)
        self.session.add(p)
        await self.session.flush()
        return p
```

Add to `app/config.py`:

```python
yandex_music_token: str = ""
yandex_music_base_url: str = "https://api.music.yandex.net:443"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_providers_repo.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/config.py app/repositories/providers.py tests/test_providers_repo.py
git commit -m "feat: add ProviderRepository + YM config settings"
```

---

## Task 3: YandexMusicClient (HTTP wrapper)

**Files:**
- Create: `app/clients/__init__.py`
- Create: `app/clients/yandex_music.py`
- Test: `tests/test_ym_client.py`

Переиспользует паттерн из `yandex_music_mcp/client.py`, но адаптирован для app-контекста (без MCP, с настройками из `app/config.py`).

**Step 1: Write the failing test**

```python
# tests/test_ym_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.clients.yandex_music import YandexMusicClient

async def test_search_tracks() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "tracks": {
                "results": [
                    {
                        "id": 103119407,
                        "title": "Octopus Neuroplasticity",
                        "artists": [{"id": 3976138, "name": "Jouska", "various": False}],
                        "albums": [{
                            "id": 36081872,
                            "title": "Techgnosis, Vol. 6",
                            "genre": "techno",
                            "labels": ["Techgnosis"],
                            "releaseDate": "2022-03-21T00:00:00+03:00",
                            "year": 2022,
                        }],
                    }
                ]
            }
        }
    }

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp

    client = YandexMusicClient(token="test", http_client=mock_http)
    results = await client.search_tracks("Jouska Octopus Neuroplasticity")

    assert len(results) == 1
    assert results[0]["id"] == 103119407

async def test_fetch_track_metadata() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": [
            {
                "id": 103119407,
                "title": "Octopus Neuroplasticity",
                "artists": [{"id": 3976138, "name": "Jouska"}],
                "albums": [{"genre": "techno", "labels": []}],
            }
        ]
    }
    mock_http = AsyncMock()
    mock_http.post.return_value = mock_resp

    client = YandexMusicClient(token="test", http_client=mock_http)
    data = await client.fetch_tracks(["103119407"])
    assert "103119407" in data
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ym_client.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# app/clients/yandex_music.py
"""Yandex Music API HTTP client for the DJ Set Builder backend."""

from __future__ import annotations

from typing import Any

import httpx

_DEFAULT_BASE = "https://api.music.yandex.net:443"

class YandexMusicClient:
    """Thin async wrapper around Yandex Music REST API."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = _DEFAULT_BASE,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base = base_url
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"OAuth {self._token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        client = await self._client()
        resp = await client.get(
            f"{self._base}{path}", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def _post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        resp = await client.post(
            f"{self._base}{path}", headers=self._headers(), data=data
        )
        resp.raise_for_status()
        return resp.json()

    # --- Public API ---

    async def search_tracks(self, query: str, *, page: int = 0) -> list[dict[str, Any]]:
        data = await self._get("/search", text=query, type="track", page=page)
        return data.get("result", {}).get("tracks", {}).get("results", [])

    async def fetch_tracks(self, track_ids: list[str]) -> dict[str, dict[str, Any]]:
        data = await self._post_form("/tracks", {"track-ids": ",".join(track_ids)})
        return {str(t["id"]): t for t in data.get("result", [])}

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ym_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/clients/__init__.py app/clients/yandex_music.py tests/test_ym_client.py
git commit -m "feat: add YandexMusicClient HTTP wrapper"
```

---

## Task 4: Enrichment Schemas

**Files:**
- Create: `app/schemas/yandex_music.py`
- Test: `tests/test_schemas_ym.py`

**Step 1: Write the failing test**

```python
# tests/test_schemas_ym.py
from app.schemas.yandex_music import (
    YmSearchRequest,
    YmSearchResult,
    YmEnrichRequest,
    YmEnrichResponse,
    YmBatchEnrichRequest,
    YmBatchEnrichResponse,
)

def test_search_request() -> None:
    req = YmSearchRequest(query="Jouska Octopus")
    assert req.query == "Jouska Octopus"
    assert req.page == 0

def test_search_result() -> None:
    item = YmSearchResult(
        yandex_track_id="103119407",
        title="Octopus Neuroplasticity",
        artists=["Jouska"],
        album_title="Techgnosis, Vol. 6",
        genre="techno",
        label="Techgnosis",
        duration_ms=347150,
    )
    assert item.yandex_track_id == "103119407"

def test_enrich_request() -> None:
    req = YmEnrichRequest(yandex_track_id="103119407")
    assert req.yandex_track_id == "103119407"

def test_batch_enrich_response() -> None:
    resp = YmBatchEnrichResponse(total=10, enriched=8, skipped=1, failed=1)
    assert resp.total == 10
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas_ym.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# app/schemas/yandex_music.py
from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema

class YmSearchRequest(BaseSchema):
    """Search Yandex Music for a track."""
    query: str = Field(min_length=1, max_length=400)
    page: int = Field(default=0, ge=0)

class YmSearchResult(BaseSchema):
    """A single search result from Yandex Music."""
    yandex_track_id: str
    title: str
    artists: list[str]
    album_title: str | None = None
    genre: str | None = None
    label: str | None = None
    duration_ms: int | None = None
    year: int | None = None
    release_date: str | None = None
    cover_uri: str | None = None

class YmSearchResponse(BaseSchema):
    """Search results from Yandex Music."""
    results: list[YmSearchResult]
    total: int = 0
    page: int = 0

class YmEnrichRequest(BaseSchema):
    """Link and enrich a track from Yandex Music data."""
    yandex_track_id: str

class YmEnrichResponse(BaseSchema):
    """Result of enriching a single track."""
    track_id: int
    yandex_track_id: str
    genre: str | None = None
    artists: list[str] = []
    label: str | None = None
    release_title: str | None = None
    already_linked: bool = False

class YmBatchEnrichRequest(BaseSchema):
    """Batch enrich tracks by auto-searching Yandex Music."""
    track_ids: list[int] = Field(min_length=1, max_length=500)

class YmBatchEnrichResponse(BaseSchema):
    """Result of batch enrichment."""
    total: int
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = []
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas_ym.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/schemas/yandex_music.py tests/test_schemas_ym.py
git commit -m "feat(schemas): add Yandex Music search/enrich request/response schemas"
```

---

## Task 5: Enrichment Service (Multi-Repo Orchestrator)

**Files:**
- Create: `app/services/yandex_music_enrichment.py`
- Test: `tests/test_ym_enrichment_service.py`

Ключевой сервис. Реализует то, что ad-hoc скрипт `/tmp/enrich_from_yandex.py` делал с ошибками:
- Null-safe парсинг `album.labels` (проблема #4)
- `ArtistRole.PRIMARY = 0`, не строка "main" (проблема #3)
- Idempotent: пропускает уже обогащённые треки
- Работает через существующие repos (artist, genre, label, release)

**Step 1: Write the failing test**

```python
# tests/test_ym_enrichment_service.py
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.providers import Provider
from app.services.yandex_music_enrichment import YandexMusicEnrichmentService

async def test_enrich_track_creates_genre_and_artist(session: AsyncSession) -> None:
    """Enrichment creates Genre, Artist, Label, Release, and links them to Track."""
    # Setup: create track and provider
    track = Track(title="Jouska — Octopus Neuroplasticity", duration_ms=347150)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    # Mock YM API response
    ym_track_data = {
        "id": 103119407,
        "title": "Octopus Neuroplasticity",
        "artists": [
            {"id": 3976138, "name": "Jouska", "various": False},
        ],
        "albums": [{
            "id": 36081872,
            "title": "Techgnosis, Vol. 6",
            "genre": "techno",
            "labels": ["Techgnosis"],
            "releaseDate": "2022-03-21T00:00:00+03:00",
            "year": 2022,
            "trackPosition": {"volume": 1, "index": 4},
        }],
    }

    mock_client = AsyncMock()
    mock_client.fetch_tracks.return_value = {"103119407": ym_track_data}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id, yandex_track_id="103119407")

    assert result.genre == "techno"
    assert result.artists == ["Jouska"]
    assert result.label == "Techgnosis"
    assert result.release_title == "Techgnosis, Vol. 6"
    assert not result.already_linked

async def test_enrich_track_empty_labels(session: AsyncSession) -> None:
    """Enrichment handles albums with empty labels array (problem #4)."""
    track = Track(title="Test Track", duration_ms=300000)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    ym_track_data = {
        "id": 999,
        "title": "Test",
        "artists": [{"id": 1, "name": "Artist", "various": False}],
        "albums": [{
            "id": 1,
            "title": "Album",
            "genre": "techno",
            "labels": [],  # <-- empty!
            "year": 2024,
        }],
    }

    mock_client = AsyncMock()
    mock_client.fetch_tracks.return_value = {"999": ym_track_data}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    result = await svc.enrich_track(track.track_id, yandex_track_id="999")
    assert result.label is None  # No crash, label is None

async def test_enrich_track_idempotent(session: AsyncSession) -> None:
    """Second enrichment of same track returns already_linked=True."""
    track = Track(title="Test", duration_ms=300000)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    ym_data = {
        "id": 123,
        "title": "Test",
        "artists": [],
        "albums": [{"id": 1, "title": "A", "genre": "techno", "labels": [], "year": 2024}],
    }
    mock_client = AsyncMock()
    mock_client.fetch_tracks.return_value = {"123": ym_data}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    r1 = await svc.enrich_track(track.track_id, yandex_track_id="123")
    assert not r1.already_linked

    r2 = await svc.enrich_track(track.track_id, yandex_track_id="123")
    assert r2.already_linked
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ym_enrichment_service.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# app/services/yandex_music_enrichment.py
"""Enriches tracks with metadata from Yandex Music API.

Handles: provider linking, genre, artist, label, release creation.
Null-safe for missing album fields (labels, genre, etc.).
Uses ArtistRole.PRIMARY (int 0), not string "main".
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yandex_music import YandexMusicClient
from app.models.catalog import (
    Artist,
    Genre,
    Label,
    Release,
    TrackArtist,
    TrackGenre,
    TrackRelease,
)
from app.models.enums import ArtistRole
from app.models.ingestion import ProviderTrackId
from app.schemas.yandex_music import YmEnrichResponse
from app.services.base import BaseService

_PROVIDER_ID = 4  # yandex_music — see providers seed data

class YandexMusicEnrichmentService(BaseService):
    def __init__(
        self,
        session: AsyncSession,
        ym_client: YandexMusicClient,
    ) -> None:
        super().__init__()
        self.session = session
        self.ym_client = ym_client

    # ------ Public ------

    async def enrich_track(
        self,
        track_id: int,
        *,
        yandex_track_id: str,
    ) -> YmEnrichResponse:
        """Enrich a single track from Yandex Music data."""
        # Check if already linked
        existing = await self._get_provider_link(track_id)
        if existing:
            return YmEnrichResponse(
                track_id=track_id,
                yandex_track_id=existing.provider_track_id,
                already_linked=True,
            )

        # Fetch metadata from YM API
        tracks_data = await self.ym_client.fetch_tracks([yandex_track_id])
        ym_track = tracks_data.get(yandex_track_id)
        if not ym_track:
            msg = f"Track {yandex_track_id} not found on Yandex Music"
            raise ValueError(msg)

        # Create provider link
        self.session.add(ProviderTrackId(
            track_id=track_id,
            provider_id=_PROVIDER_ID,
            provider_track_id=yandex_track_id,
        ))

        # Process artists
        artist_names = await self._process_artists(track_id, ym_track.get("artists", []))

        # Process album (genre, label, release)
        genre_name = None
        label_name = None
        release_title = None
        albums = ym_track.get("albums", [])
        if albums:
            album = albums[0]
            genre_name = await self._process_genre(track_id, album)
            label_name, release_title = await self._process_release(track_id, album)

        await self.session.flush()

        return YmEnrichResponse(
            track_id=track_id,
            yandex_track_id=yandex_track_id,
            genre=genre_name,
            artists=artist_names,
            label=label_name,
            release_title=release_title,
        )

    async def enrich_batch(self, track_ids: list[int]) -> list[YmEnrichResponse]:
        """Enrich multiple tracks by auto-searching YM."""
        # Implementation: for each track, parse "Artist — Title" from track.title,
        # search YM, pick best match, call enrich_track()
        ...

    # ------ Helpers ------

    async def _get_provider_link(self, track_id: int) -> ProviderTrackId | None:
        stmt = select(ProviderTrackId).where(
            ProviderTrackId.track_id == track_id,
            ProviderTrackId.provider_id == _PROVIDER_ID,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _process_artists(
        self, track_id: int, ym_artists: list[dict[str, Any]]
    ) -> list[str]:
        names: list[str] = []
        for ym_a in ym_artists:
            if ym_a.get("various"):
                continue
            name = ym_a["name"]
            names.append(name)
            artist = await self._get_or_create_artist(name)
            # Use ArtistRole.PRIMARY (int 0), NOT string "main"
            await self._link_track_artist(track_id, artist.artist_id, ArtistRole.PRIMARY)
        return names

    async def _process_genre(
        self, track_id: int, album: dict[str, Any]
    ) -> str | None:
        genre_name = album.get("genre")
        if not genre_name:
            return None
        genre = await self._get_or_create_genre(genre_name)
        await self._link_track_genre(track_id, genre.genre_id)
        return genre_name

    async def _process_release(
        self, track_id: int, album: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        # Null-safe labels (problem #4)
        labels = album.get("labels", [])
        label_name = None
        label_id = None
        if labels:
            raw_label = labels[0]
            label_name = raw_label if isinstance(raw_label, str) else raw_label.get("name")
            if label_name:
                label = await self._get_or_create_label(label_name)
                label_id = label.label_id

        release_title = album.get("title")
        if release_title:
            release = await self._get_or_create_release(
                title=release_title,
                label_id=label_id,
                release_date=album.get("releaseDate", "")[:10] if album.get("releaseDate") else None,
                year=album.get("year"),
            )
            track_pos = album.get("trackPosition", {})
            await self._link_track_release(
                track_id, release.release_id,
                track_number=track_pos.get("index"),
                disc_number=track_pos.get("volume"),
            )

        return label_name, release_title

    # ------ get_or_create helpers (all idempotent) ------

    async def _get_or_create_artist(self, name: str) -> Artist:
        stmt = select(Artist).where(Artist.name == name)
        artist = (await self.session.execute(stmt)).scalar_one_or_none()
        if artist:
            return artist
        artist = Artist(name=name)
        self.session.add(artist)
        await self.session.flush()
        return artist

    async def _get_or_create_genre(self, name: str) -> Genre:
        stmt = select(Genre).where(Genre.name == name)
        genre = (await self.session.execute(stmt)).scalar_one_or_none()
        if genre:
            return genre
        genre = Genre(name=name)
        self.session.add(genre)
        await self.session.flush()
        return genre

    async def _get_or_create_label(self, name: str) -> Label:
        stmt = select(Label).where(Label.name == name)
        label = (await self.session.execute(stmt)).scalar_one_or_none()
        if label:
            return label
        label = Label(name=name)
        self.session.add(label)
        await self.session.flush()
        return label

    async def _get_or_create_release(
        self, *, title: str, label_id: int | None, release_date: str | None, year: int | None
    ) -> Release:
        stmt = select(Release).where(Release.title == title)
        release = (await self.session.execute(stmt)).scalar_one_or_none()
        if release:
            return release

        rd = release_date
        precision = "day" if rd else ("year" if year else None)
        if not rd and year:
            rd = f"{year}-01-01"

        release = Release(
            title=title,
            label_id=label_id,
            release_date=rd,
            release_date_precision=precision,
        )
        self.session.add(release)
        await self.session.flush()
        return release

    # ------ link helpers (skip if exists) ------

    async def _link_track_artist(
        self, track_id: int, artist_id: int, role: ArtistRole
    ) -> None:
        stmt = select(TrackArtist).where(
            TrackArtist.track_id == track_id,
            TrackArtist.artist_id == artist_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackArtist(track_id=track_id, artist_id=artist_id, role=role))

    async def _link_track_genre(self, track_id: int, genre_id: int) -> None:
        stmt = select(TrackGenre).where(
            TrackGenre.track_id == track_id,
            TrackGenre.genre_id == genre_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackGenre(
            track_id=track_id,
            genre_id=genre_id,
            source_provider_id=_PROVIDER_ID,
        ))

    async def _link_track_release(
        self, track_id: int, release_id: int, *, track_number: int | None, disc_number: int | None
    ) -> None:
        stmt = select(TrackRelease).where(
            TrackRelease.track_id == track_id,
            TrackRelease.release_id == release_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none():
            return
        self.session.add(TrackRelease(
            track_id=track_id,
            release_id=release_id,
            track_number=track_number,
            disc_number=disc_number,
        ))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ym_enrichment_service.py -v`
Expected: PASS

**Step 5: Lint check**

Run: `uv run ruff check app/services/yandex_music_enrichment.py`

**Step 6: Commit**

```bash
git add app/services/yandex_music_enrichment.py tests/test_ym_enrichment_service.py
git commit -m "feat(services): add YandexMusicEnrichmentService with null-safe parsing"
```

---

## Task 6: Yandex Music Router

**Files:**
- Create: `app/routers/v1/yandex_music.py`
- Modify: `app/routers/v1/__init__.py` — register router
- Test: `tests/test_ym_api.py`

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/yandex-music/search` | Поиск треков в YM |
| POST | `/api/v1/tracks/{track_id}/enrich/yandex-music` | Обогатить один трек по YM track ID |
| POST | `/api/v1/yandex-music/enrich/batch` | Пакетное обогащение (auto-search) |

**Step 1: Write the failing test**

```python
# tests/test_ym_api.py
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.providers import Provider

async def test_search_yandex_music(client: AsyncClient) -> None:
    """POST /api/v1/yandex-music/search returns search results."""
    with patch("app.routers.v1.yandex_music._ym_client") as mock:
        mock.search_tracks = AsyncMock(return_value=[{
            "id": 103119407,
            "title": "Octopus Neuroplasticity",
            "artists": [{"name": "Jouska", "various": False}],
            "albums": [{"title": "Techgnosis", "genre": "techno", "labels": ["Techgnosis"]}],
            "durationMs": 347150,
        }])

        resp = await client.post(
            "/api/v1/yandex-music/search",
            json={"query": "Jouska Octopus"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["yandex_track_id"] == "103119407"

async def test_enrich_track_from_yandex(client: AsyncClient, session: AsyncSession) -> None:
    """POST /api/v1/tracks/{id}/enrich/yandex-music links and enriches."""
    # Create track + provider in test DB
    track = Track(title="Test — Track", duration_ms=300000)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.commit()

    with patch("app.routers.v1.yandex_music._ym_client") as mock:
        mock.fetch_tracks = AsyncMock(return_value={
            "999": {
                "id": 999,
                "title": "Track",
                "artists": [{"name": "Artist", "various": False}],
                "albums": [{"title": "Album", "genre": "techno", "labels": [], "year": 2024}],
            }
        })

        resp = await client.post(
            f"/api/v1/tracks/{track.track_id}/enrich/yandex-music",
            json={"yandex_track_id": "999"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["genre"] == "techno"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ym_api.py -v`
Expected: FAIL — ImportError

**Step 3: Implement router**

```python
# app/routers/v1/yandex_music.py
from __future__ import annotations

from fastapi import APIRouter

from app.clients.yandex_music import YandexMusicClient
from app.config import settings
from app.dependencies import DbSession
from app.routers.v1._openapi import RESPONSES_GET
from app.schemas.yandex_music import (
    YmBatchEnrichRequest,
    YmBatchEnrichResponse,
    YmEnrichRequest,
    YmEnrichResponse,
    YmSearchRequest,
    YmSearchResponse,
    YmSearchResult,
)
from app.services.yandex_music_enrichment import YandexMusicEnrichmentService

router = APIRouter(tags=["yandex-music"])

# Lazy-init client (token from app settings)
_ym_client: YandexMusicClient | None = None

def _get_client() -> YandexMusicClient:
    global _ym_client  # noqa: PLW0603
    if _ym_client is None:
        _ym_client = YandexMusicClient(
            token=settings.yandex_music_token,
            base_url=settings.yandex_music_base_url,
        )
    return _ym_client

def _enrichment_service(db: DbSession) -> YandexMusicEnrichmentService:
    return YandexMusicEnrichmentService(session=db, ym_client=_get_client())

@router.post(
    "/yandex-music/search",
    response_model=YmSearchResponse,
    summary="Search Yandex Music tracks",
    description="Search for tracks on Yandex Music by query string.",
    response_description="List of matching tracks with metadata",
    operation_id="search_yandex_music",
)
async def search_yandex_music(data: YmSearchRequest) -> YmSearchResponse:
    results = await _get_client().search_tracks(data.query, page=data.page)
    items = []
    for r in results:
        artists = [a["name"] for a in r.get("artists", []) if not a.get("various")]
        albums = r.get("albums", [])
        album = albums[0] if albums else {}
        labels = album.get("labels", [])
        label = labels[0] if labels else None
        if isinstance(label, dict):
            label = label.get("name")
        items.append(YmSearchResult(
            yandex_track_id=str(r["id"]),
            title=r.get("title", ""),
            artists=artists,
            album_title=album.get("title"),
            genre=album.get("genre"),
            label=label,
            duration_ms=r.get("durationMs"),
            year=album.get("year"),
            release_date=album.get("releaseDate"),
            cover_uri=r.get("coverUri"),
        ))
    return YmSearchResponse(results=items, total=len(items), page=data.page)

@router.post(
    "/tracks/{track_id}/enrich/yandex-music",
    response_model=YmEnrichResponse,
    summary="Enrich track from Yandex Music",
    description=(
        "Link a track to a Yandex Music track ID and enrich metadata: "
        "genre, artists, label, release. Idempotent — skips if already linked."
    ),
    response_description="Enrichment result with extracted metadata",
    responses=RESPONSES_GET,
    operation_id="enrich_track_yandex_music",
)
async def enrich_track(
    track_id: int,
    data: YmEnrichRequest,
    db: DbSession,
) -> YmEnrichResponse:
    result = await _enrichment_service(db).enrich_track(
        track_id, yandex_track_id=data.yandex_track_id
    )
    await db.commit()
    return result

@router.post(
    "/yandex-music/enrich/batch",
    response_model=YmBatchEnrichResponse,
    summary="Batch enrich tracks from Yandex Music",
    description=(
        "Auto-search and enrich multiple tracks. For each track, parses "
        "'Artist — Title' from track.title, searches YM, enriches with best match."
    ),
    response_description="Aggregate enrichment results",
    operation_id="batch_enrich_yandex_music",
)
async def batch_enrich(
    data: YmBatchEnrichRequest,
    db: DbSession,
) -> YmBatchEnrichResponse:
    svc = _enrichment_service(db)
    total = len(data.track_ids)
    enriched = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    for tid in data.track_ids:
        try:
            # TODO: implement auto-search logic in service
            result = await svc.enrich_batch([tid])
            enriched += 1
        except Exception as e:
            failed += 1
            errors.append(f"Track {tid}: {e}")

    await db.commit()
    return YmBatchEnrichResponse(
        total=total, enriched=enriched, skipped=skipped, failed=failed, errors=errors
    )
```

**Step 4: Register in `__init__.py`**

Add to `app/routers/v1/__init__.py`:
```python
from app.routers.v1 import yandex_music
v1_router.include_router(yandex_music.router)
```

Imports must be alphabetically sorted (ruff I001).

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_ym_api.py -v`
Expected: PASS

**Step 6: Lint**

Run: `uv run ruff check app/routers/v1/yandex_music.py app/routers/v1/__init__.py`

**Step 7: Commit**

```bash
git add app/routers/v1/yandex_music.py app/routers/v1/__init__.py tests/test_ym_api.py
git commit -m "feat(api): add /yandex-music/ search + enrich endpoints"
```

---

## Task 7: Auto-Search Enrichment (batch logic)

**Files:**
- Modify: `app/services/yandex_music_enrichment.py` — implement `enrich_batch`
- Test: `tests/test_ym_enrichment_service.py` — add batch test

The batch method parses "Artist — Title" from `track.title`, searches YM, picks best match, enriches.

**Step 1: Write the failing test**

```python
async def test_enrich_batch_auto_search(session: AsyncSession) -> None:
    """Batch enrichment auto-searches YM by parsing track title."""
    track = Track(title="Jouska — Octopus Neuroplasticity", duration_ms=347150)
    session.add(track)
    provider = Provider(provider_id=4, provider_code="yandex_music", name="Yandex Music")
    session.add(provider)
    await session.flush()

    mock_client = AsyncMock()
    mock_client.search_tracks.return_value = [{
        "id": 103119407,
        "title": "Octopus Neuroplasticity",
        "artists": [{"name": "Jouska", "various": False}],
        "albums": [{"title": "Techgnosis", "genre": "techno", "labels": ["Techgnosis"], "year": 2022}],
    }]
    mock_client.fetch_tracks.return_value = {"103119407": {
        "id": 103119407,
        "title": "Octopus Neuroplasticity",
        "artists": [{"id": 1, "name": "Jouska", "various": False}],
        "albums": [{"id": 1, "title": "Techgnosis", "genre": "techno", "labels": ["Techgnosis"], "year": 2022}],
    }}

    svc = YandexMusicEnrichmentService(session=session, ym_client=mock_client)
    results = await svc.enrich_batch([track.track_id])

    assert len(results) == 1
    assert results[0].genre == "techno"
```

**Step 2: Run — FAIL (method not implemented)**

**Step 3: Implement `enrich_batch`**

Key logic:
1. Load track titles from DB
2. Parse "Artist — Title" format
3. Search YM with parsed query
4. Match by title similarity (fuzzy)
5. Call `enrich_track` with best match's yandex_track_id

**Step 4: Run — PASS**

**Step 5: Commit**

```bash
git add app/services/yandex_music_enrichment.py tests/test_ym_enrichment_service.py
git commit -m "feat(services): implement batch auto-search enrichment from YM"
```

---

## Task 8: Seed Yandex Provider in DB init

**Files:**
- Modify: `app/database.py` — seed provider row on init
- Test: `tests/test_ym_api.py` — verify provider exists after startup

Add to `init_db()`:

```python
async def _seed_providers(session: AsyncSession) -> None:
    """Ensure standard providers exist."""
    from app.repositories.providers import ProviderRepository
    repo = ProviderRepository(session)
    await repo.get_or_create(provider_id=1, code="spotify", name="Spotify")
    await repo.get_or_create(provider_id=2, code="soundcloud", name="SoundCloud")
    await repo.get_or_create(provider_id=3, code="beatport", name="Beatport")
    await repo.get_or_create(provider_id=4, code="yandex_music", name="Yandex Music")
```

**Commit:**

```bash
git commit -m "feat(db): seed standard providers including yandex_music on init"
```

---

## Execution Order & Dependencies

```text
Task 1  (MCP fix)              — standalone
Task 2  (Config + Provider repo) — standalone
Task 3  (YM HTTP client)       — standalone
Task 4  (Schemas)              — standalone
Task 5  (Enrichment service)   — depends on 2, 3, 4
Task 6  (Router)               — depends on 4, 5
Task 7  (Batch auto-search)    — depends on 5
Task 8  (Provider seed)        — depends on 2

Parallelizable: Tasks 1, 2, 3, 4 (all independent)
Sequential:     Tasks 5 → 6 → 7 (core pipeline)
```

## Notes

- **SQLite limitation**: Batch enrichment runs sequentially within one transaction. No concurrent writes.
- **Rate limiting**: YM API ~3 req/sec. Add `asyncio.sleep(0.3)` between search calls in batch.
- **Token refresh**: YM OAuth tokens expire. Out of scope for v1; document in README.
- **Provider ID 4**: Hardcoded in enrichment service and seed. Matches schema_v6.sql pattern.
