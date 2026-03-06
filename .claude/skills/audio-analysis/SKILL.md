---
name: Audio Analysis and Set Delivery
description: Гайд по аудио анализу, scoring переходов и доставке сетов в этом проекте. Используй когда: работаешь с audio features, BPM, Camelot keys, scoring переходов, GA set builder, iCloud стабами, M3U8 экспортом, cheat_sheet генерацией. Триггеры: audio features, TrackFeatures, scoring, Camelot, cheat_sheet, M3U8, iCloud, app/utils/audio/.
allowed-tools: Read, Grep, Glob
---

# Audio Analysis and Set Delivery

## Философия

Audio анализ — дорогая операция. Не запускай `compute_audio_features` без нужды. Если фичи уже есть в DB — используй их. Этот скилл описывает когда и как работать с аудио данными.

---

## Точки входа — определи по контексту

| Что просит пользователь | С чего начать |
|------------------------|---------------|
| "Какие у трека BPM / key / energy?" | → `dj_get_track_details` (читает из DB) |
| "Посчитай фичи для этого трека" | → `dj_compute_audio_features` (тяжело, ML) |
| "Где есть треки 138-142 BPM?" | → `dj_search_by_criteria` или `dj_filter_tracks` |
| "Построй сет из этого плейлиста" | → `dj_build_set` (использует уже вычисленные фичи) |
| "Проанализируй переходы" | → `dj_score_transitions` |
| "Экспортируй сет" | → `dj_deliver_set` |
| "Скачай треки из YM" | → `dj_download_tracks` |

---

## Инструменты анализа

### `dj_get_track_details` (read-only, мгновенно)

Возвращает всё что есть в DB: BPM, key_code, Camelot, LUFS, chroma_entropy, MFCC, sections, cue points.
Использует `get_track_service` + `get_features_service`. Не запускает ML.

### `dj_search_by_criteria` (read-only, быстро)

Фильтр по BPM/ключу/energy диапазону из `track_audio_features_computed`.
Возвращает список треков с матчингом. Пустые заголовки = баг в schema, используй `dj_get_track_details` для деталей.

### `dj_compute_audio_features` (тяжёлый, скрыт)

ML-пайплайн: BPM → key → LUFS → energy → spectral → beats → MFCC → groove → structure.
**Активировать только через `dj_activate_heavy_mode`** — скрыт по умолчанию.
Время: 15-120 сек на трек в зависимости от длины и CPU.

---

## Пайплайн аудио анализа (`app/utils/audio/`)

Чистые функции, без DB/ORM зависимостей.

### Зависимости по модулям

| Нужно | Extra | Команда |
|-------|-------|---------|
| BPM, key, energy, spectral | `audio` | `uv sync --extra audio` |
| Stem separation | `ml` | `uv sync --extra ml` |
| Базовый анализ | essentia, soundfile, scipy, numpy, librosa | — |
| Demucs | demucs, torch | — |

### Ключевые типы

```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    bpm: float
    energy_lufs: float
    key_code: int          # 0-23
    harmonic_density: float  # chroma entropy
    centroid_hz: float
    band_ratios: list[float]  # [low, mid, high]
    onset_rate: float
    mfcc_vector: list[float] | None = None  # 13 MFCC
    kick_prominence: float = 0.5
    hnr_db: float = 0.0
    spectral_slope: float = 0.0
```

ORM → TrackFeatures: `app/utils/audio/feature_conversion.py` — единственное место конверсии.

---

## Scoring переходов

`TransitionScoringService` — **чистый сервис**, без DB:

| Компонент | Вес | Формула |
|-----------|-----|---------|
| BPM | 0.30 | Gaussian (sigma=8) + double/half-time |
| Harmonic | 0.25 | Camelot + chroma entropy + HNR |
| Energy | 0.20 | Sigmoid на разнице LUFS |
| Spectral | 0.15 | MFCC cosine + centroid + band balance |
| Groove | 0.10 | Onset density + kick prominence |

**Hard constraints** (score = 0.0):
- BPM разница > 10
- Camelot distance ≥ 5
- Energy разница > 6 LUFS

**Thresholds**:
```text
1.0       идеальный (тот же Camelot ключ)
≥ 0.85    хороший
0.0–0.84  слабый → !!! в cheat_sheet
0.0       жёсткий конфликт
```

---

## Camelot система

Ключи 0-23, Camelot нотация `1A`..`12B`:
- `A` = minor, `B` = major
- Совместимые: тот же ключ (1.0), соседи ±1 (0.85), параллельный (0.75)
- `app/services/camelot_lookup.py` — `build_lookup_table()` → `dict[int, dict[int, float]]`

---

## Построение сета

`SetGenerationService` (`app/services/set_generation.py`):

- **GA с 2-opt** для оптимизации порядка треков
- **8 шаблонов** (`app/utils/audio/set_templates.py`): `classic`, `progressive`, `roller`, `wave`, `festival_main`, `festival_warm_up`, `warehouse`, `acid_techno`
- **Fitness** = transition_score * 0.35 + template_slot_fit * 0.25 + energy_arc * 0.20 + bpm_smooth * 0.10 + variety * 0.10
- **GAConstraints**: `pinned_ids` (всегда в хромосоме) + `excluded_ids` (запрещены при мутации)

**Mood categories** (для template slot matching):
`ambient_dub` → `deep_minimal` → `driving_groovy` → `peak_melodic` → `hard_techno` → `acid_industrial`

---

## Set delivery (`dj_deliver_set`) — 3 стадии

Полный цикл: score → file export → optional YM sync.

### Stage 1: Scoring (обратимо)

Вычисляет `TransitionScoreResult` для каждой пары треков.
Если `hard_conflicts > 0` → `resolve_conflict()` с вопросом пользователю.

### Stage 2: Запись файлов (необратимо)

```text
{library_path}/../generated-sets/{safe_name}/
├── {safe_name}.m3u8          # Extended M3U8 с DJ метаданными
├── {safe_name}_guide.json    # JSON переходов и метаданных
└── {safe_name}_cheat.txt     # Cheat sheet для DJ
```

**Cheat sheet** (`cheat_sheet.txt`):
- Позиция, название, BPM, Camelot, LUFS
- Переход к следующему: тип, score, причина
- `!!!` для переходов < 0.85

### Stage 3: YM sync (опционально)

Создаёт/обновляет плейлист через `YandexMusicClient.create_playlist()` + `add_tracks_to_playlist()`.
Ошибка YM не блокирует — файлы уже записаны, статус остаётся `"ok"`.

**YM track mapping**:
- Есть запись в `yandex_metadata` → использует `yandex_track_id`
- `track_id > 1_000_000` → YM native трек (без `album_id` будет пропущен)

---

## iCloud стабы

Проблема: `os.path.exists()` и `stat().st_size` возвращают True/корректные значения для стабов.

```python
def is_local(path: Path) -> bool:
    st = path.stat()
    return st.st_blocks * 512 >= st.st_size * 0.9

# shutil.copy2 на стабе = TimeoutError — НЕ делай!
# brctl download path — запускает скачивание (медленно)
```

При экспорте: пропускай стабы, в M3U указывай путь к исходному файлу.

---

## M3U8 расширения

Стандартные + кастомные `#EXTDJ-*` теги (backward compatible):

| Тег | Данные |
|-----|--------|
| `#EXTDJ-BPM:` | BPM трека |
| `#EXTDJ-KEY:` | Camelot нотация |
| `#EXTDJ-ENERGY:` | LUFS |
| `#EXTDJ-CUE:` | Cue points: `time=,type=hot\|memory,name=,color=` |
| `#EXTDJ-LOOP:` | Loops: `in=,out=,name=` |
| `#EXTDJ-SECTION:` | Структурные секции: `type=intro\|drop\|outro,start=,end=` |
| `#EXTDJ-TRANSITION:` | Переход к следующему: `type=,score=,bpm_delta=,camelot=,reason=` |

---

## Что НЕ делать

- Не запускать `compute_audio_features` без явного запроса — занимает минуты, блокирует
- Не копировать iCloud стабы через `shutil.copy2` — TimeoutError
- Не синхронизировать в YM без явного согласия пользователя
- Не пересобирать сет если `avg_score ≥ 0.75` — уже хороший
