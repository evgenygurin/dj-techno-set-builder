# Full Schema v6 Models Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement all 30+ SQLAlchemy ORM models from `schema_v6.sql` with full constraints, relationships, and enums.

**Architecture:** Models split into domain modules under `app/models/`. Each module maps to a DDL section in `schema_v6.sql`. IntEnum classes for domain-specific smallint codes. CheckConstraints inline in `mapped_column()` matching DDL exactly. No ORM relationships yet (added when needed by service layer). Tests validate constraint enforcement via SQLite in-memory DB.

**Tech Stack:** SQLAlchemy 2.0+ (async, Mapped[], mapped_column()), Python 3.12 (PEP 695 type params), Pydantic v2, pytest-asyncio, aiosqlite.

---

## Conventions (apply to every task)

- **Naming**: `ck_{table}_{field}_{rule}` for CheckConstraints, `uq_{table}_{desc}` for UniqueConstraints
- **Imports**: `from app.models.base import Base, TimestampMixin, CreatedAtMixin`
- **Enums**: `IntEnum` in `app/models/enums.py`, used for documentation only (DB stores smallint)
- **`mapped_column()`**: CheckConstraint as positional arg, SmallInteger explicit for smallint columns
- **Tests**: one test file per model module, test constraint violations return IntegrityError
- **Commits**: one commit per task

## Table → File Mapping

| DDL Section | File | Tables |
|---|---|---|
| Base mixins | `base.py` | TimestampMixin, CreatedAtMixin |
| Enums | `enums.py` | ArtistRole, SectionType, CueKind, SourceApp, TargetApp, AssetType, RunStatus, FeedbackType |
| §2 Providers | `providers.py` | Provider |
| §3 Core catalog | `catalog.py` | Track, Artist, TrackArtist, Label, Release, TrackRelease, Genre, TrackGenre |
| §4 Raw ingestion | `ingestion.py` | ProviderTrackId, RawProviderResponse |
| §5 Provider metadata | `metadata_spotify.py` | SpotifyAlbumMetadata, SpotifyMetadata, SpotifyAudioFeatures, SpotifyArtistMetadata, SpotifyPlaylistMetadata |
| §5 Provider metadata | `metadata_soundcloud.py` | SoundCloudMetadata |
| §5 Provider metadata | `metadata_beatport.py` | BeatportMetadata |
| §6 Audio assets | `assets.py` | AudioAsset |
| §7 Pipeline runs | `runs.py` | FeatureExtractionRun, TransitionRun |
| §8 Harmony | `harmony.py` | Key, KeyEdge |
| §9 Computed features | `features.py` | TrackAudioFeaturesComputed |
| §10 Sections | `sections.py` | TrackSection |
| §11 Timeseries | `timeseries.py` | TrackTimeseriesRef |
| §12-13 Transitions | `transitions.py` | TransitionCandidate, Transition |
| §14 Embeddings | `embeddings.py` | EmbeddingType, TrackEmbedding |
| §15 DJ layer | `dj.py` | DjLibraryItem, DjBeatgrid, DjBeatgridChangePoint, DjCuePoint, DjSavedLoop, DjPlaylist, DjPlaylistItem, DjAppExport |
| §16-17 Sets | `sets.py` | DjSet, DjSetVersion, DjSetConstraint, DjSetItem, DjSetFeedback |

---

## Task 1: Base mixins and enums

**Files:**
- Modify: `app/models/base.py`
- Create: `app/models/enums.py`
- Test: `tests/test_models_enums.py`

**Step 1: Write the failing test**

```python
# tests/test_models_enums.py
from app.models.enums import ArtistRole, SectionType, CueKind, SourceApp, AssetType, RunStatus

def test_artist_role_values() -> None:
    assert ArtistRole.PRIMARY == 0
    assert ArtistRole.FEATURED == 1
    assert ArtistRole.REMIXER == 2

def test_section_type_range() -> None:
    assert len(SectionType) == 12
    assert SectionType.INTRO == 0
    assert SectionType.UNKNOWN == 11

def test_source_app_range() -> None:
    assert SourceApp.TRAKTOR == 1
    assert SourceApp.GENERATED == 5

def test_asset_type_range() -> None:
    assert AssetType.FULL_MIX == 0
    assert AssetType.PREVIEW_CLIP == 5

def test_run_status_values() -> None:
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.COMPLETED.value == "completed"
    assert RunStatus.FAILED.value == "failed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_enums.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.enums'`

**Step 3: Implement enums and update base mixins**

```python
# app/models/enums.py
"""Domain enums matching schema_v6.sql smallint CHECK constraints.

These are for documentation and app-level validation.
The database stores raw smallint/text values.
"""
from enum import IntEnum, StrEnum

class ArtistRole(IntEnum):
    PRIMARY = 0
    FEATURED = 1
    REMIXER = 2

class SectionType(IntEnum):
    INTRO = 0
    BUILDUP = 1
    DROP = 2
    BREAKDOWN = 3
    OUTRO = 4
    BREAK = 5
    INST = 6
    VERSE = 7
    CHORUS = 8
    BRIDGE = 9
    SOLO = 10
    UNKNOWN = 11

class CueKind(IntEnum):
    CUE = 0
    LOAD = 1
    GRID = 2
    FADE_IN = 3
    FADE_OUT = 4
    LOOP_IN = 5
    LOOP_OUT = 6
    MEMORY = 7

class SourceApp(IntEnum):
    TRAKTOR = 1
    REKORDBOX = 2
    DJAY = 3
    IMPORT = 4
    GENERATED = 5

class TargetApp(IntEnum):
    TRAKTOR = 1
    REKORDBOX = 2
    DJAY = 3

class AssetType(IntEnum):
    FULL_MIX = 0
    DRUMS_STEM = 1
    BASS_STEM = 2
    VOCALS_STEM = 3
    OTHER_STEM = 4
    PREVIEW_CLIP = 5

class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class FeedbackType(StrEnum):
    MANUAL = "manual"
    LIVE_CROWD = "live_crowd"
    A_B_TEST = "a_b_test"
```

Update `app/models/base.py` — add `CreatedAtMixin` for tables with only `created_at` (no `updated_at`):

```python
# app/models/base.py
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    """created_at + updated_at (for tables with UPDATE triggers in DDL)."""
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

class CreatedAtMixin:
    """created_at only (for append-only tables like sections, embeddings, feedback)."""
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_enums.py -v`
Expected: PASS

**Step 5: Commit**

```text
feat(models): add domain enums and CreatedAtMixin
```

---

## Task 2: Provider model

**Files:**
- Create: `app/models/providers.py`
- Test: `tests/test_models_providers.py`

**Step 1: Write the failing test**

```python
# tests/test_models_providers.py
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.providers import Provider

async def test_create_provider(session: AsyncSession) -> None:
    p = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add(p)
    await session.flush()
    result = await session.execute(select(Provider).where(Provider.provider_id == 1))
    assert result.scalar_one().provider_code == "spotify"

async def test_provider_code_unique(session: AsyncSession) -> None:
    session.add(Provider(provider_id=1, provider_code="spotify", name="Spotify"))
    session.add(Provider(provider_id=2, provider_code="spotify", name="Duplicate"))
    with pytest.raises(IntegrityError):
        await session.flush()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_providers.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement Provider model**

```python
# app/models/providers.py
from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

class Provider(Base):
    __tablename__ = "providers"

    provider_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    provider_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_providers.py -v`
Expected: PASS

**Step 5: Commit**

```text
feat(models): add Provider model
```

---

## Task 3: Expand catalog models (Label, Release, TrackRelease, Genre, TrackGenre, TrackArtist)

**Files:**
- Modify: `app/models/catalog.py`
- Test: `tests/test_models_catalog.py`

**Step 1: Write the failing test**

```python
# tests/test_models_catalog.py
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Artist,
    Genre,
    Label,
    Release,
    Track,
    TrackArtist,
    TrackGenre,
    TrackRelease,
)

async def test_create_label(session: AsyncSession) -> None:
    label = Label(name="Drumcode")
    session.add(label)
    await session.flush()
    assert label.label_id is not None

async def test_create_release_with_label(session: AsyncSession) -> None:
    label = Label(name="Drumcode")
    session.add(label)
    await session.flush()
    release = Release(title="A-Sides Vol.12", label_id=label.label_id)
    session.add(release)
    await session.flush()
    assert release.release_id is not None

async def test_release_date_precision_constraint(session: AsyncSession) -> None:
    """release_date_precision must be 'year', 'month', or 'day'."""
    release = Release(title="Bad", release_date_precision="century")
    session.add(release)
    with pytest.raises(IntegrityError):
        await session.flush()

async def test_track_artist_role_constraint(session: AsyncSession) -> None:
    """role must be 0, 1, or 2."""
    track = Track(title="T", duration_ms=300000)
    artist = Artist(name="A")
    session.add_all([track, artist])
    await session.flush()
    ta = TrackArtist(track_id=track.track_id, artist_id=artist.artist_id, role=99)
    session.add(ta)
    with pytest.raises(IntegrityError):
        await session.flush()

async def test_genre_self_reference(session: AsyncSession) -> None:
    parent = Genre(name="Techno")
    session.add(parent)
    await session.flush()
    child = Genre(name="Hard Techno", parent_genre_id=parent.genre_id)
    session.add(child)
    await session.flush()
    assert child.parent_genre_id == parent.genre_id

async def test_genre_name_unique(session: AsyncSession) -> None:
    session.add(Genre(name="Techno"))
    session.add(Genre(name="Techno"))
    with pytest.raises(IntegrityError):
        await session.flush()

async def test_track_release_composite_pk(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    release = Release(title="R")
    session.add_all([track, release])
    await session.flush()
    tr = TrackRelease(
        track_id=track.track_id,
        release_id=release.release_id,
        track_number=1,
    )
    session.add(tr)
    await session.flush()
    assert tr.track_id is not None

async def test_track_genre_with_provider(session: AsyncSession) -> None:
    from app.models.providers import Provider
    track = Track(title="T", duration_ms=300000)
    genre = Genre(name="Techno")
    prov = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add_all([track, genre, prov])
    await session.flush()
    tg = TrackGenre(
        track_id=track.track_id,
        genre_id=genre.genre_id,
        source_provider_id=1,
    )
    session.add(tg)
    await session.flush()
    assert tg.track_genre_id is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_catalog.py -v`
Expected: FAIL with `ImportError: cannot import name 'Label'`

**Step 3: Implement all catalog models**

Expand `app/models/catalog.py` with Label, Release, TrackRelease, Genre, TrackGenre, TrackArtist. Each model:
- Matches DDL table name, column types, CHECK constraints
- Uses `SmallInteger` for smallint columns
- Uses `ForeignKey` for FK references
- Uses `CheckConstraint` inline in `mapped_column()` for single-column checks
- Uses `__table_args__` for composite PKs and multi-column constraints

Key constraints from DDL:
- `TrackArtist`: composite PK `(track_id, artist_id, role)`, `CHECK (role BETWEEN 0 AND 2)`
- `Release`: `CHECK (release_date_precision IN ('year','month','day'))`
- `Genre`: `name UNIQUE`, self-referencing FK `parent_genre_id`
- `TrackGenre`: surrogate PK `track_genre_id`, `UNIQUE (track_id, genre_id, source_provider_id)`
- `TrackRelease`: composite PK `(track_id, release_id)`

```python
# app/models/catalog.py — full replacement
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin

class Track(TimestampMixin, Base):
    __tablename__ = "tracks"

    track_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    title_sort: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int] = mapped_column(
        CheckConstraint("duration_ms > 0", name="ck_tracks_duration_positive"),
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("status IN (0, 1)", name="ck_tracks_status_valid"),
        default=0,
    )
    archived_at: Mapped[datetime | None] = mapped_column(default=None)

class Artist(TimestampMixin, Base):
    __tablename__ = "artists"

    artist_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_sort: Mapped[str | None] = mapped_column(String(300))

class TrackArtist(CreatedAtMixin, Base):
    __tablename__ = "track_artists"
    __table_args__ = (
        CheckConstraint("role BETWEEN 0 AND 2", name="ck_track_artists_role"),
    )

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"), primary_key=True,
    )
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.artist_id", ondelete="CASCADE"), primary_key=True,
    )
    role: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

class Label(TimestampMixin, Base):
    __tablename__ = "labels"

    label_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_sort: Mapped[str | None] = mapped_column(String(300))

class Release(TimestampMixin, Base):
    __tablename__ = "releases"

    release_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    label_id: Mapped[int | None] = mapped_column(
        ForeignKey("labels.label_id", ondelete="SET NULL"),
    )
    release_date: Mapped[date | None]
    release_date_precision: Mapped[str | None] = mapped_column(
        String(5),
        CheckConstraint(
            "release_date_precision IN ('year','month','day')",
            name="ck_releases_date_precision",
        ),
    )

class TrackRelease(CreatedAtMixin, Base):
    __tablename__ = "track_releases"

    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"), primary_key=True,
    )
    release_id: Mapped[int] = mapped_column(
        ForeignKey("releases.release_id", ondelete="CASCADE"), primary_key=True,
    )
    track_number: Mapped[int | None] = mapped_column(SmallInteger)
    disc_number: Mapped[int | None] = mapped_column(SmallInteger)

class Genre(Base):
    __tablename__ = "genres"

    genre_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    parent_genre_id: Mapped[int | None] = mapped_column(
        ForeignKey("genres.genre_id", ondelete="SET NULL"),
    )

class TrackGenre(CreatedAtMixin, Base):
    __tablename__ = "track_genres"
    __table_args__ = (
        UniqueConstraint(
            "track_id", "genre_id", "source_provider_id", name="uq_track_genres_composite",
        ),
    )

    track_genre_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.track_id", ondelete="CASCADE"),
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.genre_id", ondelete="CASCADE"),
    )
    source_provider_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("providers.provider_id", ondelete="SET NULL"),
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_catalog.py -v`
Expected: PASS

**Step 5: Ruff + mypy check**

Run: `uv run ruff check app/models/ && uv run mypy app/models/`
Expected: All checks passed, no issues

**Step 6: Commit**

```text
feat(models): expand catalog — Label, Release, Genre, TrackArtist, TrackGenre, TrackRelease
```

---

## Task 4: Raw ingestion models

**Files:**
- Create: `app/models/ingestion.py`
- Test: `tests/test_models_ingestion.py`

**Step 1: Write the failing test**

```python
# tests/test_models_ingestion.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.ingestion import ProviderTrackId, RawProviderResponse
from app.models.providers import Provider

async def test_create_provider_track_id(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    prov = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add_all([track, prov])
    await session.flush()

    ptid = ProviderTrackId(
        track_id=track.track_id,
        provider_id=1,
        provider_track_id="6rqhFgbbKwnb9MLmUQDhG6",
        provider_country="US",
    )
    session.add(ptid)
    await session.flush()
    assert ptid.track_id == track.track_id

async def test_create_raw_provider_response(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    prov = Provider(provider_id=1, provider_code="spotify", name="Spotify")
    session.add_all([track, prov])
    await session.flush()

    raw = RawProviderResponse(
        track_id=track.track_id,
        provider_id=1,
        provider_track_id="6rqhFgbbKwnb9MLmUQDhG6",
        endpoint="audio-features",
        payload={"tempo": 128.0},
    )
    session.add(raw)
    await session.flush()
    assert raw.id is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_ingestion.py -v`
Expected: FAIL

**Step 3: Implement ingestion models**

```python
# app/models/ingestion.py
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

class ProviderTrackId(TimestampMixin, Base):
    """Maps tracks to their external provider IDs (Spotify, SoundCloud, Beatport)."""
    __tablename__ = "provider_track_ids"

    # No identity PK in DDL — use composite surrogate for ORM compatibility
    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    provider_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("providers.provider_id"),
    )
    provider_track_id: Mapped[str] = mapped_column(String(200))
    provider_country: Mapped[str | None] = mapped_column(String(2))

class RawProviderResponse(Base):
    """Raw JSON responses from providers. In PG: partitioned by ingested_at."""
    __tablename__ = "raw_provider_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    provider_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("providers.provider_id"),
    )
    provider_track_id: Mapped[str] = mapped_column(String(200))
    endpoint: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ingested_at: Mapped[datetime] = mapped_column(server_default="now()")
```

Note: `JSONB` will fall back to `JSON` on SQLite automatically. For the `ProviderTrackId`, the DDL has no identity PK — we add a surrogate `id` PK for ORM ergonomics (Alembic migration will use the DDL structure). The `PARTITION BY RANGE` and `UNIQUE NULLS NOT DISTINCT` are PostgreSQL-only features — the ORM models represent the logical structure.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_ingestion.py -v`
Expected: PASS

**Step 5: Commit**

```text
feat(models): add ProviderTrackId and RawProviderResponse
```

---

## Task 5: Spotify metadata models

**Files:**
- Create: `app/models/metadata_spotify.py`
- Test: `tests/test_models_spotify.py`

**Step 1: Write the failing test**

```python
# tests/test_models_spotify.py
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.metadata_spotify import (
    SpotifyAlbumMetadata,
    SpotifyAudioFeatures,
    SpotifyMetadata,
)

async def test_create_spotify_metadata(session: AsyncSession) -> None:
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    sm = SpotifyMetadata(
        track_id=track.track_id,
        spotify_track_id="6rqhFgbbKwnb9MLmUQDhG6",
    )
    session.add(sm)
    await session.flush()
    assert sm.track_id == track.track_id

async def test_spotify_popularity_constraint(session: AsyncSession) -> None:
    """popularity must be between 0 and 100."""
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    sm = SpotifyMetadata(
        track_id=track.track_id,
        spotify_track_id="abc",
        popularity=200,
    )
    session.add(sm)
    with pytest.raises(IntegrityError):
        await session.flush()

async def test_spotify_audio_features_mode_constraint(session: AsyncSession) -> None:
    """mode must be 0 or 1."""
    track = Track(title="T", duration_ms=300000)
    session.add(track)
    await session.flush()
    saf = SpotifyAudioFeatures(
        track_id=track.track_id,
        danceability=0.8, energy=0.9, loudness=-5.0, speechiness=0.04,
        acousticness=0.01, instrumentalness=0.95, liveness=0.1, valence=0.3,
        tempo=128.0, time_signature=4, key=5, mode=2,  # invalid mode
    )
    session.add(saf)
    with pytest.raises(IntegrityError):
        await session.flush()

async def test_spotify_album_metadata(session: AsyncSession) -> None:
    album = SpotifyAlbumMetadata(
        spotify_album_id="2noRn2Aes5aoNVsU6iWThc",
        album_type="album",
        name="Test Album",
    )
    session.add(album)
    await session.flush()
    assert album.spotify_album_id == "2noRn2Aes5aoNVsU6iWThc"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_spotify.py -v`
Expected: FAIL

**Step 3: Implement Spotify metadata models**

Full file `app/models/metadata_spotify.py` with:
- `SpotifyAlbumMetadata` — text PK `spotify_album_id`, jsonb `extra`
- `SpotifyMetadata` — FK to tracks (PK), FK to albums, `popularity CHECK BETWEEN 0 AND 100`, `release_date_precision CHECK`
- `SpotifyAudioFeatures` — all 0..1 range CHECKs on danceability/energy/etc., `mode CHECK IN (0, 1)`
- `SpotifyArtistMetadata` — text PK `spotify_artist_id`
- `SpotifyPlaylistMetadata` — text PK `spotify_playlist_id`

Every `real` → `Float`, every `CHECK (x BETWEEN a AND b)` → inline `CheckConstraint`.

**Step 4: Run test, commit**

```text
feat(models): add Spotify metadata models
```

---

## Task 6: SoundCloud + Beatport metadata models

**Files:**
- Create: `app/models/metadata_soundcloud.py`
- Create: `app/models/metadata_beatport.py`
- Test: `tests/test_models_metadata_ext.py`

Models follow same pattern as Spotify. Key constraints:
- `BeatportMetadata.key_code`: `CHECK (key_code BETWEEN 0 AND 23)`, FK to keys (deferred — uses `use_alter=True`)
- Both: PK = `track_id` with FK to tracks

```text
feat(models): add SoundCloud and Beatport metadata models
```

---

## Task 7: Audio assets + Pipeline runs

**Files:**
- Create: `app/models/assets.py`
- Create: `app/models/runs.py`
- Test: `tests/test_models_pipeline.py`

Key constraints:
- `AudioAsset.asset_type`: `CHECK BETWEEN 0 AND 5`
- `AudioAsset`: `UNIQUE (track_id, asset_type, source_run_id)`
- `FeatureExtractionRun.status` / `TransitionRun.status`: `CHECK IN ('running','completed','failed')`
- Deferred FK: `audio_assets.source_run_id → feature_extraction_runs` — define both models, SA handles ordering

```text
feat(models): add AudioAsset, FeatureExtractionRun, TransitionRun
```

---

## Task 8: Harmony models (Key, KeyEdge)

**Files:**
- Create: `app/models/harmony.py`
- Test: `tests/test_models_harmony.py`

Key constraints:
- `Key.key_code`: PK, `CHECK BETWEEN 0 AND 23`
- `Key`: `CHECK (key_code = pitch_class * 2 + mode)`, `pitch_class CHECK BETWEEN 0 AND 11`, `mode CHECK IN (0, 1)`
- `KeyEdge`: composite PK `(from_key_code, to_key_code)`, `distance CHECK >= 0`

```text
feat(models): add Key and KeyEdge harmony models
```

---

## Task 9: Computed audio features

**Files:**
- Create: `app/models/features.py`
- Test: `tests/test_models_features.py`

This is the largest single model (~35 columns). Key constraints:
- Composite PK `(track_id, run_id)`
- `bpm CHECK BETWEEN 20 AND 300`
- Multiple `CHECK BETWEEN 0 AND 1` for energy, confidence, clarity etc.
- Multiple `CHECK >= 0` for spectral descriptors
- `key_code` FK to keys, `CHECK BETWEEN 0 AND 23`
- `chroma` column: skip `vector(12)` type — use `String` placeholder (pgvector not available in SQLite); note in comment

```text
feat(models): add TrackAudioFeaturesComputed
```

---

## Task 10: Track sections

**Files:**
- Create: `app/models/sections.py`
- Test: `tests/test_models_sections.py`

Key constraints:
- `section_type CHECK BETWEEN 0 AND 11`
- `section_duration_ms CHECK > 0`
- `UNIQUE (section_id, track_id)` — for composite FK from transitions
- `range_ms` (`int4range`): PG-only type — use `Integer` start_ms/end_ms pair for ORM; the actual range column is managed by Alembic migration
- Multiple `CHECK BETWEEN 0 AND 1` for per-section aggregates

```text
feat(models): add TrackSection
```

---

## Task 11: Timeseries refs + Transition candidates + Transitions

**Files:**
- Create: `app/models/timeseries.py`
- Create: `app/models/transitions.py`
- Test: `tests/test_models_transitions.py`

Key constraints:
- `TrackTimeseriesRef`: composite PK `(track_id, run_id, feature_set)`, `frame_count/hop_length/sample_rate CHECK > 0`
- `TransitionCandidate`: composite PK `(from_track_id, to_track_id, run_id)`, `CHECK (from_track_id <> to_track_id)`, `bpm_distance/key_distance CHECK >= 0`
- `Transition`: identity PK, `overlap_ms CHECK >= 0`, `transition_quality CHECK BETWEEN 0 AND 1`, `CHECK (from_track_id <> to_track_id)`, composite FK to sections (logical — omit composite FK for SQLite compat, document for PG migration)

```text
feat(models): add TrackTimeseriesRef, TransitionCandidate, Transition
```

---

## Task 12: Embeddings (EmbeddingType, TrackEmbedding)

**Files:**
- Create: `app/models/embeddings.py`
- Test: `tests/test_models_embeddings.py`

Key constraints:
- `EmbeddingType`: text PK `embedding_type`, `dim CHECK > 0`
- `TrackEmbedding`: identity PK, `UNIQUE (track_id, embedding_type, run_id)`, FK to embedding_types
- `vector` column: `String` placeholder (pgvector); PG migration adds `vector` type

```text
feat(models): add EmbeddingType and TrackEmbedding
```

---

## Task 13: DJ layer models

**Files:**
- Create: `app/models/dj.py`
- Test: `tests/test_models_dj.py`

8 models, all following established patterns:
- `DjLibraryItem`: `file_size_bytes CHECK >= 0`, `source_app CHECK BETWEEN 1 AND 5`
- `DjBeatgrid`: `bpm CHECK BETWEEN 20 AND 300`, `first_downbeat_ms CHECK >= 0`, `UNIQUE (track_id, source_app)`
- `DjBeatgridChangePoint`: `position_ms CHECK >= 0`, `bpm CHECK BETWEEN 20 AND 300`
- `DjCuePoint`: `position_ms CHECK >= 0`, `cue_kind CHECK BETWEEN 0 AND 7`, `hotcue_index CHECK BETWEEN 0 AND 15`, `color_rgb CHECK BETWEEN 0 AND 16777215`
- `DjSavedLoop`: `in_ms CHECK >= 0`, `length_ms CHECK > 0`, `CHECK (out_ms > in_ms AND length_ms = out_ms - in_ms)`
- `DjPlaylist`: self-referencing FK `parent_playlist_id`, `source_app CHECK`
- `DjPlaylistItem`: identity PK, `UNIQUE (playlist_id, sort_index)`, `sort_index CHECK >= 0`
- `DjAppExport`: `target_app CHECK BETWEEN 1 AND 3`

```text
feat(models): add DJ layer — library, beatgrid, cues, loops, playlists, exports
```

---

## Task 14: DJ Sets models

**Files:**
- Create: `app/models/sets.py`
- Test: `tests/test_models_sets.py`

5 models:
- `DjSet`: `target_duration_ms CHECK > 0`, jsonb `target_energy_arc`
- `DjSetVersion`: FK to sets, `score` real
- `DjSetConstraint`: FK to versions, jsonb `value`
- `DjSetItem`: `sort_index CHECK >= 0`, `UNIQUE (set_version_id, sort_index)`, `mix_in_ms/mix_out_ms CHECK >= 0`
- `DjSetFeedback`: `rating CHECK BETWEEN -1 AND 5`, `feedback_type CHECK IN ('manual','live_crowd','a_b_test')`

```text
feat(models): add DjSet, DjSetVersion, DjSetConstraint, DjSetItem, DjSetFeedback
```

---

## Task 15: Update `__init__.py` re-exports and final verification

**Files:**
- Modify: `app/models/__init__.py`

**Step 1: Update re-exports**

```python
# app/models/__init__.py
from app.models.assets import AudioAsset
from app.models.base import Base, CreatedAtMixin, TimestampMixin
from app.models.catalog import (
    Artist, Genre, Label, Release, Track, TrackArtist, TrackGenre, TrackRelease,
)
from app.models.dj import (
    DjAppExport, DjBeatgrid, DjBeatgridChangePoint, DjCuePoint,
    DjLibraryItem, DjPlaylist, DjPlaylistItem, DjSavedLoop,
)
from app.models.embeddings import EmbeddingType, TrackEmbedding
from app.models.enums import (
    ArtistRole, AssetType, CueKind, FeedbackType,
    RunStatus, SectionType, SourceApp, TargetApp,
)
from app.models.features import TrackAudioFeaturesComputed
from app.models.harmony import Key, KeyEdge
from app.models.ingestion import ProviderTrackId, RawProviderResponse
from app.models.metadata_beatport import BeatportMetadata
from app.models.metadata_soundcloud import SoundCloudMetadata
from app.models.metadata_spotify import (
    SpotifyAlbumMetadata, SpotifyArtistMetadata, SpotifyAudioFeatures,
    SpotifyMetadata, SpotifyPlaylistMetadata,
)
from app.models.providers import Provider
from app.models.runs import FeatureExtractionRun, TransitionRun
from app.models.sections import TrackSection
from app.models.sets import (
    DjSet, DjSetConstraint, DjSetFeedback, DjSetItem, DjSetVersion,
)
from app.models.timeseries import TrackTimeseriesRef
from app.models.transitions import Transition, TransitionCandidate

__all__ = [  # sorted alphabetically
    "Artist", "ArtistRole", "AssetType", "AudioAsset",
    "Base", "BeatportMetadata",
    "CreatedAtMixin", "CueKind",
    "DjAppExport", "DjBeatgrid", "DjBeatgridChangePoint", "DjCuePoint",
    "DjLibraryItem", "DjPlaylist", "DjPlaylistItem", "DjSavedLoop",
    "DjSet", "DjSetConstraint", "DjSetFeedback", "DjSetItem", "DjSetVersion",
    "EmbeddingType",
    "FeatureExtractionRun", "FeedbackType",
    "Genre",
    "Key", "KeyEdge",
    "Label",
    "Provider", "ProviderTrackId",
    "RawProviderResponse", "Release", "RunStatus",
    "SectionType", "SoundCloudMetadata",
    "SpotifyAlbumMetadata", "SpotifyArtistMetadata", "SpotifyAudioFeatures",
    "SpotifyMetadata", "SpotifyPlaylistMetadata", "SourceApp",
    "TargetApp", "TimestampMixin", "Track", "TrackArtist",
    "TrackAudioFeaturesComputed", "TrackEmbedding", "TrackGenre",
    "TrackRelease", "TrackSection", "TrackTimeseriesRef",
    "Transition", "TransitionCandidate", "TransitionRun",
]
```

**Step 2: Full verification**

Run:
```bash
uv run ruff check app/ tests/
uv run mypy app/
uv run pytest -v
```

Expected: All checks passed, all tests pass.

**Step 3: Commit**

```text
feat(models): complete schema v6 — all 30+ tables with constraints
```

---

## PostgreSQL-only features (documented, not modeled)

These DDL features cannot be expressed in SQLite and are handled by Alembic migrations:

| Feature | Tables | Migration strategy |
|---|---|---|
| `PARTITION BY RANGE` | raw_provider_responses | PG migration only |
| `int4range` + GiST | track_sections | Use start_ms/end_ms in ORM |
| `UNIQUE NULLS NOT DISTINCT` | track_genres, provider_track_ids, transitions | PG-only UNIQUE variant |
| `vector(N)` (pgvector) | track_audio_features_computed, track_embeddings, transitions | String placeholder in ORM |
| HNSW indexes | chroma, trans_feature, embeddings | PG migration only |
| Partial unique index | dj_beatgrid (is_canonical) | PG migration only |
| Triggers | trg_set_updated_at, trg_check_embedding_dim | SA `onupdate` for timestamps; dim check in app layer |
| Functions | camelot_distance, key_distance_weighted | PG migration only |
| Views | v_latest_track_features, v_active_tracks_with_features, v_pending_scoring | PG migration only |

## Model count summary

| Category | Models | Tables |
|---|---|---|
| Enums | 8 IntEnum/StrEnum | — |
| Core catalog | 8 | tracks, artists, track_artists, labels, releases, track_releases, genres, track_genres |
| Providers | 1 | providers |
| Ingestion | 2 | provider_track_ids, raw_provider_responses |
| Metadata | 7 | spotify_metadata/album/features/artist/playlist, soundcloud, beatport |
| Assets | 1 | audio_assets |
| Runs | 2 | feature_extraction_runs, transition_runs |
| Harmony | 2 | keys, key_edges |
| Features | 1 | track_audio_features_computed |
| Sections | 1 | track_sections |
| Timeseries | 1 | track_timeseries_refs |
| Transitions | 2 | transition_candidates, transitions |
| Embeddings | 2 | embedding_types, track_embeddings |
| DJ layer | 8 | library, beatgrid, change_points, cues, loops, playlists, playlist_items, exports |
| Sets | 5 | sets, versions, constraints, items, feedback |
| **Total** | **51 types** | **43 tables** |
