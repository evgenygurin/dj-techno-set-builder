# DJ Techno Set Builder — Research Brief for Claude Opus 4.6

> **Purpose**: Comprehensive research on algorithmic techno DJ set generation
> **Current State**: Using ~5% of available audio analysis data
> **Goal**: Professional-quality sets matching human DJ performance

---

# Part 1: Data Inventory

## 📊 Currently Available Data (118 tracks analyzed)

### Track Metadata
| Поле | Тип | Источник | Использование |
|------|-----|----------|---------------|
| `track_id` | int | local | Идентификатор |
| `title` | str | local/YM | Название трека |
| `duration_ms` | int | local/YM | Длительность |
| `status` | enum | local | active/archived |

---

### Audio Analysis Features

#### Tempo (4 поля)
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

#### Spectral (9 полей)
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

#### Key & Harmony (4 поля + edges table)
| Поле | Тип | Диапазон | Текущее использование |
|------|-----|----------|----------------------|
| `key_code` | int | 0-23 | ✅ GA transition matrix (примитивно) |
| `key_confidence` | float | 0-1 | ❌ Не используется |
| `is_atonal` | bool | - | ❌ Не используется |
| `chroma` | json | 12 floats | ❌ Не используется (питч-класс профиль) |

**Camelot Wheel (`key_edges` table) — КРИТИЧНО!**
| Поле | Описание | Текущее использование |
|------|----------|----------------------|
| `from_key_code` → `to_key_code` | Связи тональностей | ❌ **НЕ ИСПОЛЬЗУЕТСЯ!** |
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

---

### Structure Analysis (`track_sections` table)
| Поле | Тип | Описание | Текущее использование |
|------|-----|----------|----------------------|
| `section_type` | enum | intro/breakdown/buildup/drop/bridge/outro | ❌ Не используется |
| `start_ms`, `end_ms` | int | Позиция в треке | ❌ |
| `duration_ms` | int | Длительность секции | ❌ |
| `energy` | float | Энергия секции | ❌ |
| `pulse_clarity` | float | Ритмическая четкость | ❌ |

---

### External Metadata (Yandex Music)
| Поле | Тип | Текущее использование |
|------|-----|----------------------|
| `album_title` | str | ❌ Не используется |
| `album_genre` | str | ❌ Не используется |
| `label_name` | str | ❌ Не используется |
| `release_date` | str | ❌ Не используется |

### Catalog Data (Artists, Genres, Labels)
| Таблица | Поля | Текущее использование |
|---------|------|----------------------|
| `artists` | name, name_sort | ❌ Не используется |
| `genres` | name, parent_genre_id | ❌ Не используется |
| `labels` | name, name_sort | ❌ Не используется |

---

## ❌ Missing / Not Computed Data

### Mix Points (критично для реальных DJ переходов!)
| Данные | Как получить | Зачем |
|--------|--------------|-------|
| `mix_in_start_ms` | Анализ intro секции | Оптимальная точка входа |
| `mix_in_end_ms` | Первый drop | Когда перестать миксовать |
| `mix_out_start_ms` | Последний breakdown | Когда начать выход |
| `mix_out_end_ms` | Outro начало | Оптимальная точка выхода |
| `safe_loop_ranges` | Структура + beats | Где можно зациклить для ожидания |

### Transition Compatibility Metrics (не вычисляется!)
| Метрика | Формула | Текущий статус |
|---------|---------|----------------|
| `camelot_distance` | Из key_edges таблицы | ❌ Данные есть, не используются |
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

## 📈 Data Utilization Summary

| Категория | Полей в БД | Используется | % Использования |
|-----------|-----------|--------------|-----------------|
| Tempo | 4 | 1 | 25% |
| Loudness | 7 | 0 | 0% |
| Energy | 11 | 1 | 9% |
| Spectral | 9 | 0 | 0% |
| Key/Harmony | 4 + edges table | 1 | 10% |
| Beats/Groove | 5 | 0 | 0% |
| Structure | sections table | 0 | 0% |
| **ИТОГО** | **41+ полей** | **2-3** | **~5%** |

---

## 🎯 Current Algorithm Limitations

### Transition Matrix (примитивная!)
```python
def _build_transition_matrix(tracks):
    for i, j:
        # BPM component (0-0.5)
        bpm_diff = abs(tracks[i].bpm - tracks[j].bpm)
        bpm_score = max(0, 0.5 - bpm_diff / 20)

        # Key component (0-0.5) — НЕПРАВИЛЬНО!
        key_diff = abs(tracks[i].key_code - tracks[j].key_code)
        key_score = max(0, 0.5 - key_diff / 24)  # Игнорирует Camelot wheel!

        matrix[i][j] = bpm_score + key_score
```

**Проблемы:**
- ❌ Key distance линейный (не учитывает Camelot совместимость)
- ❌ Игнорирует energy bands (kick vs hi-hat совместимость)
- ❌ Нет spectral similarity (тембр)
- ❌ Нет groove matching
- ❌ Нет LUFS matching

---

## 🚀 Improvement Priorities

### High Priority (данные есть, быстро внедрить)
1. ✅ **Camelot wheel** — `key_edges` table уже заполнена!
2. ✅ **Energy band matching** — 6 bands доступны
3. ✅ **TransitionScoringService** — уже написан в кодебазе

### Medium Priority (нужно вычислить)
4. **Spectral similarity** — centroid, rolloff, contrast
5. **Groove compatibility** — kick_prominence + pulse_clarity
6. **Loudness matching** — LUFS для плавности

### Low Priority (требует дополнительной работы)
7. **Mix points** — использовать structure sections
8. **Temporal features** — frame-level analysis
9. **ML predictor** — обучение на feedback

---

## 💾 Recommended: Pre-computed Transition Scores Table

```sql
CREATE TABLE transition_scores (
    from_track_id INT NOT NULL,
    to_track_id INT NOT NULL,

    -- Composite scores
    overall_score REAL NOT NULL,
    camelot_score REAL,
    energy_score REAL,
    spectral_score REAL,
    groove_score REAL,
    loudness_score REAL,

    -- Mix recommendations
    recommended_mix_duration_ms INT,
    optimal_mix_in_point_ms INT,
    optimal_mix_out_point_ms INT,

    -- Metadata
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    algorithm_version TEXT,

    PRIMARY KEY (from_track_id, to_track_id),
    FOREIGN KEY (from_track_id) REFERENCES tracks(track_id),
    FOREIGN KEY (to_track_id) REFERENCES tracks(track_id)
);

CREATE INDEX idx_transition_from ON transition_scores(from_track_id);
CREATE INDEX idx_transition_to ON transition_scores(to_track_id);
CREATE INDEX idx_transition_score ON transition_scores(overall_score DESC);
```

**Использование**:
- Pre-compute матрицу 118×118 = 13,924 переходов
- GA использует готовые scores → ускорение в 100x
- Пересчёт только при изменении алгоритма

---

# Part 2: Research Tasks for Claude Opus 4.6

## Mission

Conduct comprehensive research on **algorithmic techno DJ set generation** to inform development of professional-quality automated DJ system.

**Current bottleneck**: Primitive transition scoring using <5% of available audio analysis data.

**Goal**: Evidence-based recommendations for world-class set generation.

---

## Research Objectives (10 areas)

### 1. DJ Theory & Practice

**Investigate:**
- Professional techno DJ workflows for track selection and ordering
- What defines "good" vs "bad" transitions in techno?
- Key mixing rules: Camelot wheel effectiveness, energy matching, phrase alignment
- Mixing techniques: beatmatching, EQ blending, frequency masking, harmonic mixing
- Set structure patterns: warm-up → peak → breakdown → second peak → outro
- Genre-specific considerations: minimal techno vs peak-time vs industrial

**Sources to search:**
- DJ forums: Resident Advisor, r/DJs, r/Beatmatch, Gearslutz
- DJ education: Crossfader, DJ TechTools, Point Blank, Dubspot
- YouTube tutorials: Phil Harris, Carlo Atendido, Crossfader
- Books: "How to DJ Right" (Brewster), "Last Night a DJ Saved My Life"
- Software docs: Rekordbox, Traktor, Serato analysis features
- DJ podcasts: Transitions, The DJ Sessions

**Key questions:**
- How important is Camelot wheel vs "sounds good together"?
- Do pro DJs prioritize harmonic mixing or energy flow?
- What's typical warm-up BPM progression? (120→128→135?)
- How long should transitions be in techno? (8 bars? 16 bars?)

**Deliverable**:
- Principles of techno set construction
- Rules-of-thumb from pro DJs
- Evidence for/against Camelot wheel strictness
- Typical BPM/energy progression patterns

---

### 2. Audio Features for Transition Quality

**Investigate:**
- Which audio features best predict mixable transitions?
- Feature importance ranking: harmonic > energy > spectral > groove?
- Perceptual weighting: does kick prominence matter more than hi-hat ratio?
- Genre differences: techno vs house vs trance feature priorities

**Research questions:**
- **Harmonic mixing**: Does Camelot wheel correlate with perceived quality? Studies?
- **Energy matching**: Which frequency bands matter most? (kick energy vs hi-hat?)
- **Spectral similarity**: Centroid vs rolloff vs contrast — which predicts "sounds similar"?
- **Groove compatibility**: Does pulse_clarity matching improve transitions?
- **Loudness**: LUFS vs peak vs RMS — which matters for smooth mix?
- **BPM stability**: Filter out variable-tempo tracks?

**Sources to search:**
- Academic papers: "Music Information Retrieval", "Automatic DJ", "Playlist Generation"
- arXiv: cs.SD (Sound), cs.IR (Information Retrieval)
- IEEE/ACM: "music similarity", "harmonic mixing", "DJ automation"
- GitHub: transitions.py, djv, automix projects
- Music tech blogs: iZotope, Waves, Universal Audio
- Patents: Spotify/Apple playlist generation

**Deliverable**:
- Feature importance ranking with citations
- Optimal distance metrics (Euclidean vs Cosine vs ?)
- Perceptual weighting formulas
- Genre-specific recommendations

---

### 3. Transition Scoring Algorithms

**Investigate:**
- State-of-the-art transition quality scoring
- Multi-objective optimization: harmonic + energy + spectral + groove
- Existing formulas from academic/commercial systems
- Temporal considerations: mix duration, phrase alignment, overlap strategies

**Research questions:**
- What scoring formula does Mixed In Key use?
- How does Rekordbox analyze transition compatibility?
- Are ML models better than rule-based scoring?
- How to combine conflicting objectives? (best key match vs best energy match)
- Optimal mix point detection algorithms?

**Sources to search:**
- "Automatic playlist continuation" papers (Spotify Challenge)
- "Music similarity" research (ISMIR conference proceedings)
- DJ software reverse engineering (forums, patents)
- Music recommendation systems (collaborative vs content-based)
- Mix.dj, Pacemaker, Djay Pro — how do they score transitions?

**Deliverable**:
- Recommended scoring formulas with evidence
- Multi-objective aggregation strategies
- Comparison: rule-based vs ML approaches
- Mix point detection algorithms

---

### 4. Set Generation Algorithms

**Investigate:**
- Algorithm comparison for sequence optimization:
  - **Genetic Algorithms** (current approach) — strengths/weaknesses?
  - **Simulated Annealing** — better for local optima?
  - **Reinforcement Learning** — learn from user feedback?
  - **Constraint Satisfaction** — hard rules + soft preferences
  - **Graph algorithms** — TSP formulation, shortest path
- Multi-objective optimization techniques: Pareto fronts, weighted sums, lexicographic

**Research questions:**
- Is GA optimal or should we switch algorithms?
- How to handle competing objectives (harmonic flow vs energy arc)?
- Can RL personalize to user taste over time?
- Graph-based: model as TSP where transitions are edge weights?
- Hybrid approaches: GA for global search + local refinement?

**Sources to search:**
- Operations research: TSP variants, vehicle routing
- "Music playlist generation" papers
- "Sequential recommendation" research
- AI: "multi-objective optimization", "Pareto optimization"
- GitHub: GA libraries, optimization frameworks

**Deliverable**:
- Algorithm comparison table (pros/cons/performance)
- Recommendation: stick with GA or switch?
- Hybrid approach design
- Parameter tuning guidelines (population size, mutation rate, etc.)

---

### 5. Energy Arc Patterns

**Investigate:**
- Typical techno set energy curves
- Genre-specific patterns: warm-up vs peak-time vs closing
- Mathematical models for energy progression
- Multi-peak vs single-peak structures
- Adaptive energy arcs based on available track pool

**Research questions:**
- What's the "classic" techno energy curve? (formula?)
- How many peaks? (one big peak vs wave pattern?)
- Should energy be monotonic rise or have valleys (breakdowns)?
- Do pro DJs follow templates or improvise?
- Energy vs crowd response correlation studies?

**Sources to search:**
- Set analysis: Mixcloud/SoundCloud tracklists with timestamps
- Ben Klock, Amelie Lens, Marcel Dettmann, Nina Kraviz set breakdowns
- DJ mix structure discussions on forums
- "Music dynamics" or "tension/release" academic papers
- Live recording analysis (Boiler Room, Cercle, HÖR)

**Deliverable**:
- Energy arc templates with formulas (warm-up, peak, closing)
- Genre-specific patterns
- Adaptive arc algorithm (fit curve to available tracks)
- Visualization of pro DJ sets vs our algorithm

---

### 6. Mix Point Detection

**Investigate:**
- Identifying optimal mix-in and mix-out points from structure analysis
- Using intro/outro sections effectively
- Beat/phrase alignment importance
- "Safe zones" with low complexity for mixing
- Loop points for waiting/extending tracks

**Research questions:**
- Can we reliably detect intro/outro from `track_sections`?
- What makes a "good mix point"? Low energy? Minimal harmonic content?
- How long should transitions overlap? (4/8/16 bars?)
- Detecting breakdown sections for effect opportunities
- Using `pulse_clarity` to find rhythmically stable zones?

**Sources to search:**
- Music segmentation research (intro/verse/chorus detection)
- Beatmatching algorithms
- DJ software: hot cues, loop markers, auto-cue features
- Music theory: phrase structure, bar counts, song form
- Ableton Live / FL Studio auto-align features

**Deliverable**:
- Mix point detection algorithm using our `track_sections` data
- Recommended mix durations by section type
- Safe loop zone identification
- Phrase alignment strategy

---

### 7. Real-World Examples & Case Studies

**Investigate:**
- Analyze famous techno DJ sets (tracklists with timestamps)
- Extract observable patterns:
  - BPM progression (start→peak→end)
  - Key changes (do they follow Camelot?)
  - Energy flow (visualize arc)
  - Track selection logic (label/artist patterns?)
- Compare human sets to our algorithm output

**DJs to analyze:**
- Ben Klock (Berghain style)
- Marcel Dettmann (dark minimal)
- Amelie Lens (peak-time driving)
- Nina Kraviz (eclectic)
- Adam Beyer (melodic techno)

**Sources:**
- Mixcloud/SoundCloud with tracklists
- Resident Advisor podcasts with track IDs
- Discogs: CD mix releases
- YouTube: Boiler Room, Cercle, HÖR with timestamps
- 1001tracklists.com

**Deliverable**:
- Analysis of 5-10 professional sets
- Patterns: BPM curves, key progressions, energy arcs
- Deviation from "rules" (when do pros break Camelot?)
- Gap analysis: algorithm vs human sets

---

### 8. Evaluation Metrics

**Investigate:**
- Objective metrics for set quality:
  - Transition smoothness (no harsh jumps)
  - Energy arc coherence (follows target curve)
  - Harmonic flow (Camelot compliance %)
  - Variety vs cohesion balance (not too repetitive, not too chaotic)
- Subjective evaluation:
  - User study designs
  - A/B testing methodologies
  - Proxy metrics (skip rate, engagement)

**Research questions:**
- Which objective metrics correlate with human preference?
- Can we predict "crowd energy" from features?
- How to evaluate without extensive user testing?
- Industry standards: what does Spotify measure for playlists?

**Sources to search:**
- Music recommendation evaluation (ISMIR, RecSys conferences)
- UX research in music apps (Spotify, Apple Music)
- "Playlist quality" metrics papers
- DJ community feedback on auto-playlists (reddit threads)

**Deliverable**:
- Evaluation framework with multiple metrics
- Correlation analysis: metric vs human rating
- A/B testing protocol
- Benchmarking targets (e.g., "match human DJ 80% of time")

---

### 9. Edge Cases & Constraints

**Investigate:**
- Handling problematic tracks:
  - Variable BPM (tempo changes mid-track)
  - Atonal/experimental (no clear key)
  - Key changes within track (modulation)
  - Low confidence features (unreliable detection)
- Genre boundaries: techno → minimal → tech-house transitions
- Track filtering: when to exclude "unmixable" tracks?

**Research questions:**
- How to weight low-confidence features?
- Filter threshold: exclude tracks with key_confidence < 0.5?
- Detecting tempo drift vs intentional BPM changes?
- Genre drift tolerance (how far from techno before breaking flow)?

**Sources to search:**
- DJ forums: "hard to mix tracks" discussions
- Music analysis tool limitations (Essentia, librosa docs)
- Beatport/Discogs genre tagging debates
- Error handling in music apps

**Deliverable**:
- Edge case taxonomy
- Filtering rules (when to exclude tracks)
- Confidence weighting strategy
- Genre boundary handling

---

### 10. Tools & Libraries

**Investigate:**
- Open-source DJ automation tools:
  - **Essentia** (current: audio analysis)
  - **librosa** (Python MIR)
  - **Sonic Annotator** (batch processing)
  - **madmom** (beat tracking, tempo)
- DJ software analysis:
  - **Mixed In Key** — harmonic analysis
  - **Rekordbox** — analysis features (beatgrid, phrase, color)
  - **Traktor Pro** — key detection, beatgrid
- Research codebases:
  - GitHub: DJ automation, playlist generation
  - Transitions.py, djv, automix

**Deliverable**:
- Tool comparison (features, accuracy, speed)
- Integration recommendations
- Open issues/limitations in current tools
- Potential replacements for primitives

---

## Research Methodology

For each objective:

1. **Search comprehensively** (2-3 hours per objective):
   - Academic papers: arXiv, Google Scholar, IEEE, ACM Digital Library
   - Technical blogs: Medium, dev.to, Towards Data Science
   - DJ communities: Reddit (r/DJs, r/Beatmatch, r/Techno), Resident Advisor forums
   - Documentation: Rekordbox, Traktor, Essentia, librosa
   - GitHub: search "DJ automation", "playlist generation", "music similarity"
   - YouTube: educational channels (DJ TechTools, Crossfader, Phil Harris)
   - Books: DJ technique, music theory, MIR textbooks

2. **Synthesize findings**:
   - Identify consensus approaches
   - Note conflicting opinions with reasoning
   - Extract actionable formulas/algorithms
   - Cite all sources with links

3. **Prioritize**:
   - **Quick wins**: use existing data better (Camelot wheel, energy bands)
   - **Medium-term**: compute new features (spectral similarity, groove match)
   - **Long-term**: advanced approaches (ML models, RL personalization)

---

## Output Format (per objective)

### [Objective Title]

#### Summary (2-3 paragraphs)
- Key findings
- Consensus in field
- Surprising/counterintuitive results

#### Detailed Findings
1. [Finding with source citation]
2. [Finding with source citation]
...

#### Actionable Recommendations

**✅ Quick wins** (use existing data):
- [Specific action with implementation notes]

**🔧 Medium-term** (requires new computation):
- [Specific action with effort estimate]

**🚀 Long-term** (advanced approaches):
- [Specific action with dependencies]

#### Sources
- [Author, Year, Title, URL/DOI]
- [Author, Year, Title, URL/DOI]
...

#### Open Questions
- [Unanswered questions requiring experimentation]

---

## Success Criteria

Research complete when:
- ✅ All 10 objectives addressed with detailed findings
- ✅ Minimum 20 academic papers cited
- ✅ Minimum 10 practical resources (tutorials, forums, docs)
- ✅ Clear roadmap: quick wins → medium → long-term
- ✅ Specific formulas/algorithms recommended (not just concepts)
- ✅ Evidence-based feature prioritization

---

## Special Focus Areas

Given current state, prioritize:

1. **Camelot wheel effectiveness**
   - Search: "Camelot wheel DJ", "harmonic mixing research", "key compatibility"
   - Goal: Confirm it works, get optimal usage rules

2. **Energy band matching**
   - Search: "frequency band similarity", "spectral matching DJ"
   - Goal: Which of 6 bands matter most for techno?

3. **TransitionScoringService design**
   - Search: "transition quality metric", "mix compatibility score"
   - Goal: Formula combining harmonic + energy + spectral + groove

4. **Mix point detection from structure**
   - Search: "intro detection", "outro detection", "music segmentation"
   - Goal: Use our `track_sections` data effectively

---

## Context & Constraints

- **Genre**: Techno (minimal, peak-time, industrial subtypes)
- **Tech stack**: Python, Essentia, librosa, SQLite/PostgreSQL, FastAPI
- **Current bottleneck**: Transition scoring uses 2 features (BPM, key_code) primitively
- **Goal**: Match/exceed human DJ quality for "filler sets" (warm-up, background)
- **Data**: 118 tracks fully analyzed, 41+ features per track, structure sections, Camelot wheel table

---

## Timeline Estimate

- **Initial research** (broad sweep): 3-4 hours
- **Deep dive** (per objective): 4-6 hours
- **Synthesis** (compile findings): 2 hours
- **Total**: ~10 hours focused research

---

## Deliverable

Comprehensive document with:

1. **Executive Summary** (2 pages)
   - Top 10 findings
   - Immediate action items
   - Long-term vision

2. **Detailed Findings** (50-100 pages)
   - All 10 objectives addressed
   - Evidence with citations
   - Formulas and algorithms

3. **Appendix A**: Full bibliography (sources with URLs)
4. **Appendix B**: Recommended formulas (copy-paste ready)
5. **Appendix C**: Implementation roadmap (prioritized)

---

## Critical Research Questions (TL;DR)

If time-constrained, focus on:

1. **Does Camelot wheel work?** (objective 1, 2)
2. **Which features predict good transitions?** (objective 2)
3. **Best transition scoring formula?** (objective 3)
4. **Is GA the right algorithm?** (objective 4)
5. **How do pro DJs structure sets?** (objective 7)

---

## Additional Notes

- **Emphasize evidence** — cite sources, don't speculate
- **Include code** — GitHub links, formulas, pseudocode
- **Note conflicts** — if field disagrees, present both sides
- **Be quantitative** — "Algorithm A outperforms B by 15%" not "A is better"
- **Consider cost** — real-time vs batch processing tradeoffs

---

## Ready to Begin

Start comprehensive research. Take your time. Be thorough. Cite extensively.

**Surprise me with insights I didn't know to ask for.**

Go! 🚀
