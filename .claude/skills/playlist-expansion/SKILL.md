---
name: playlist-expansion
description: Use when expanding playlists with new tracks, discovering similar tracks, importing from YM, auditing quality, or distributing by subgenre. Triggers on "расширь плейлист", "найди похожие", "заполни плейлист", "expand playlist", "fill playlist", discover_candidates, audit_playlist, distribute_to_subgenres.
---

# Playlist Expansion Workflow

Автоматическое расширение DJ-плейлиста: поиск → фильтрация → импорт → download → анализ → аудит → субжанры.

## Два режима

### Полный pipeline (download + audio analysis)
Используй скрипт напрямую — он делает download MP3 + audio analysis в subprocess:
```bash
uv run python scripts/fill_and_verify.py --kind <ym_kind> --target <N> --workers 4
```
Или через slash-команду: `/fill-playlist <kind> <target>`

### Лёгкий режим (только discover + import, без download/analyze)
Используй MCP tool — мгновенный, но без аудио-верификации:
```text
dj_expand_playlist_full(playlist_id=24, seed_count=3, batch_size=15)
```

---

## Pipeline (6 фаз)

### Phase 1: Разведка
Узнай текущее состояние плейлиста.

```text
dj_get_playlist(playlist_ref)     → track_count, analyzed_count
dj_audit_playlist(playlist_id)    → passed, failed, no_features, failures[]
```

Если audit показывает failures — сообщи пользователю перед расширением.

### Phase 2: Поиск кандидатов
Выбери seed-трек из плейлиста и найди похожие.

```text
dj_get_set_tracks(set_ref) или dj_filter_tracks(...)  → выбрать seed
dj_discover_candidates(seed_track_id, batch_size=20, exclude_track_ids=[...])
  → candidates[] с ym_track_id, title, artists, duration, genre
```

**Стратегия seed**: бери треки из середины плейлиста (уже проверенные).
**exclude**: передавай все track_ids уже в плейлисте — не дублировать.

### Phase 3: Импорт + Скачивание
Для каждого кандидата:

```text
dj_populate_from_ym(playlist_id, ym_kind)  — для массового импорта
ИЛИ
dj_create_track(title, duration_ms) → track_id   — поштучно
dj_download_tracks(track_ids)                     — скачать MP3
```

### Phase 4: Анализ
Запусти аудио-анализ для новых треков:

```text
dj_analyze_track(track_id)  — полный pipeline (BPM, LUFS, energy, spectral)
```

Это тяжёлая операция — сообщи пользователю про время.

### Phase 5: Аудит качества
Проверь все новые треки против техно-критериев:

```text
dj_audit_playlist(playlist_id) → passed, failed, failures[]
```

Критерии: BPM 120-155, LUFS -20..-4, kick>0.05, onset>1.0, centroid 300-10000.
Треки не прошедшие аудит — предложи удалить.

### Phase 6: Классификация по субжанрам
Распредели прошедшие треки по 15 субжанровым плейлистам:

```text
dj_distribute_to_subgenres(playlist_id) → distribution {mood: count}
```

15 субжанров: ambient_dub, dub_techno, minimal, detroit, melodic_deep,
progressive, hypnotic, driving, tribal, breakbeat, peak_time, acid,
raw, industrial, hard_techno.

---

## Режимы использования

### Quick (1 seed, ~20 треков)
```text
Пользователь: "расширь плейлист 24"
→ Phase 1-2 (один seed) → Phase 3-6
```

### Deep (несколько seeds, ~100+ треков)
```text
Пользователь: "заполни плейлист 24 до 200 треков"
→ Цикл: Phase 2-5 повторять с разными seeds пока не достигнут target
→ Phase 6 в конце
```

### Audit Only
```text
Пользователь: "проверь качество плейлиста 24"
→ Phase 1 + Phase 5 только
```

### Distribute Only
```text
Пользователь: "распредели треки по субжанрам"
→ Phase 6 только
```

---

## Ключевые правила

- **НЕ дублируй логику** — всё через MCP tools
- **Сообщай прогресс** на каждой фазе: "Phase 3/6 — скачиваю 15 треков..."
- **Exclude уже обработанных** — передавай exclude_track_ids чтобы не дублировать
- **Feedback gate**: если у пользователя есть liked/disliked списки — спроси перед началом
- **Batch**: не обрабатывай все 100 треков сразу — батчами по 10-20

---

## Iron Law

```text
NO IMPORT WITHOUT DUPLICATE CHECK AND EXCLUDE LIST
```

Каждый `discover_candidates` ДОЛЖЕН получать `exclude_track_ids` со всеми track_ids уже в плейлисте. Дубликаты = битый sort_index + лишние скачивания.

## Red Flags

| Отговорка | Реальность |
|-----------|------------|
| "Дубликатов не будет" | YM API возвращает похожие треки — часть уже в плейлисте |
| "Пропущу аудит" | Без аудита в плейлист попадут non-techno треки (BPM<120, no kick) |
| "Сразу импортирую 100 штук" | Батчи по 10-20 + exclude на каждом шаге — иначе дубли |
| "Seed не важен" | Seed из середины плейлиста даёт лучшие результаты чем из начала |
