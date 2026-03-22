---
name: audio-analysis
description: Use when working with audio features, BPM, Camelot keys, transition scoring, GA set builder, iCloud stubs, M3U8 export, or cheat_sheet generation. Triggers on app/utils/audio/, TrackFeatures, scoring, deliver_set, cheat_sheet.
---

# Audio Analysis and Set Delivery

Audio анализ — дорогая операция. Если фичи уже есть в DB — используй их. `dj_analyze_track` требует `dj_activate_heavy_mode`.

## Точки входа

| Запрос | Инструмент |
|--------|-----------|
| BPM / key / energy трека | `dj_get_track` + `dj_get_features` (DB, мгновенно) |
| Посчитать фичи | `dj_analyze_track` (ML, 15-120 сек, тег `heavy`) |
| Треки по параметрам | `dj_filter_tracks` (BPM, key, energy) |
| Построить сет | `dj_build_set` (использует готовые фичи) |
| Оценить переходы | `dj_score_transitions` |
| Экспортировать | `dj_deliver_set` (score → файлы → опционально YM) |

## Scoring переходов (5 компонентов)

| Компонент | Вес | Hard constraint |
|-----------|-----|-----------------|
| BPM | 0.30 | diff > 10 → 0.0 |
| Harmonic | 0.25 | Camelot dist ≥ 5 → 0.0 |
| Energy | 0.20 | LUFS diff > 6 → 0.0 |
| Spectral | 0.15 | — |
| Groove | 0.10 | — |

Пороги: `≥ 0.85` хороший, `< 0.85` слабый (`!!!`), `0.0` жёсткий конфликт.

## Delivery — 3 стадии

1. **Scoring** — `TransitionScoreResult` для каждой пары. Hard conflicts → вопрос пользователю.
2. **Файлы** — M3U8 + JSON guide + cheat_sheet.txt в `generated-sets/{name}/`
3. **YM sync** (опционально) — ошибка YM не блокирует (файлы уже записаны).

## iCloud стабы

```python
def is_local(path: Path) -> bool:
    st = path.stat()
    return st.st_blocks * 512 >= st.st_size * 0.9
# shutil.copy2 на стабе = TimeoutError!
```

Пропускай стабы при экспорте, в M3U указывай путь к исходному файлу.

## TrackFeatures (ключевой тип)

```python
@dataclass(frozen=True, slots=True)
class TrackFeatures:
    bpm: float; energy_lufs: float; key_code: int  # 0-23
    harmonic_density: float; centroid_hz: float
    band_ratios: list[float]; onset_rate: float
    mfcc_vector: list[float] | None = None
    kick_prominence: float = 0.5; hnr_db: float = 0.0
```

Конверсия ORM→TrackFeatures: `app/utils/audio/feature_conversion.py`.

## Что НЕ делать

- Не запускать `dj_analyze_track` без явного запроса — занимает минуты
- Не копировать iCloud стабы через `shutil.copy2` — TimeoutError
- Не синхронизировать в YM без согласия пользователя
- Не пересобирать сет если `avg_score ≥ 0.75`

Подробности: `.claude/rules/audio.md`.

---

## Iron Law

```text
NO FEATURE INTERPRETATION WITHOUT CHECKING COLUMN NAMES IN DB SCHEMA
```

`onset_rate` vs `onset_rate_mean`, `hnr_db` vs `hnr_mean_db` — неправильное имя колонки = NULL = сломанный scoring. Перед ЛЮБЫМ SQL или ORM запросом к audio features — проверь `.claude/rules/db-schema.md`.

## Red Flags

| Отговорка | Реальность |
|-----------|------------|
| "Я помню имя колонки" | `onset_rate` vs `onset_rate_mean` уже ломало запросы дважды |
| "hp_ratio в диапазоне 0-1" | hp_ratio UNBOUNDED (0.66-17.25), НЕ нормализован |
| "Запущу анализ для всех треков" | Анализ = 15-120 сек × N треков, нужен `heavy_mode` + согласие юзера |
| "Фичи одинаковые для всех pipeline" | v1.0 не имеет beats (kick, onset, pulse = NULL), только v2.1b6 полный |
