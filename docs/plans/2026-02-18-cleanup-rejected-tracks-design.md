# Cleanup Rejected Tracks — Design

**Date:** 2026-02-18
**Status:** Approved

## Context

After analyzing 1000 tracks from the "Techno Develop Recs" YM playlist (kind=1271, userId=250905515), 441 tracks were rejected across multiple tiers:

| Tier | Count | Reason |
|------|-------|--------|
| 0 (metadata) | 432 | Wrong genre or duration |
| 1 (BPM) | 5 | BPM outside 120-150 |
| 2 (LUFS) | 4 | LUFS outside -14 to -3 |
| 3 (error) | 1 | Worker crash |
| **Total** | **441** | |

559 tracks are kept with full audio features in the local DB.

## Goal

Full cleanup of 441 rejected tracks from 3 locations:
1. YM playlist (via API)
2. Local DB (`dj_playlist_items`)
3. MP3 files on disk (iCloud)

## Solution: `scripts/cleanup_rejected.py`

### Input

Rejection report JSON: `techno-develop-recs/rejection_report_20260218_172228.json`
Contains `ym_ids_to_delete` array (441 YM track IDs).

### Phase 1 — YM Playlist

- Read current playlist state via `ym_get_playlist_by_id(userId=250905515, kind=1271)`
- Build mapping: `ym_track_id → (index, albumId)` from playlist tracks
- Delete tracks **from highest index to lowest** (avoids index shift)
- Each delete: `ym_change_playlist_tracks` with diff `{"op":"delete","from":idx,"to":idx+1,"tracks":[{"id":"...","albumId":"..."}]}`
- After each successful call, increment revision
- Log progress every 50 tracks
- Idempotent: skip tracks not found in current playlist

### Phase 2 — Local DB

- Delete from `dj_playlist_items` WHERE `playlist_id=2` AND `track_id` IN (local track IDs of rejected tracks)
- Single SQL DELETE statement via async session
- Log count of deleted rows

### Phase 3 — MP3 Files

- For each rejected track, find `{track_id}_*.mp3` in audio dir
- Delete file if exists, skip if missing
- Log count of deleted files

### Error Handling

- Phase 1 failure → stop (YM is the master, don't desync)
- Phase 2 failure → log, continue to Phase 3
- Phase 3 failure per file → log, continue

### CLI Interface

- `--confirm` flag required for actual deletion (dry-run by default)
- `--report PATH` to specify rejection report (default: latest in output dir)
- Logs to `logs/cleanup_YYYYMMDD_HHMMSS.log`

### YM API Details

- Playlist: userId=250905515, kind=1271
- Current revision: 3 (check at runtime)
- Track structure: `{id, track: {albums: [{id}]}}`
- Diff format: `{"diff":{"op":"delete","from":N,"to":N+1,"tracks":[{"id":"X","albumId":"Y"}]}}`
