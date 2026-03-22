# MCP DJ-Techno Tools — Checklist (2026-02-20)

Полный тест всех инструментов с реальными данными из БД.
- **DB**: iCloud SQLite (1423 треков, 584 проанализированы, 2 плейлиста, 6 сетов)
- **YM user**: 250905515 (sitemakerz / DJ Music)
- **Write ops**: тест + откат (create → verify → delete)

---

## Итог

| Категория | Всего | ✅ Работает | ⚠️ Работает с оговоркой | ❌ Сломан |
|-----------|-------|------------|------------------------|-----------|
| DJ Tools  | 20    | 20         | 0                      | 0         |
| YM Tools  | 28    | 22         | 4                      | 2         |
| **Итого** | **48**| **42**     | **4**                  | **2**     |

---

## DJ Tools (20/20 ✅)

### Tracks — Read (4/4)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 1 | `dj_list_tracks` | ✅ | 1423 треков, пагинация cursor работает, stats в ответе |
| 2 | `dj_get_track` | ✅ | Полный TrackDetail с genres/labels/albums/platform_ids |
| 3 | `dj_search` | ✅ | Fuzzy-поиск по title, возвращает categorized results + stats |
| 4 | `dj_filter_tracks` | ✅ | BPM 130-145 → 76 треков, key/energy_lufs в ответе |

### Tracks — Write (3/3 + rollback)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 5 | `dj_create_track` | ✅ | Создал `local:146616954`, total: 1423→1424 |
| 6 | `dj_update_track` | ✅ | Обновил title, возвращает обновлённый TrackDetail |
| 7 | `dj_delete_track` | ✅ | Удалил, total вернулся к 1423 |

### Playlists (6/6)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 8 | `dj_list_playlists` | ✅ | 2 плейлиста ("Techno Develop Recs", "Techno develop") |
| 9 | `dj_get_playlist` | ✅ | PlaylistDetail с analyzed_count, keys, duration |
| 10 | `dj_create_playlist` | ✅ | Создал `local:3` |
| 11 | `dj_update_playlist` | ✅ | Переименовал плейлист |
| 12 | `dj_delete_playlist` | ✅ | Удалил, playlists: 3→2 |

### Sets (5/5)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 13 | `dj_list_sets` | ✅ | 6 сетов с version_count/track_count |
| 14 | `dj_get_set` | ✅ | SetDetail с latest_version_id |
| 15 | `dj_create_set` | ✅ | Создал `local:7` с description |
| 16 | `dj_update_set` | ✅ | Переименовал |
| 17 | `dj_delete_set` | ✅ | Удалил, sets: 7→6 |

### Features (3/3)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 18 | `dj_list_features` | ✅ | 579 треков с BPM/key/energy_lufs |
| 19 | `dj_get_features` | ✅ | Полный набор: BPM, key, LUFS, spectral, MFCC, HP-ratio, onset, chroma |
| 20 | `dj_save_features` | ✅ | Сохранил фичи для local:223 (analyzed: 584→585) |

---

## YM Tools (22/28 ✅, 4 ⚠️, 2 ❌)

> Все ключи и аутентификация настроены. Используемые IDs:
> - artistId: **481113** (Boris Brejcha)
> - albumId: **8628586** (Carbon — Deep Breath)
> - trackId: **16188235** (Boris Brejcha — Purple Noise)
> - userId: **250905515**

### Search & Discovery (3/3)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 1 | `ym_search_yandex_music` | ✅ | type=artist нашёл Boris Brejcha (id=481113), total 12 |
| 2 | `ym_get_search_suggestions` | ✅ | 11 suggestions + best match = artist объект |
| 3 | `ym_get_genres` | ⚠️ **Huge response** | Работает, но возвращает **177k символов** — превышает лимит MCP (файл сохранён). Не использовать в продакшн без фильтрации. |

### Albums (3/3)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 4 | `ym_get_album_by_id` | ✅ | Полный Album с artists/labels/cover/derivedColors |
| 5 | `ym_get_albums_with_tracks` | ✅ | Album + volumes с треками + pager |
| 6 | `ym_get_albums_by_ids` | ✅ | Принимает CSV: "8628586,9820225" → 2 альбома |

### Artists (3/4)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 7 | `ym_get_artist_brief_info` | ❌ **HTTP 403** | Yandex CAPTCHA/smart-antirobot. Стабильная ошибка при каждом вызове. Endpoint `/artists/{id}/brief-info` заблокирован. |
| 8 | `ym_get_artist_tracks` | ✅ | 314 треков Boris Brejcha, pager работает |
| 9 | `ym_get_artist_direct_albums` | ✅ | 78 альбомов, sort-by=year работает |
| 10 | `ym_get_popular_tracks` | ✅ | Массив из 300+ track IDs (только ID, без мета) |

### Tracks (4/5)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 11 | `ym_get_tracks` | ✅ | Массив track-ids → полные объекты с artists/albums |
| 12 | `ym_get_track_supplement` | ⚠️ **Пустой** | Возвращает `{"id":"16188235"}` — нет текста, нет видео. Endpoint работает, но данных нет для данного трека (лирика недоступна) |
| 13 | `ym_get_similar_tracks` | ✅ | 20 похожих треков с полными объектами + объект source track |
| 14 | `ym_get_download_info` | ✅ | 2 ссылки: mp3 192kbps + 320kbps (signed URLs) |
| 15 | `ym_get_track_lyrics` | ❌ **HTTP 400** | Требует скрытые параметры `timeStamp` и `sign` (HMAC-подпись запроса). Без них: `"Parameters requirements are not met"`. Инструмент неиспользуем без генерации подписи. |

### Playlists — Read (5/5)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 16 | `ym_get_play_lists` | ⚠️ **Huge response** | Работает, но **86k символов** — превышает лимит MCP. Использовать с осторожностью. |
| 17 | `ym_get_playlist_by_id` | ⚠️ **Huge response** | Работает, но **154k символов** для плейлиста из 557 треков. |
| 18 | `ym_get_playlists_by_ids` | ✅ | Принимает `["uid:kind", ...]` → массив PlaylistFull без треков |
| 19 | `ym_get_user_playlists_by_ids` | ✅ | kinds=CSV → плейлисты с треками (без rich-tracks — только id/albumId) |
| 20 | `ym_get_playlists_ids_by_tag` | ✅ | tagId="techno" → 7 плейлистов ({uid, kind}) |

### Likes (4/4)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 21 | `ym_get_liked_tracks_ids` | ✅ | 394 трека с id/albumId/timestamp (revision: 1937) |
| 22 | `ym_get_disliked_tracks_ids` | ✅ | 73 трека с id/albumId/timestamp |
| 23 | `ym_like_tracks` | ✅ | revision: 1937→1938 |
| 24 | `ym_remove_liked_tracks` | ✅ | revision: 1938→1939 (rollback выполнен) |

### Playlist Write (5/5 + rollback)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| 25 | `ym_create_playlist` | ✅ | Создал kind:1273 "__TEST_PLAYLIST_MCP__" (private) |
| 26 | `ym_rename_playlist` | ✅ | Переименовал в "__TEST_PLAYLIST_MCP_RENAMED__" |
| 27 | `ym_change_playlist_visibility` | ✅ | private → public |
| 28 | `ym_change_playlist_tracks` | ✅ | insert op: добавил трек 57383136, trackCount: 0→1, revision: 1→2 |
| — | `ym_delete_playlist` | ✅ | Удалил kind:1273, вернул `"ok"` (rollback) |

### Recommendations (1/1)

| # | Инструмент | Статус | Результат |
|---|-----------|--------|-----------|
| — | `ym_get_recommendations` | ✅ | 5 рекомендаций для плейлиста kind:3 |

---

## Проблемы и решения

### ❌ `ym_get_artist_brief_info` → HTTP 403

**Причина**: Yandex Smart Antirobot блокирует endpoint `/artists/{id}/brief-info`.
Другие artist endpoints (`artist_tracks`, `direct_albums`, `popular_tracks`) работают нормально.

**Решение**: Использовать `ym_search_yandex_music(type=artist)` для получения brief info через search results (там есть cover, genres, counts, links).

---

### ❌ `ym_get_track_lyrics` → HTTP 400 (requires sign + timestamp)

**Причина**: Яндекс.Музыка требует HMAC-подпись и timestamp для endpoint лирики.
Параметры `sign` и `timeStamp` обязательны, но не задокументированы в инструменте.

**Решение**: Реализовать генерацию подписи в YM gateway или убрать инструмент из публичного API.

---

### ⚠️ Huge responses (genres, playlists)

| Инструмент | Размер | Решение |
|-----------|--------|---------|
| `ym_get_genres` | ~177k символов | Добавить серверную фильтрацию по genre name/ID |
| `ym_get_playlist_by_id` | ~154k для 557 треков | Добавить параметр `page`/`limit` для треков |
| `ym_get_play_lists` | ~86k | Добавить `limit` / фильтр плейлистов пользователя |

---

### ⚠️ `ym_get_track_supplement` возвращает пустые данные

**Причина**: Endpoint возвращает только доступные данные. Для треков без текста/видео → `{"id": "..."}`.
Это ожидаемое поведение API. Не ошибка инструмента.

---

## Заметки по формату

- **`dj_filter_tracks`**: `energy_min/max` — это LUFS (отрицательные значения), не normalized energy
- **`ym_change_playlist_tracks`**: поле `diff` — JSON **array** `[{"op":"insert",...}]`, NOT object
- **`ym_get_playlists_by_ids`**: playlistIds format = `"uid:kind"` (строка через двоеточие)
- **`dj_save_features`**: `mfcc_vector` — строка JSON, не массив: `"[127.0, -13.0, ...]"`
- **`ym_get_popular_tracks`**: возвращает только массив track IDs, без мета — нужен отдельный `ym_get_tracks`
