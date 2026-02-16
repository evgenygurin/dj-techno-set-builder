# DJ Techno Set Builder — Музыкально-DJ аудит использования данных

Дата: 2026-02-15  
Область: музыкальная теория, реальная практика микширования, соответствие алгоритмов DJ-процессу  
Источники: `docs/data-inventory.md`, `app/utils/audio/structure.py`, `app/utils/audio/beats.py`, `app/services/set_generation.py`, `app/services/transition_scoring.py`, `dev.db`

## 1) Что важно в реальном techno mixing

Для практического DJ-сета обычно критичны 5 слоев:

1. Beat alignment: стабильный темп, отсутствие “развала” грува
2. Harmonic fit: допустимая тональная совместимость (Camelot/relative moves)
3. Energy dramaturgy: осмысленная кривая энергии (развитие, разрядка, новый пик)
4. Phrase/section alignment: переходы по фразам (чаще 8/16/32 такта)
5. Low-end management: контроль конфликта кика/баса и loudness jump

Текущая система решает пп. 1-3 частично на уровне треков, но почти не решает 4-5 на уровне секций и микс-точек.

## 2) Музыкальная интерпретация текущих признаков

## 2.1 Tempo/Groove

Есть:

- `bpm`, `tempo_confidence`, `bpm_stability`, `is_variable_tempo`
- `onset_rate_mean/max`, `pulse_clarity`, `kick_prominence`, `hp_ratio`

С практической точки зрения:

- `bpm` используется.
- `bpm_stability` и `is_variable_tempo` пока не фильтруют “опасные” треки.
- Groove пока редуцирован к `onset_rate_mean`, что слабее реального groove matching.

## 2.2 Harmony

Есть:

- `key_code`, `key_confidence`, `is_atonal`, `chroma`
- таблица `key_edges` (правила same/adjacent/relative/energy moves)

Практический смысл:

- для melodic techno гармония сильно влияет на субъективное качество перехода.
- для percussive techno гармония менее критична, но не нулевая.

Проблема интеграции:

- в GA-path не используется DB-граф `key_edges` из-за инициализации lookup без DB session.

## 2.3 Energy и timbre

Есть:

- LUFS-блок (`lufs_i`, `lra_lu`, peak/rms)
- 6 частотных band-энергий
- спектральные дескрипторы (`centroid`, `rolloff`, `flatness`, `flux`, `contrast`, `hnr`)

Музыкально:

- LUFS-прыжок напрямую слышен в миксе.
- low/sub конфликт критичен при наложении кика и баса.
- timbre matching полезен для “натурального” ощущения склейки.

Сейчас:

- часть этих сигналов участвует только в отдельных сценариях (или вообще не участвует в генерации сетов).

## 2.4 Structure / phrase logic

Есть:

- `track_sections` со старт/энд, типом секции, энергией, onset, pulse

Практически:

- mix-in/out должен привязываться к intro/outro, breakdown/buildup, phrase boundaries.

Сейчас:

- GA переставляет треки как атомы без выбора конкретных зон входа/выхода.
- `mix_in_ms`, `mix_out_ms` в `dj_set_items` не заполняются (в `dev.db` нули).

## 3) Фактическое состояние музыкальной готовности (по данным)

По `dev.db`:

- `transitions = 0`, `transition_candidates = 0`, `dj_set_feedback = 0`
- `dj_set_items` есть (693), но:
  - `transition_id` не заполнен
  - `mix_in_ms`/`mix_out_ms` не заполнены

То есть:

- порядок треков генерируется,
- но “качество сведения” на уровне точек входа/выхода не материализуется в данных.

## 4) Критичные расхождения с практикой DJ

## 4.1 Нет phrase-locked mixing

Для техно ожидается привязка к 16/32-тактовым блокам.  
Без этого возможны “музыкально неуместные” переключения даже при хорошем BPM/key score.

## 4.2 Нет explicit low-end swap логики

`planned_eq` иногда заполнен, но нет обязательной логики:

- когда убирать бас у входящего/выходящего трека,
- как долго держать overlap,
- где делать bass handoff.

## 4.3 Harmonic policy не учитывает стиль сета

В peak-time/hard techno часто допустимы более резкие harmonic shifts,  
в melodic/progressive — нужна более строгая гармоническая связность.

Система пока не задает style-aware режим (strict vs permissive).

## 4.4 Структура слишком дробная для надежных cue/mix points

`track_sections` в среднем ~75.8 секций на трек при среднем размере ~4.79s.  
Для DJ-практики это слишком мелко: нужен более устойчивый музыкальный сегмент, а не “дрожащие” границы.

## 5) Что нужно сделать, чтобы алгоритм звучал “по-диджейски”

## 5.1 Section-aware transition model

Вместо `track_i -> track_j`:

- `out_section(track_i) -> in_section(track_j)`

С ограничениями:

- минимальная длина overlap
- наличие стабильного ритмического участка
- допустимый low-end конфликт

## 5.2 Phrase compatibility term

Добавить в score:

- кратность длин секций тактовой сетке
- penalty за вход/выход вне phrase boundary

## 5.3 Mix-point extraction (обязательный слой)

Для каждого трека вычислять:

- `mix_in_start_ms`, `mix_in_end_ms`
- `mix_out_start_ms`, `mix_out_end_ms`
- `safe_loop_ranges`

И писать в `dj_set_items` при генерации версии.

## 5.4 Style presets

Профили:

- `melodic_strict`: выше вес harmonic/timbre
- `peak_time_balanced`: баланс harmonic + energy
- `hard_percussive`: ниже harmonic penalty, выше groove/low-end

## 5.5 Loudness-aware transition policy

Музыкально корректный вариант:

- избегать больших `|ΔLUFS|`
- если jump неизбежен, компенсировать planned gain/eq в переходе

## 6) Минимальный набор музыкальных KPI

1. Harmonic continuity:
- доля переходов с допустимым Camelot-правилом (по `key_edges`)

2. Phrase integrity:
- доля переходов, попавших в phrase-safe окна

3. Mix feasibility:
- доля переходов с валидными `mix_in/out` и acceptable overlap

4. Loudness smoothness:
- медиана `|ΔLUFS|` между соседними треками

5. Human validation:
- средний ручной рейтинг переходов (`dj_set_feedback`) по новым версиям

## 7) Резюме

Система уже умеет “упорядочивать треки”, но для реального DJ-quality ей не хватает второго слоя:  
не только “какие треки рядом”, но и “как именно их сводить по музыкальной структуре”.  
Главный шаг к практическому качеству — section-aware/mix-point-aware генерация и сохранение этих решений в данных.
