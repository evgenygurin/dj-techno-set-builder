# DJ Techno Set Builder — Математический аудит данных и скоринга

Дата: 2026-02-15  
Область: математика признаков, скоринг переходов, оптимизация порядка треков  
Источники: `docs/data-inventory.md`, `docs/database.md`, `app/services/set_generation.py`, `app/services/transition_scoring.py`, `app/utils/audio/transition_score.py`, `app/utils/audio/set_generator.py`, `dev.db`

## 1) Что реально есть в данных (по `dev.db`)

Снимок базы (`file:dev.db?mode=ro`) показывает:

- `tracks`: 136
- `track_audio_features_computed`: 136 строк, 133 уникальных `track_id`
- `track_sections`: 10075 строк, 133 трека с секциями
- `transitions`: 0
- `transition_candidates`: 0
- `track_timeseries_refs`: 0
- `dj_set_feedback`: 0

### Заполненность признаков (latest per track)

Для 133 треков:

- `tempo_confidence`, `bpm_stability`, `lufs_i`, `sub_energy`, `centroid_mean_hz`, `chroma`, `onset_rate_mean`, `kick_prominence`: 100% non-null
- Это означает, что проблема не в отсутствии данных, а в том, что они не доживают до целевой функции оптимизации.

### Наблюдения по диапазонам

- `tempo_confidence`: 0.9872..1.0
- `bpm_stability`: 0.9136..0.9976
- `pulse_clarity`: 0.9872..1.0
- `key_confidence`: 0.2838..0.9485
- `onset_rate_mean`: 3.4429..8.4875
- `centroid_mean_hz`: 1061.56..4877.15
- `flatness_mean`: 0.0155..0.2023
- `hnr_mean_db`: 14.2574..27.439

Ключевой вывод: часть признаков почти вырождена (например, `pulse_clarity` около 1.0), поэтому их вклад в скоринг в текущей шкале будет слабым без дополнительной калибровки.

## 2) Текущие математические модели

## 2.1 GA fitness

В `app/utils/audio/set_generator.py`:

- `fitness = w_transition * transition + w_energy_arc * arc + w_bpm_smooth * bpm`
- По умолчанию:
  - `w_transition = 0.50`
  - `w_energy_arc = 0.30`
  - `w_bpm_smooth = 0.20`

Где:

- `transition`: среднее качество переходов по матрице
- `arc`: `1 - RMSE(actual_energy, target_curve)`
- `bpm_smooth`: `1 - mean(|ΔBPM|)/20`, clamp [0,1]

Следствие:

- Любые признаки, не вошедшие в `transition_matrix`, статистически не влияют на порядок треков.

## 2.2 Матрица переходов (основной режим генерации)

В `app/services/set_generation.py::_build_transition_matrix_scored` используется `TransitionScoringService` с формулой:

- `score = 0.30*bpm + 0.25*harmonic + 0.20*energy + 0.15*spectral + 0.10*groove`

Компоненты:

- BPM: гауссов спад `exp(-(diff^2)/(2*8^2))` с double/half-time fallback
- Harmonic: lookup + модуляция плотностью гармоник
- Energy: `1 / (1 + (ΔLUFS/4)^2)`
- Spectral: `0.5*centroid_score + 0.5*cosine(band_ratios)`
- Groove: `1 - |Δonset|/max(onset)`

## 2.3 Альтернативный скорер (в API /transitions/compute)

В `app/utils/audio/transition_score.py` — другая формула:

- `0.40*bpm + 0.25*key + 0.15*energy + 0.10*compatibility + 0.10*groove`
- Где `compatibility = 0.5*bass_conflict + 0.5*spectral_overlap`

Следствие: в кодовой базе уже две разные математические модели качества перехода.

## 3) Где информация теряется математически

## 3.1 Camelot/graph-информация не доходит до GA

`CamelotLookupService` использует таблицу `key_edges` только если передан DB session.  
В `SetGenerationService` и MCP setbuilder сервис создается без сессии:

- `camelot_service = CamelotLookupService()`

В этом режиме lookup становится:

- same-key = 1.0
- все остальные пары = 0.5

Итог:

- математически богатый граф `key_edges` (144 ребра, веса 0.7..1.0) не участвует в GA-оптимизации.

## 3.2 Сжатие энергетических признаков

База хранит 6 band-энергий + производные, но в GA/TransitionScoring:

- используется только 3-компонентный вектор `[low, mid, high]`
- `sub`, `lowmid`, `highmid`, `energy_std`, `energy_slope_mean` выпадают

Итог: уменьшается разрешение по спектрально-энергетическому пространству.

## 3.3 Структура трека не участвует в целевой функции

Хотя `track_sections` заполнена, ни один section-level сигнал не входит в:

- `transition_matrix`
- fitness GA

Математически мы оптимизируем “какие треки рядом”, но не “где внутри треков делать переход”.

## 3.4 Отсутствует обучающая петля

`dj_set_feedback` и `transitions` пустые.  
Без целевой метки нет:

- калибровки весов
- валидации качества модели
- авто-подстройки под конкретный стиль/диджея

## 4) Статистические аномалии, влияющие на скоринг

## 4.1 `pulse_clarity` почти константа

По latest-фичам: 0.9872..1.0, среднее ~1.0.  
Это почти неинформативный признак для ранжирования.

Риск:

- если дать ему большой вес, это будет почти “шумовой” компонент.

## 4.2 Сверхдробная сегментация структуры

По `track_sections`:

- в среднем 75.8 секций на трек
- 101 трек имеют >60 секций
- средняя секция ~4.79 секунды
- `section_type=11 (unknown)` доминирует

Это плохо для устойчивого выбора mix-point: секции слишком короткие и шумные.

## 5) Что считать “используется” в текущей математике

Для фактической генерации сетов (GA path):

- точно участвуют: `bpm`, `lufs_i`, `key_code`, `key_confidence` (как proxy density), `low_energy`, `mid_energy`, `high_energy`, `centroid_mean_hz`, `onset_rate_mean`
- почти не участвуют напрямую: остальные 20+ признаков

Отдельно:

- endpoint `/api/v1/transitions/compute` использует расширенные поля (через альтернативный скорер), но `transitions` в базе сейчас 0, значит pipeline не operational.

## 6) Приоритетная математическая дорожная карта

## P0 (быстрый эффект, минимум риска)

1. Передавать DB session в `CamelotLookupService` в GA/MCP, чтобы реально использовать `key_edges`.
2. Привести к одной формуле transition-score (либо service-based, либо utils-based), убрать двойную математику.
3. Добавить precompute таблицу (или материализованный слой) парных скоров `N x N` для latest run.

## P1 (рост качества)

4. Включить 6-band energy distance (вместо 3-band) с нормализацией по корпусу.
5. Добавить loudness safety term:
   - штраф за `|ΔLUFS| > τ`
   - бонус за приемлемый диапазон перехода
6. Включить key confidence gating:
   - при низкой уверенности ослаблять harmonic penalty/bonus.

## P2 (структурная оптимизация)

7. Перейти от track-level transition к section-aware transition:
   - `score(track_i.section_a -> track_j.section_b)`
8. Устранить пере-сегментацию (минимальная длительность секций, merge соседних коротких).
9. Добавить objective mixability:
   - совместимость длины intro/outro,
   - фазовая устойчивость по тактам.

## P3 (обучаемая система)

10. Заполнить `transitions` и `dj_set_feedback`, собрать supervised target.
11. Калибровать веса компонентов на исторических оценках.
12. Добавить A/B валидацию новых весов/моделей на реальных сетах.

## 7) KPI для внедрения

- Coverage:
  - доля реально используемых признаков в transition objective: >60%
- Harmonic quality:
  - доля переходов с совместимыми Camelot ребрами: +30% к baseline
- Energy continuity:
  - снижение median `|ΔLUFS|` между соседними треками
- Structural validity:
  - доля переходов intro/outro-compatible >70%
- Learning loop:
  - >500 переходов с feedback для первичной калибровки

## 8) Резюме

Данные и признаки уже есть, но главная математическая проблема — не extraction, а “потеря сигнала” между БД и целевой функцией оптимизатора.  
Приоритет №1: соединить фактические данные (`key_edges`, секции, многополосная энергия) с единой формулой transition-score и сделать это источником для GA.
