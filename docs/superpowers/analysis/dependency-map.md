# Карта зависимостей app/

> Сгенерировано: 2026-03-23 | 211 Python-файлов | 629 dependency-рёбер | 0 циклов

## Fan-In Top 10 (от чего зависят больше всего файлов)

| # | Модуль | Fan-in | Комментарий |
|---|--------|--------|-------------|
| 1 | `app.errors` | 31 | Центральная точка обработки ошибок |
| 2 | `app.services.base` | 19 | BaseService (self.logger) |
| 3 | `app.schemas.base` | 19 | BaseSchema (from_attributes, extra=forbid) |
| 4 | `app.models.base` | 19 | Base, TimestampMixin, CreatedAtMixin |
| 5 | `app.utils.audio._types` | 18 | TrackFeatures, AudioData, result dataclasses |
| 6 | `app.repositories.base` | 18 | BaseRepository[ModelT] |
| 7 | `app.mcp.dependencies` | 16 | FastMCP DI hub |
| 8 | `app.dependencies` | 15 | FastAPI DI (DbSession) |
| 9 | `app.routers.v1._openapi` | 14 | Shared error response schemas |
| 10 | `app.repositories.tracks` | 14 | ⚠️ Высокий fan-in для repo — прямые импорты из MCP |

**Вывод**: Base-классы и `errors` — ожидаемо. `repositories.tracks` и `repositories.audio_features` (13) имеют слишком высокий fan-in для persistence layer — это прямые импорты из MCP tools, минуя services.

## Fan-Out Top 10 (файлы с наибольшим числом зависимостей)

| # | Файл | Fan-out | Роль |
|---|------|---------|------|
| 1 | `app/mcp/dependencies.py` | 22 | MCP DI hub |
| 2 | `app/cli/setbuilder.py` | 22 | CLI set builder |
| 3 | `app/models/__init__.py` | 19 | Re-export hub для create_all() |
| 4 | `app/services/track_analysis.py` | 18 | Multi-repo orchestrator |
| 5 | `app/mcp/tools/server.py` | 18 | Tool registry |
| 6 | `app/cli/sets.py` | 18 | CLI sets |
| 7 | `app/mcp/tools/export.py` | 17 | Export tool (heavy) |
| 8 | `app/mcp/tools/sync.py` | 16 | Sync tools |
| 9 | `app/mcp/tools/setbuilder.py` | 16 | Set builder tool |
| 10 | `app/mcp/tools/set.py` | 16 | Set CRUD tool |

**Вывод**: MCP tools доминируют в fan-out (7 из 10). Это симптом: tools берут на себя слишком много, тянут зависимости из всех слоёв.

## Cross-Layer Violations

### MCP tools → Repositories напрямую (18 импортов в 8 файлах)

| Файл | Строка | Импорт |
|------|--------|--------|
| `tools/track.py` | 25-26 | `AudioFeaturesRepository`, `TrackRepository` |
| `tools/features.py` | 24-25 | `AudioFeaturesRepository`, `TrackRepository` |
| `tools/playlist.py` | 34 | `DjPlaylistItemRepository`, `DjPlaylistRepository` |
| `tools/search.py` | 23-26, 145 | `ArtistRepo`, `DjPlaylistRepo`, `DjSetRepo`, `TrackRepo`, `AudioFeaturesRepo` |
| `tools/set.py` | 43 | `DjSetItemRepo`, `DjSetRepo`, `DjSetVersionRepo` |
| `tools/compute.py` | 130 | `DjSetRepo`, `DjSetVersionRepo`, `DjSetItemRepo` (lazy) |
| `tools/export.py` | 93-98 | `BeatgridRepo`, `CuePointRepo`, `LoopRepo`, `KeyRepo`, `SectionsRepo`, `TrackRepo` (lazy) |

### MCP tools → Models напрямую (11 импортов в 5 файлах)

| Файл | Строка | Модели |
|------|--------|--------|
| `tools/curation_discovery.py` | 20-23 | `Track`, `DjPlaylistItem`, `ProviderTrackId`, `YandexMetadata` |
| `tools/delivery.py` | 189, 317 | `DjLibraryItem`, `YandexMetadata` (lazy) |
| `tools/playlist.py` | 32-33 | `DjPlaylistItem`, `ProviderTrackId` |
| `tools/sync.py` | 34-35 | `YandexMetadata`, `DjSet` |
| `tools/compute.py` | 49 | `DjLibraryItem` (lazy) |

### MCP helpers → Models/SQL (3 файла)

| Файл | Импорт |
|------|--------|
| `mcp/library_stats.py` | `Track`, `DjPlaylist`, `TrackAudioFeaturesComputed`, `DjSet` + `func, select` |
| `mcp/sync/track_mapper.py` | `ProviderTrackId`, `Provider` + `select` |

## Raw SQL в адаптерном слое (7 файлов в MCP)

| Файл | Строка | Импорт | Описание |
|------|--------|--------|----------|
| `mcp/library_stats.py` | 7 | `func, select` | COUNT-агрегаты |
| `mcp/sync/track_mapper.py` | 5 | `select` | Provider lookup |
| `mcp/tools/compute.py` | 47 | `select` (lazy) | Track analysis |
| `mcp/tools/curation_discovery.py` | 15 | `func, select` | Direct ORM queries |
| `mcp/tools/delivery.py` | 25 | `select` | Track data collection |
| `mcp/tools/playlist.py` | 19 | `select` | Playlist item queries |
| `mcp/tools/sync.py` | 14 | `select` | Set/metadata queries |

**В routers raw SQL нет** — они чисты.

## Циклические зависимости

**Не обнаружено.** Граф — строго ацикличный DAG.

## Рекомендации по приоритетности

| Приоритет | Файл | Нарушений | Действие |
|-----------|------|-----------|----------|
| **P0** | `curation_discovery.py` | 4 модели + raw SQL + 563 LOC бизнес-логики | Extract → `services/discovery.py` |
| **P1** | `delivery.py` | 2 модели (lazy) + raw SQL + 518 LOC | Extract → `services/delivery.py` |
| **P1** | `playlist.py` | 2 repos + 2 модели + raw SQL | Делегировать в PlaylistService |
| **P2** | `search.py` | 5 repos прямо | Делегировать в DI / SearchService |
| **P2** | `set.py` | 3 repos прямо | Делегировать через DI |
| **P2** | `sync.py` | 2 модели + raw SQL | Делегировать в SyncEngine |
| **P3** | `export.py` | 6 repos (lazy) | Делегировать в ExportService |
| **P3** | `compute.py` | 3 repos + 1 модель (lazy) | Делегировать в AnalysisService |
