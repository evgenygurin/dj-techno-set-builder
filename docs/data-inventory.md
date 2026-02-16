# DJ Techno Set Builder — Data Inventory

## 📊 Имеющиеся данные

### Track Metadata
| Поле | Тип | Источник | Использование |
|------|-----|----------|---------------|
| `track_id` | int | local | Идентификатор |
| `title` | str | local/YM | Название трека |
| `duration_ms` | int | local/YM | Длительность |
| `status` | enum | local | active/archived |

### Audio Analysis Features (118 треков)

#### Tempo
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `bpm` | float | 20-300 | ✅ GA transition matrix |
| `tempo_confidence` | float | 0-1 | ❌ Не используется |
| `bpm_stability` | float | 0-1 | ❌ Не используется |
| `is_variable_tempo` | bool | - | ❌ Не используется |

#### Loudness (7 полей)
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `lufs_i` | float | -70 to 0 | ❌ Не используется |
| `lufs_s_mean` | float | -70 to 0 | ❌ Не используется |
| `lufs_m_max` | float | -70 to 0 | ❌ Не используется |
| `rms_dbfs` | float | -∞ to 0 | ❌ Не используется |
| `true_peak_db` | float | -∞ to 0 | ❌ Не используется |
| `crest_factor_db` | float | 0+ | ❌ Не используется |
| `lra_lu` | float | 0+ | ❌ Не используется |

#### Energy (11 полей)
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `energy_mean` | float | 0-1 | ✅ GA energy arc (как proxy для global_energy) |
| `energy_max` | float | 0-1 | ❌ Не используется |
| `energy_std` | float | 0-1 | ❌ Не используется |
| `sub_energy` | float | 0-1 | ❌ Не используется (20-60 Hz) |
| `low_energy` | float | 0-1 | ❌ Не используется (60-250 Hz, kick) |
| `lowmid_energy` | float | 0-1 | ❌ Не используется (250-500 Hz) |
| `mid_energy` | float | 0-1 | ❌ Не используется (500-2k Hz) |
| `highmid_energy` | float | 0-1 | ❌ Не используется (2k-4k Hz) |
| `high_energy` | float | 0-1 | ❌ Не используется (4k+ Hz, hi-hats) |
| `low_high_ratio` | float | 0+ | ❌ Не используется |
| `sub_lowmid_ratio` | float | 0+ | ❌ Не используется |
| `energy_slope_mean` | float | ±∞ | ❌ Не используется |

#### Spectral (7 полей)
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `centroid_mean_hz` | float | 0-22050 | ❌ Не используется (тембр) |
| `rolloff_85_hz` | float | 0-22050 | ❌ Не используется |
| `rolloff_95_hz` | float | 0-22050 | ❌ Не используется |
| `flatness_mean` | float | 0-1 | ❌ Не используется (шум vs тоны) |
| `flux_mean` | float | 0+ | ❌ Не используется (изменчивость) |
| `flux_std` | float | 0+ | ❌ Не используется |
| `slope_db_per_oct` | float | ±∞ | ❌ Не используется |
| `contrast_mean_db` | float | 0+ | ❌ Не используется |
| `hnr_mean_db` | float | ±∞ | ❌ Не используется (harmonic-to-noise) |

#### Key & Harmony (4 поля + chroma)
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `key_code` | int | 0-23 | ✅ GA transition matrix (примитивно) |
| `key_confidence` | float | 0-1 | ❌ Не используется |
| `is_atonal` | bool | - | ❌ Не используется |
| `chroma` | json | 12 floats | ❌ Не используется (питч-класс профиль) |

**Camelot Wheel (key_edges table)**:
| Поле | Описание | Текущее использование |
|------|----------|----------------------|
| `from_key_code` → `to_key_code` | Связи тональностей | ❌ НЕ ИСПОЛЬЗУЕТСЯ! |
| `distance` | 0 (same), 1 (adjacent), 2 (boost/drop) | ❌ |
| `weight` | Качество перехода (0.7-1.0) | ❌ |
| `rule` | same_key, camelot_adjacent, relative_major_minor, energy_boost/drop | ❌ |

#### Beats & Groove (5 полей)
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `onset_rate_mean` | float | 0+ | ❌ Не используется (атаки/сек) |
| `onset_rate_max` | float | 0+ | ❌ Не используется |
| `pulse_clarity` | float | 0-1 | ❌ Не используется (ритмическая четкость) |
| `kick_prominence` | float | 0-1 | ❌ Не используется (выраженность кика) |
| `hp_ratio` | float | 0-1 | ❌ Не используется (hat/perc соотношение) |

### Structure Analysis (track_sections table)
| Поле | Тип | Описание | Текущее использование |
|------|-----|----------|----------------------|
| `section_type` | enum | intro/breakdown/buildup/drop/bridge/outro | ❌ Не используется |
| `start_ms`, `end_ms` | int | Позиция в треке | ❌ |
| `duration_ms` | int | Длительность секции | ❌ |
| `energy` | float | Энергия секции | ❌ |
| `pulse_clarity` | float | Ритмическая четкость | ❌ |

### Yandex Music Metadata
| Поле | Тип | Текущее использование |
|------|-----|----------------------|
| `album_title` | str | ❌ Не используется |
| `album_genre` | str | ❌ Не используется |
| `label_name` | str | ❌ Не используется |
| `release_date` | str | ❌ Не используется |

### Artists & Genres (связанные таблицы)
| Таблица | Поля | Текущее использование |
|---------|------|----------------------|
| `artists` | name, name_sort | ❌ Не используется |
| `genres` | name, parent_genre_id | ❌ Не используется |
| `labels` | name, name_sort | ❌ Не используется |

---

## 🔌 MCP / OpenAI: контекст и рекомендованные серверы

Этот документ описывает данные. На практике LLM получает доступ к ним через MCP-инструменты.

### Что уже есть в репозитории

- **DJ Set Builder MCP gateway**: `fastmcp.json` + `app/mcp/gateway.py` — единый сервер, который монтирует:
  - `ym` (Yandex Music) — провайдерные инструменты
  - `dj` (Workflows) — инструменты для анализа/поиска/сборки сета/экспорта
- **HTTP транспорт для клиентов**: `make mcp-dev` → `http://localhost:9100/mcp`
- **ASGI-монтирование внутри API**: `make run` → MCP на `/mcp/mcp`
- **Клиентский конфиг-пример**: `.mcp.json` (подключение к `dj-techno`)

### “Базовый стек” MCP-серверов (полезно подключать к OpenAI-клиенту рядом с `dj-techno`)

- **Filesystem (read-only)**: доступ к `docs/`, конфигам, экспортам — чтобы LLM мог ссылаться на факты из репозитория.
- **Git**: история изменений/контекст решений (diff/blame/log) без ручного копипаста.
- **DB (SQLite/PostgreSQL)**: ad-hoc запросы/агрегации по каталогу, фичам, переходам (удобно для проверки гипотез из scoring).
- **HTTP fetch / web-search** (опционально): если нужен актуальный ресёрч с цитатами — лучше с allowlist доменов и жёсткими лимитами.
- **Browser automation** (опционально): когда нужен JS-heavy веб/формы/логины (часто для ресёрча и сверки источников).

### Минимальная безопасность (чтобы не подставиться)

- **Принцип наименьших прав**: read-only FS, allowlist путей/домена, без доступа к `/` и домашним директориям.
- **Отдельные креды**: для БД — отдельный read-only пользователь; для провайдеров — отдельные токены.
- **Секреты не в логах**: редактирование (redaction) токенов/ключей, request-id корреляция.

---

## ❌ Недостающие данные

### Mix Points (критично для DJ!)
| Данные | Как получить | Зачем |
|--------|--------------|-------|
| `mix_in_start_ms` | Анализ intro секции | Оптимальная точка входа |
| `mix_in_end_ms` | Первый drop | Когда перестать миксовать |
| `mix_out_start_ms` | Последний breakdown | Когда начать выход |
| `mix_out_end_ms` | Outro начало | Оптимальная точка выхода |
| `safe_loop_ranges` | Структура + beats | Где можно зациклить для ожидания |

### Transition Compatibility (сейчас не вычисляется!)
| Метрика | Формула | Текущий статус |
|---------|---------|----------------|
| `camelot_distance` | Из key_edges таблицы | ❌ Есть в БД, НЕ используется |
| `energy_band_match` | Euclidean dist по 6 bands | ❌ Не вычисляется |
| `spectral_similarity` | Cosine similarity (centroid, rolloff, etc) | ❌ Не вычисляется |
| `groove_compatibility` | kick_prominence + pulse_clarity match | ❌ Не вычисляется |
| `loudness_jump` | abs(lufs_i[A] - lufs_i[B]) | ❌ Не вычисляется |

### Temporal Features (динамика во времени)
| Данные | Как получить | Зачем |
|--------|--------------|-------|
| `energy_evolution` | Frame-level analysis | Кривая энергии для визуализации |
| `bpm_evolution` | Beat tracking with time | Detect tempo changes |
| `key_changes` | Chroma tracking | Треки с модуляцией |

### User Feedback (для ML)
| Данные | Источник | Статус |
|--------|----------|--------|
| `transition_rating` | Ручная разметка | ❌ Нет таблицы |
| `set_rating` | Feedback после прослушивания | ✅ Есть `dj_set_feedback` (но не используется) |

---

## 📈 Использование данных: текущее vs потенциал

| Категория | Полей в БД | Используется | Потенциал неиспользован |
|-----------|-----------|--------------|-------------------------|
| Tempo | 4 | 1 (25%) | bpm_stability для фильтрации |
| Loudness | 7 | 0 (0%) | LUFS matching для плавности |
| Energy | 11 | 1 (9%) | Band matching для совместимости |
| Spectral | 9 | 0 (0%) | Тембральное сходство |
| Key | 4 + edges | 1 (10%) | Camelot wheel |
| Beats | 5 | 0 (0%) | Groove matching |
| Structure | sections | 0 (0%) | Mix points |

**Итого: используется ~5% данных!**

---

## 🎯 Приоритеты для улучшения

### High Priority (быстро + большой эффект)
1. **Camelot wheel** — данные есть в key_edges, просто использовать
2. **Energy band matching** — данные есть (6 bands), вычислить Euclidean distance
3. **TransitionScoringService** — уже написан, просто внедрить

### Medium Priority (нужно вычислить)
4. **Spectral similarity** — использовать centroid, rolloff, contrast
5. **Groove compatibility** — kick_prominence + pulse_clarity
6. **Loudness matching** — LUFS для плавных переходов

### Low Priority (требует дополнительного анализа)
7. **Mix points** — использовать structure sections
8. **Temporal features** — frame-level analysis
9. **ML predictor** — обучить на feedback

---

## 💾 Сохранить результаты scoring

Создать таблицу `transition_scores`:
```sql
CREATE TABLE transition_scores (
    from_track_id INT,
    to_track_id INT,

    -- Composite scores
    overall_score REAL,        -- Общий transition score
    camelot_score REAL,        -- Тональная совместимость
    energy_score REAL,         -- Energy band matching
    spectral_score REAL,       -- Тембральное сходство
    groove_score REAL,         -- Ритмическая совместимость
    loudness_score REAL,       -- LUFS matching

    -- Mix recommendations
    recommended_mix_duration_ms INT,
    optimal_mix_in_point_ms INT,
    optimal_mix_out_point_ms INT,

    -- Metadata
    computed_at TIMESTAMP,
    algorithm_version TEXT,

    PRIMARY KEY (from_track_id, to_track_id)
);
```

**Использование**: Pre-compute матрицу переходов → ускорение GA в 100x
