# Контракты между слоями

> Определяет интерфейсы и типы, пересекающие границы слоёв.
> Основа: дизайн-спек §3 (Strict Import Rules) + результаты dependency-map.

---

## 1. Domain → Persistence (L2 → L3)

### Типы, пересекающие границу

| Тип (Domain L2) | Используется в Persistence L3 | Направление |
|-----------------|-------------------------------|-------------|
| `TrackFeatures` (scoring) | `AudioFeaturesRepository.save_features()` принимает ORM model, не domain type | L3 → L2 через конвертер |
| `TrackData` | Не используется в L3 | — |
| `TransitionScore` | Не используется в L3 | — |
| `MoodClassification` | Не используется в L3 | — |

**Ключевой принцип**: Domain НИЧЕГО не знает о persistence. Конвертеры ORM↔Domain живут в L4 (services).

### Конвертеры (L4, services/_converters.py)

```python
# ORM → Domain (persistence → domain)
def orm_to_track_features(feat: TrackAudioFeaturesComputed) -> TrackFeatures:
    """Single source of truth. Заменяет feature_conversion.py."""

def orm_to_track_data(
    feat: TrackAudioFeaturesComputed,
    artist_id: int = 0,
) -> TrackData:
    """Load + classify mood + build. Заменяет 3 дублированных паттерна.
    Использует ПРАВИЛЬНЫЕ дефолты (hp_ratio=2.0, не 0.5)."""

# Domain → ORM (для save_features)
def track_features_to_orm_kwargs(tf: TrackFeatures) -> dict:
    """Flat dict для AudioFeaturesRepository.create()."""
```

---

## 2. Services → Domain (L4 → L2)

### Интерфейс SetGenerationService → GeneticSetGenerator

```python
# Input
class GAConfig:
    population_size: int
    generations: int
    mutation_rate: float
    track_limit: int | None
    energy_arc: EnergyArcType
    template_name: TemplateName | None

class GAConstraints:
    pinned_ids: frozenset[int]
    excluded_ids: frozenset[int]

# Output
class GAResult:
    chromosome: list[int]      # ordered track indices
    fitness: float
    generation: int
    transition_scores: list[float]
```

**Service отвечает за**:
1. Загрузку ORM features из repos
2. Конвертацию ORM → `TrackData` (через `_converters.py`)
3. Построение transition matrix (через `TransitionScoringService`)
4. Вызов `GeneticSetGenerator.run()` с pure domain types
5. Конвертацию результата → ORM entities (DjSetVersion, DjSetItem)
6. Persist через repos

**Domain НЕ знает о**: Session, Repository, ORM models, FastAPI, FastMCP.

### Интерфейс TransitionScoringService (Domain L2)

```python
class TransitionScoringService:
    """Pure scorer. Вход/выход — только domain types."""

    def score_pair(self, a: TrackFeatures, b: TrackFeatures) -> float:
        """Score transition quality between two tracks."""

    def score_bpm(self, a: TrackFeatures, b: TrackFeatures) -> float: ...
    def score_harmonic(self, a: TrackFeatures, b: TrackFeatures) -> float: ...
    def score_energy(self, a: TrackFeatures, b: TrackFeatures) -> float: ...
    def score_spectral(self, a: TrackFeatures, b: TrackFeatures) -> float: ...
    def score_groove(self, a: TrackFeatures, b: TrackFeatures) -> float: ...
```

**CamelotLookupService** — чистый domain lookup (24 ключа → compatibility). Не трогает DB.

### Интерфейс UnifiedTransitionScoringService (Facade, L4)

```python
class UnifiedTransitionScoringService:
    """Service facade. Подгружает features из DB, вызывает domain scorer."""

    def __init__(self, features_repo, camelot_svc, domain_scorer): ...

    async def score_set_version(self, version_id: int) -> list[TransitionScoreResult]: ...
    async def score_track_pair(self, track_a_id: int, track_b_id: int) -> float: ...
    async def build_matrix(self, track_ids: list[int]) -> np.ndarray: ...
```

---

## 3. Adapter → Services (L5 → L4)

### Принцип "Thin Adapter"

Каждый MCP tool / API router — ≤80 LOC. Может только:

1. **Parse input** — resolve refs, validate params
2. **Report progress** — `ctx.info()`, `ctx.report_progress()` (MCP only)
3. **Elicitation** — `ctx.elicit()` (MCP only)
4. **Call service** — один вызов, получает domain/response type
5. **Map result** — domain type → MCP response type / HTTP response

### MCP Tool Contract

```python
async def deliver_set(
    set_id: int,
    version_id: int | None = None,
    sync_to_ym: bool = False,
    ctx: Context,
    delivery_svc: DeliveryService = Depends(get_delivery_service),
) -> DeliveryResult:
    # 1. Parse
    resolved = await delivery_svc.resolve_version(set_id, version_id)
    # 2. Progress
    await ctx.info("Stage 1/3 — scoring transitions...")
    await ctx.report_progress(progress=0, total=3)
    # 3. Service call
    result = await delivery_svc.deliver(resolved, sync_ym=sync_to_ym)
    # 4. Return MCP type
    return result  # DeliveryResult Pydantic model
```

### API Router Contract

```python
@router.post("/{set_id}/deliver", response_model=DeliveryRead)
async def deliver_set(set_id: int, db: DbSession) -> DeliveryRead:
    svc = create_delivery_service(db)  # from _factories.py
    result = await svc.deliver(set_id)
    await db.commit()
    return result
```

---

## 4. Единый TrackFeatures (Domain L2)

### Текущее состояние

| Класс | Файл | Полей | Назначение |
|-------|------|-------|------------|
| `TrackFeatures` | `_types.py:161` | 11 (result objects) | Контейнер DSP результатов |
| `TrackFeatures` | `transition_scoring.py:32` | 12 (flat numbers) | Scoring input |

### Целевое состояние

```python
# domain/audio/types.py

@dataclass(frozen=True, slots=True)
class TrackFeatures:
    """Unified scoring-oriented track features. Used across all domain logic."""
    bpm: float
    energy_lufs: float
    key_code: int
    harmonic_density: float   # from chroma_entropy
    centroid_hz: float
    band_ratios: list[float]  # [low, mid, high]
    onset_rate: float
    # Phase 2 enrichments (optional, backward-compat defaults)
    mfcc_vector: list[float] | None = None
    kick_prominence: float = 0.5
    hnr_db: float = 0.0
    spectral_slope: float = 0.0

@dataclass(frozen=True, slots=True)
class AllFeatures:
    """Full DSP pipeline output. Only used in pipeline → DB persist path."""
    bpm: BpmResult
    key: KeyResult
    loudness: LoudnessResult
    energy: EnergyResult
    spectral: SpectralResult
    beats: BeatsResult | None
    groove: GrooveResult | None
    structure: StructureResult
    mfcc: MfccResult | None
```

---

## 5. Единый YandexMusicClient (L4)

### Целевой интерфейс

```python
class YandexMusicClient:
    """Single YM client. Rate limiting built-in."""

    def __init__(self, token: str, base_url: str, user_id: str,
                 rate_limit_delay: float = 1.5): ...

    # Search & fetch
    async def search_tracks(self, query: str) -> list[dict]: ...
    async def fetch_tracks(self, track_ids: list[int]) -> list[dict]: ...

    # Playlists
    async def get_playlist(self, user_id: int, kind: int) -> dict: ...
    async def create_playlist(self, user_id: int, title: str, visibility: str) -> int: ...
    async def add_tracks_to_playlist(self, user_id: int, kind: int,
                                      tracks: list[dict], revision: int) -> None: ...
    async def remove_tracks_from_playlist(self, user_id: int, kind: int,
                                           indices: list[int], revision: int) -> None: ...

    # Download
    async def download_track(self, track_id: int, dest: Path) -> Path: ...

    # Recommendations
    async def get_similar_tracks(self, track_id: int) -> list[dict]: ...
    async def get_recommendations(self, track_id: int) -> list[dict]: ...

    # Lifecycle
    async def close(self) -> None: ...
```

Живёт в `services/platform/yandex/client.py`. Rate limiting через `asyncio.sleep(rate_limit_delay)` перед каждым HTTP вызовом.

---

## 6. DI Factories (L4)

### Целевой интерфейс (_factories.py)

```python
# Pure factory functions — no framework deps, just session → service

def build_track_service(session: AsyncSession) -> TrackService: ...
def build_playlist_service(session: AsyncSession) -> DjPlaylistService: ...
def build_features_service(session: AsyncSession) -> AudioFeaturesService: ...
def build_set_service(session: AsyncSession) -> DjSetService: ...
def build_analysis_service(session: AsyncSession) -> TrackAnalysisService: ...
def build_generation_service(session: AsyncSession) -> SetGenerationService: ...
def build_delivery_service(session: AsyncSession, ym_client: YandexMusicClient | None = None) -> DeliveryService: ...
def build_scoring_service(session: AsyncSession) -> UnifiedTransitionScoringService: ...
```

### Usage in adapters

```python
# api/dependencies.py (FastAPI)
def get_track_service(db: DbSession) -> TrackService:
    return build_track_service(db)

# mcp/dependencies.py (FastMCP)
def get_track_service(session: AsyncSession = Depends(get_session)) -> TrackService:
    return build_track_service(session)
```

---

## 7. Transaction Boundaries

### Текущее состояние

| Adapter | Commit pattern |
|---------|---------------|
| REST routers | `await db.commit()` в router handler |
| MCP tools | Auto-commit в `get_session()` asynccontextmanager |

### Целевое состояние

**Оба адаптера** используют одинаковый паттерн через `get_session()`:

```python
@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- Services вызывают `flush()` — never `commit()`
- Repositories вызывают `flush()` — never `commit()`
- Adapters (REST/MCP) получают session через DI — commit/rollback automatic
- REST routers убирают явные `await db.commit()` вызовы
