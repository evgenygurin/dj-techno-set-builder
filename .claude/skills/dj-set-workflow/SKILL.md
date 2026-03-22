---
name: dj-set-workflow
description: Use when building DJ sets, scoring transitions, delivering sets, syncing to YM playlists, or improving set quality. Triggers on build_set, deliver_set, score_transitions, rebuild_set, "построй сет", "экспортируй сет".
---

# DJ Set Workflow

## Философия

Работа с DJ-сетами — это не скрипт. Это серия решений, которые принимаются на основании того, что уже есть в контексте разговора.

Прочитай диалог. Определи, где находится пользователь в процессе. Действуй с того места, где он находится, а не с начала.

---

## Точки входа — определи по контексту

| Что есть в контексте | С чего начать |
|----------------------|---------------|
| Название плейлиста, нет сета | → `dj_get_playlist` → `dj_build_set` |
| set_id + version_id есть | → `dj_score_transitions` → `dj_deliver_set` |
| Просят "доставить", "экспортировать", "синхронизировать" | → `dj_deliver_set` напрямую |
| Плохие переходы, просят улучшить | → `dj_score_transitions` → `dj_rebuild_set` |
| Ничего нет, нужно собрать с нуля | → `ym_search_tracks` → `dj_build_set` |

---

## Инструменты и что они возвращают

### Разведка (read-only, без последствий)

```text
dj_search(query)                    → tracks[] с BPM/key/energy
dj_filter_tracks(bpm_min, bpm_max)  → tracks[] по параметрам
dj_get_playlist(playlist_ref)       → playlist с items[]
dj_get_track_details(track_ref)     → audio features трека
dj_score_transitions(set_ref, version_id) → TransitionScoreResult[]
```

### Построение

```text
dj_build_set(playlist_ref, template, duration_minutes)
  → SetBuildResult(set_id, version_id, avg_transition_score, energy_curve[])

dj_rebuild_set(set_ref, version_id, feedback)
  → новый version_id с учётом пинов и исключений
```

### Доставка (3 видимых этапа)

```text
dj_deliver_set(set_ref, version_id, sync_to_ym?, ym_user_id?, ym_playlist_title?)
  → DeliveryResult(set_id, version_id, set_name, output_dir, files_written[], transitions, ym_playlist_kind?, status)
```

Этапы `deliver_set` — видимые, не скрытые:
- **Stage 1** — scoring: если `hard_conflicts > 0`, пользователю задаётся вопрос — продолжать или остановиться
- **Stage 2** — запись файлов: M3U8, JSON guide, cheat_sheet.txt
- **Stage 3** — YM sync (только если `sync_to_ym=True` и `ym_user_id` задан)

---

## Качество переходов — пороги

```text
1.0       идеальный (тот же Camelot-ключ)
≥ 0.85    хороший
0.0–0.84  слабый → помечается !!! в cheat_sheet
0.0       жёсткий конфликт (Camelot dist ≥ 5 или нет фич)
```

Hard conflicts — не ошибка, а сигнал. Пользователь решает, продолжать ли.

---

## YM sync — когда возможен

- `ym_user_id` обязателен
- Трек попадёт в плейлист YM если:
  - есть строка в `yandex_metadata` (таблица с `yandex_track_id`)
  - ИЛИ `track_id > 1_000_000` (YM native-трек, без album_id — будет пропущен с warning)
- YM-ошибка — не блокирует: файлы уже записаны, статус остаётся `"ok"`

---

## Что сообщать пользователю после deliver_set

Минимальный отчёт:

```text
Сет «{set_name}» доставлен в {output_dir}

Переходы: {total} / жёстких: {hard_conflicts} / слабых: {weak}
Средний score: {avg_score:.3f}

Файлы: {files_written}
YM playlist: kind={ym_playlist_kind}  ← если sync_to_ym
```

Если `hard_conflicts > 0` или `avg_score < 0.6` — упомянуть отдельно.

---

## Что НЕ делать

- Не запускать `dj_deliver_set` без `version_id` — нужна конкретная версия
- Не синхронизировать в YM без явного согласия пользователя
- Не пересобирать сет без причины — если `avg_score ≥ 0.75`, он скорее всего хорош
- Не вызывать `dj_compute_audio_features` без нужды — тяжёлая операция, только по запросу
