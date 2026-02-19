# Fix DB Data Gaps — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all missing/broken data in dev.db so every track has complete metadata, full audio analysis, and correct provider references.

**Architecture:** One-off data fix script + code fixes to prevent recurrence. All fixes are idempotent (safe to re-run).

**Tech Stack:** Python 3.12, SQLAlchemy async, SQLite (dev.db), existing app services

---

## Диагностика (что сломано)

| # | Проблема | Масштаб | Причина |
|---|----------|---------|---------|
| 1 | `yandex_metadata` таблица не существует | 0/118 треков | Модель добавлена после создания dev.db, `create_all()` не перезапускался |
| 2 | Provider ID mismatch: yandex_music=1 вместо 4 | 118 provider_track_ids + 118 track_genres | One-off скрипт создал provider с id=1 до появления seeder |
| 3 | Отсутствуют providers spotify/soundcloud/beatport | 0 из 3 | Seeder не смог создать id=1 (spotify) — конфликт PK с yandex_music |
| 4 | `keys` таблица пустая | 0/24 ключа | Seed данные из DDL не загружены |
| 5 | `key_edges` таблица пустая | 0 рёбер | Зависит от keys |
| 6 | 52 трека с partial analysis (нет groove/sections) | tracks 67-118 | analyze_all.py: вторая партия без full_analysis |
| 7 | 5 треков с дублями feature runs | tracks 1,13,16,19,23 | Повторный запуск анализа |
| 8 | `raw_provider_responses` пустая | 0/118 | One-off скрипт не сохранял сырые ответы |
| 9 | `title_sort` = NULL у всех треков | 0/118 | Никогда не вычислялся |
| 10 | `labels.name_sort` = NULL | 0/88 | Никогда не вычислялся |

---

### Task 1: Создать таблицу yandex_metadata в dev.db

**Files:**
- Create: `scripts/fix_db_gaps.py`

**Step 1: Написать скрипт создания таблицы**

```python
"""Fix dev.db data gaps — run once to repair all known issues."""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, init_db, session_factory
from app.models import Base  # noqa: F401 — triggers all model registrations

async def fix_create_missing_tables() -> None:
    """Create any tables that exist in ORM but not in DB (e.g. yandex_metadata)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[1/7] Missing tables created (yandex_metadata etc.)")

async def main() -> None:
    await init_db()
    await fix_create_missing_tables()
    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Запустить и проверить**

Run: `uv run python scripts/fix_db_gaps.py`
Expected: таблица `yandex_metadata` появляется в dev.db

Verify: `sqlite3 dev.db ".tables" | grep yandex_metadata`

**Step 3: Commit**

```bash
git add scripts/fix_db_gaps.py
git commit -m "fix(db): add fix_db_gaps script — create missing tables"
```

---

### Task 2: Исправить provider ID mismatch

Текущее состояние: yandex_music имеет provider_id=1, а по DDL должен быть id=4.
Нужно: переназначить yandex_music → id=4, создать spotify=1, soundcloud=2, beatport=3.

**Files:**
- Modify: `scripts/fix_db_gaps.py`

**Step 1: Добавить функцию fix_providers**

```python
async def fix_providers(session: AsyncSession) -> None:
    """Fix provider IDs: yandex_music should be 4, not 1."""
    from app.models.providers import Provider

    # Check current state
    result = await session.execute(
        text("SELECT provider_id, provider_code FROM providers ORDER BY provider_id")
    )
    current = {row.provider_code: row.provider_id for row in result}

    if current.get("yandex_music") == 1:
        # Step 1: Temporarily reassign yandex_music to id=4
        # First create id=4 slot
        await session.execute(
            text("UPDATE providers SET provider_id = 4 WHERE provider_code = 'yandex_music'")
        )
        # Update all FK references
        await session.execute(
            text("UPDATE provider_track_ids SET provider_id = 4 WHERE provider_id = 1")
        )
        await session.execute(
            text("UPDATE track_genres SET source_provider_id = 4 WHERE source_provider_id = 1")
        )
        print("  - yandex_music: 1 → 4 (+ FK references updated)")

    # Seed missing providers
    expected = {1: ("spotify", "Spotify"), 2: ("soundcloud", "SoundCloud"), 3: ("beatport", "Beatport"), 4: ("yandex_music", "Yandex Music")}
    for pid, (code, name) in expected.items():
        exists = await session.execute(
            text("SELECT 1 FROM providers WHERE provider_id = :id"), {"id": pid}
        )
        if not exists.scalar():
            session.add(Provider(provider_id=pid, provider_code=code, name=name))
            print(f"  - Created provider {code} (id={pid})")

    await session.flush()
    print("[2/7] Providers fixed")
```

**Step 2: Добавить вызов в main()**

```python
async def main() -> None:
    await init_db()
    await fix_create_missing_tables()
    async with session_factory() as session:
        await fix_providers(session)
        await session.commit()
    print("\nDone!")
```

**Step 3: Запустить и проверить**

Run: `uv run python scripts/fix_db_gaps.py`
Verify: `sqlite3 dev.db "SELECT * FROM providers ORDER BY provider_id;"`
Expected:
```text
1|spotify|Spotify
2|soundcloud|SoundCloud
3|beatport|Beatport
4|yandex_music|Yandex Music
```

Verify FK: `sqlite3 dev.db "SELECT provider_id, COUNT(*) FROM provider_track_ids GROUP BY provider_id;"`
Expected: `4|118`

**Step 4: Commit**

```bash
git add scripts/fix_db_gaps.py
git commit -m "fix(db): correct provider IDs — yandex_music 1→4, seed missing providers"
```

---

### Task 3: Заполнить таблицу keys (24 ключа)

**Files:**
- Modify: `scripts/fix_db_gaps.py`

**Step 1: Добавить функцию seed_keys**

```python
async def seed_keys(session: AsyncSession) -> None:
    """Seed 24 musical keys from schema_v6.sql."""
    from app.models.harmony import Key

    existing = (await session.execute(text("SELECT COUNT(*) FROM keys"))).scalar()
    if existing == 24:
        print("[3/7] Keys already seeded (24)")
        return

    # key_code = pitch_class * 2 + mode (0=minor, 1=major)
    KEYS = [
        (0, 0, 0, "Cm", "5A"),   (1, 0, 1, "C", "8B"),
        (2, 1, 0, "C#m", "12A"), (3, 1, 1, "Db", "3B"),
        (4, 2, 0, "Dm", "7A"),   (5, 2, 1, "D", "10B"),
        (6, 3, 0, "Ebm", "2A"),  (7, 3, 1, "Eb", "5B"),
        (8, 4, 0, "Em", "9A"),   (9, 4, 1, "E", "12B"),
        (10, 5, 0, "Fm", "4A"),  (11, 5, 1, "F", "7B"),
        (12, 6, 0, "F#m", "11A"), (13, 6, 1, "F#", "2B"),
        (14, 7, 0, "Gm", "6A"),  (15, 7, 1, "G", "9B"),
        (16, 8, 0, "G#m", "1A"), (17, 8, 1, "Ab", "4B"),
        (18, 9, 0, "Am", "8A"),  (19, 9, 1, "A", "11B"),
        (20, 10, 0, "Bbm", "3A"), (21, 10, 1, "Bb", "6B"),
        (22, 11, 0, "Bm", "10A"), (23, 11, 1, "B", "1B"),
    ]

    for key_code, pitch_class, mode, name, camelot in KEYS:
        exists = (await session.execute(
            text("SELECT 1 FROM keys WHERE key_code = :kc"), {"kc": key_code}
        )).scalar()
        if not exists:
            session.add(Key(
                key_code=key_code, pitch_class=pitch_class,
                mode=mode, name=name, camelot=camelot,
            ))

    await session.flush()
    print("[3/7] Keys seeded (24)")
```

**Step 2: Запустить и проверить**

Run: `uv run python scripts/fix_db_gaps.py`
Verify: `sqlite3 dev.db "SELECT key_code, name, camelot FROM keys ORDER BY key_code;"`
Expected: 24 строки от Cm/5A до B/1B

**Step 3: Commit**

```bash
git add scripts/fix_db_gaps.py
git commit -m "fix(db): seed 24 musical keys from schema_v6.sql"
```

---

### Task 4: Заполнить key_edges (граф совместимости тональностей)

**Files:**
- Modify: `scripts/fix_db_gaps.py`

**Step 1: Добавить функцию seed_key_edges**

Правила совместимости Camelot wheel:
- `same_key`: distance=0, weight=1.0
- `camelot_adjacent`: ±1 по Camelot номеру в том же ряду (A/B), distance=1, weight=0.9
- `relative_major_minor`: одинаковый Camelot номер, A↔B, distance=1, weight=0.85
- `energy_boost`: +2 по Camelot, distance=2, weight=0.7
- `energy_drop`: -2 по Camelot, distance=2, weight=0.7

```python
async def seed_key_edges(session: AsyncSession) -> None:
    """Seed Camelot wheel compatibility edges."""
    existing = (await session.execute(text("SELECT COUNT(*) FROM key_edges"))).scalar()
    if existing and existing > 0:
        print(f"[4/7] Key edges already seeded ({existing})")
        return

    # Build Camelot → key_code lookup
    result = await session.execute(text("SELECT key_code, camelot FROM keys"))
    camelot_to_key = {}
    key_to_camelot = {}
    for row in result:
        camelot_to_key[row.camelot] = row.key_code
        key_to_camelot[row.key_code] = row.camelot

    edges = []
    for kc in range(24):
        cam = key_to_camelot[kc]
        num = int(cam[:-1])
        letter = cam[-1]

        # Same key
        edges.append((kc, kc, 0.0, 1.0, "same_key"))

        # Camelot adjacent (±1 in same row, wrapping 1↔12)
        for delta in [-1, 1]:
            adj_num = ((num - 1 + delta) % 12) + 1
            adj_cam = f"{adj_num}{letter}"
            if adj_cam in camelot_to_key:
                edges.append((kc, camelot_to_key[adj_cam], 1.0, 0.9, "camelot_adjacent"))

        # Relative major/minor (same number, opposite letter)
        opp_letter = "B" if letter == "A" else "A"
        rel_cam = f"{num}{opp_letter}"
        if rel_cam in camelot_to_key:
            edges.append((kc, camelot_to_key[rel_cam], 1.0, 0.85, "relative_major_minor"))

        # Energy boost/drop (±2 in same row)
        for delta, rule in [(2, "energy_boost"), (-2, "energy_drop")]:
            adj_num = ((num - 1 + delta) % 12) + 1
            adj_cam = f"{adj_num}{letter}"
            if adj_cam in camelot_to_key:
                edges.append((kc, camelot_to_key[adj_cam], 2.0, 0.7, rule))

    from app.models.harmony import KeyEdge
    for from_kc, to_kc, dist, weight, rule in edges:
        session.add(KeyEdge(
            from_key_code=from_kc, to_key_code=to_kc,
            distance=dist, weight=weight, rule=rule,
        ))

    await session.flush()
    print(f"[4/7] Key edges seeded ({len(edges)} edges)")
```

**Step 2: Запустить и проверить**

Run: `uv run python scripts/fix_db_gaps.py`
Verify: `sqlite3 dev.db "SELECT COUNT(*) FROM key_edges;"` — ожидаем ~144 рёбер (24 keys × 6 rules)
Verify: `sqlite3 dev.db "SELECT k1.name, k2.name, ke.rule, ke.weight FROM key_edges ke JOIN keys k1 ON ke.from_key_code=k1.key_code JOIN keys k2 ON ke.to_key_code=k2.key_code WHERE k1.name='Am' LIMIT 10;"`

**Step 3: Commit**

```bash
git add scripts/fix_db_gaps.py
git commit -m "fix(db): seed Camelot wheel key_edges compatibility graph"
```

---

### Task 5: Удалить дубли feature runs + заполнить title_sort и label.name_sort

**Files:**
- Modify: `scripts/fix_db_gaps.py`

**Step 1: Добавить функцию deduplicate_feature_runs**

5 треков (1,13,16,19,23) имеют 2-3 идентичных feature runs. Оставляем только последний (наивысший run_id).

```python
async def deduplicate_feature_runs(session: AsyncSession) -> None:
    """Remove duplicate feature runs, keeping the latest run_id per track."""
    # Find tracks with multiple runs
    result = await session.execute(text("""
        SELECT track_id, COUNT(*) as cnt, MAX(run_id) as keep_run
        FROM track_audio_features_computed
        GROUP BY track_id
        HAVING cnt > 1
    """))
    dupes = list(result)

    if not dupes:
        print("[5/7] No duplicate feature runs")
        return

    for row in dupes:
        # Delete older feature rows
        await session.execute(text(
            "DELETE FROM track_audio_features_computed "
            "WHERE track_id = :tid AND run_id != :keep"
        ), {"tid": row.track_id, "keep": row.keep_run})

        # Delete older section rows
        await session.execute(text(
            "DELETE FROM track_sections "
            "WHERE track_id = :tid AND run_id != :keep"
        ), {"tid": row.track_id, "keep": row.keep_run})

        # Delete orphaned feature_extraction_runs
        await session.execute(text(
            "DELETE FROM feature_extraction_runs "
            "WHERE run_id NOT IN (SELECT DISTINCT run_id FROM track_audio_features_computed)"
        ))

    await session.flush()
    print(f"[5/7] Deduplicated {len(dupes)} tracks with duplicate runs")
```

**Step 2: Добавить функцию fill_sort_fields**

```python
import re
import unicodedata

def _sort_key(name: str) -> str:
    """Normalize for sorting: lowercase, strip articles, normalize unicode."""
    s = unicodedata.normalize("NFKD", name).lower().strip()
    s = re.sub(r"^(the|a|an|der|die|das|le|la|les)\s+", "", s)
    return s

async def fill_sort_fields(session: AsyncSession) -> None:
    """Fill title_sort for tracks and name_sort for labels."""
    # Tracks
    result = await session.execute(text(
        "SELECT track_id, title FROM tracks WHERE title_sort IS NULL"
    ))
    tracks = list(result)
    for row in tracks:
        await session.execute(text(
            "UPDATE tracks SET title_sort = :sort WHERE track_id = :tid"
        ), {"sort": _sort_key(row.title), "tid": row.track_id})

    # Labels
    result = await session.execute(text(
        "SELECT label_id, name FROM labels WHERE name_sort IS NULL"
    ))
    labels = list(result)
    for row in labels:
        await session.execute(text(
            "UPDATE labels SET name_sort = :sort WHERE label_id = :lid"
        ), {"sort": _sort_key(row.name), "lid": row.label_id})

    await session.flush()
    print(f"[6/7] Sort fields: {len(tracks)} tracks, {len(labels)} labels")
```

**Step 3: Запустить и проверить**

Run: `uv run python scripts/fix_db_gaps.py`
Verify: `sqlite3 dev.db "SELECT track_id, title, title_sort FROM tracks LIMIT 5;"`
Verify: `sqlite3 dev.db "SELECT COUNT(*) FROM track_audio_features_computed;"` — ожидаем 118 (без дублей)
Verify: `sqlite3 dev.db "SELECT COUNT(*) FROM feature_extraction_runs;"` — меньше 124

**Step 4: Commit**

```bash
git add scripts/fix_db_gaps.py
git commit -m "fix(db): deduplicate feature runs, fill title_sort/name_sort"
```

---

### Task 6: Заполнить yandex_metadata для 118 треков

**Files:**
- Modify: `scripts/fix_db_gaps.py`

**Step 1: Добавить функцию fill_yandex_metadata**

Данные уже есть в таблицах artists, genres, labels, releases, provider_track_ids.
Нужно собрать их в yandex_metadata для каждого трека.

```python
async def fill_yandex_metadata(session: AsyncSession) -> None:
    """Populate yandex_metadata from existing enrichment data."""
    from app.models.metadata_yandex import YandexMetadata

    existing = (await session.execute(text("SELECT COUNT(*) FROM yandex_metadata"))).scalar()
    if existing and existing > 0:
        print(f"[7/7] yandex_metadata already has {existing} rows")
        return

    # Gather data from related tables
    result = await session.execute(text("""
        SELECT
            t.track_id,
            pti.provider_track_id as yandex_track_id,
            r.title as album_title,
            g.name as album_genre,
            l.name as label_name,
            r.release_date,
            t.duration_ms
        FROM tracks t
        JOIN provider_track_ids pti ON t.track_id = pti.track_id AND pti.provider_id = 4
        LEFT JOIN track_releases tr ON t.track_id = tr.track_id
        LEFT JOIN releases r ON tr.release_id = r.release_id
        LEFT JOIN track_genres tg ON t.track_id = tg.track_id
        LEFT JOIN genres g ON tg.genre_id = g.genre_id
        LEFT JOIN labels l ON r.label_id = l.label_id
    """))
    rows = list(result)

    for row in rows:
        release_str = str(row.release_date) if row.release_date else None
        session.add(YandexMetadata(
            track_id=row.track_id,
            yandex_track_id=str(row.yandex_track_id),
            album_title=row.album_title,
            album_genre=row.album_genre,
            label_name=row.label_name,
            release_date=release_str,
            duration_ms=row.duration_ms,
        ))

    await session.flush()
    print(f"[7/7] yandex_metadata populated ({len(rows)} rows)")
```

**Step 2: Запустить и проверить**

Run: `uv run python scripts/fix_db_gaps.py`
Verify: `sqlite3 dev.db "SELECT COUNT(*) FROM yandex_metadata;"` — ожидаем 118
Verify: `sqlite3 dev.db "SELECT ym.track_id, ym.yandex_track_id, ym.album_genre, ym.label_name FROM yandex_metadata ym LIMIT 5;"`

**Step 3: Commit**

```bash
git add scripts/fix_db_gaps.py
git commit -m "fix(db): populate yandex_metadata from existing enrichment data"
```

---

### Task 7: Re-analyze 52 треков с full_analysis=True

52 трека (id 67-118) имеют только базовые features без groove/sections.
Нужно перезапустить full analysis для них через API.

**Files:**
- Create: `scripts/reanalyze_partial.py`

**Step 1: Написать скрипт ре-анализа**

```python
"""Re-analyze tracks that only have partial features (no groove/sections).

Requires the API server running: uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

API = "http://localhost:8000/api/v1"
TRACKS_DIR = Path(__file__).resolve().parent.parent / "icloude" / "dj-library" / "tracks"

async def main() -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
        # Find tracks with partial analysis
        # Use DB query via custom endpoint or direct DB access
        import sqlite3
        db_path = Path(__file__).resolve().parent.parent / "dev.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("""
            SELECT DISTINCT af.track_id, t.title
            FROM track_audio_features_computed af
            JOIN tracks t ON af.track_id = t.track_id
            WHERE af.kick_prominence IS NULL
            ORDER BY af.track_id
        """)
        partial_tracks = list(cursor)
        conn.close()

        total = len(partial_tracks)
        print(f"Found {total} tracks with partial analysis\n")

        ok = failed = 0
        for i, (track_id, title) in enumerate(partial_tracks, 1):
            # Find audio file
            files = list(TRACKS_DIR.glob(f"{track_id:03d}_*"))
            if not files:
                # Try without zero-padding
                files = list(TRACKS_DIR.glob(f"{track_id}_*"))
            if not files:
                print(f"  SKIP [{i:3d}/{total}] No audio: {title}")
                failed += 1
                continue

            audio_path = files[0]
            try:
                # Delete old partial features first
                # The analyze endpoint should handle re-analysis
                resp = await client.post(
                    f"{API}/tracks/{track_id}/analyze",
                    json={"audio_path": str(audio_path), "full_analysis": True},
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    print(f"  OK [{i:3d}/{total}] {title} — BPM={data.get('bpm', '?'):.1f}")
                    ok += 1
                else:
                    print(f"  ERR [{i:3d}/{total}] HTTP {resp.status_code}: {title}")
                    failed += 1
            except Exception as e:
                print(f"  ERR [{i:3d}/{total}] {type(e).__name__}: {title}")
                failed += 1

        print(f"\nDone: {ok} re-analyzed, {failed} failed (of {total})")

if __name__ == "__main__":
    asyncio.run(main())
```

**Важно:** Перед запуском нужно проверить, обрабатывает ли `POST /tracks/{id}/analyze` повторный анализ (upsert) или выдаёт ошибку на дублирование. Если нужно — сначала удалить старые partial-features через SQL.

**Step 2: Подготовить — удалить partial features**

Добавить в `fix_db_gaps.py`:

```python
async def delete_partial_features(session: AsyncSession) -> None:
    """Delete feature runs that have no groove data (partial analysis)."""
    result = await session.execute(text("""
        SELECT af.run_id, af.track_id
        FROM track_audio_features_computed af
        WHERE af.kick_prominence IS NULL
    """))
    partial = list(result)

    if not partial:
        print("[PREP] No partial features to delete")
        return

    run_ids = [r.run_id for r in partial]
    for rid in run_ids:
        await session.execute(text(
            "DELETE FROM track_audio_features_computed WHERE run_id = :rid"
        ), {"rid": rid})
        await session.execute(text(
            "DELETE FROM track_sections WHERE run_id = :rid"
        ), {"rid": rid})
        await session.execute(text(
            "DELETE FROM feature_extraction_runs WHERE run_id = :rid"
        ), {"rid": rid})

    await session.flush()
    print(f"[PREP] Deleted {len(partial)} partial feature runs")
```

**Step 3: Запустить fix_db_gaps.py сначала, потом reanalyze**

1. `uv run python scripts/fix_db_gaps.py` — удалит partial features
2. `uv run uvicorn app.main:app --reload` — запустить API
3. `uv run python scripts/reanalyze_partial.py` — re-analyze 52 треков

**Step 4: Проверить**

```bash
sqlite3 dev.db "SELECT COUNT(*) FROM track_audio_features_computed WHERE kick_prominence IS NOT NULL;"
# Expected: 118

sqlite3 dev.db "SELECT COUNT(DISTINCT track_id) FROM track_sections;"
# Expected: 118
```

**Step 5: Commit**

```bash
git add scripts/reanalyze_partial.py scripts/fix_db_gaps.py
git commit -m "fix(db): re-analyze 52 tracks with full analysis (groove + sections)"
```

---

## Финальная проверка

После всех задач, запустить полную верификацию:

```bash
sqlite3 dev.db "
SELECT
  (SELECT COUNT(*) FROM tracks) as tracks,
  (SELECT COUNT(*) FROM providers) as providers,
  (SELECT COUNT(*) FROM keys) as keys,
  (SELECT COUNT(*) FROM key_edges) as key_edges,
  (SELECT COUNT(*) FROM yandex_metadata) as ym_meta,
  (SELECT COUNT(*) FROM track_audio_features_computed) as features,
  (SELECT COUNT(DISTINCT track_id) FROM track_sections) as tracks_with_sections,
  (SELECT COUNT(*) FROM tracks WHERE title_sort IS NOT NULL) as tracks_with_sort,
  (SELECT COUNT(*) FROM track_audio_features_computed WHERE kick_prominence IS NULL) as partial_features;
"
```

Expected: `118|4|24|~144|118|118|118|118|0`
