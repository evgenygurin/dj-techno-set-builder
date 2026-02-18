# Unified Set Builder — Design Document

**Date**: 2026-02-18
**Status**: Approved
**Branch**: feature/unified-set-builder (from feature/set-generation-bugs)

## Problem

Current architecture has a fundamental flaw: track selection (curation) and track ordering (GA) are two disconnected processes. Curation picks tracks individually by mood/energy slots without checking transition compatibility. GA orders whatever it receives without template awareness. Result: curation can select 20 tracks that don't mix together, and GA happily builds 558-track sets with no template structure.

## Solution

Merge curation into GA fitness function. One algorithm simultaneously selects AND orders tracks. Add iterative feedback loop via Yandex Music likes/dislikes.

## Architecture

### End-to-End Pipeline

```bash
1. SYNC
   YM Playlist ←──bidirectional──→ dj_playlists + dj_playlist_items
        ↓ new tracks
   Download MP3 → iCloud dir
        ↓
   Audio Analysis (BPM, key, LUFS, spectral, mood, sections)
        ↓
   track_audio_features_computed + track_sections

2. BUILD SET
   Input: playlist_id + template_name
        ↓
   Pre-filter: BPM in template range, has features
        ↓
   Classify mood (all pool tracks)
        ↓
   Unified GA: select + order + score
        ↓
   DjSet + DjSetVersion + DjSetItems in DB

3. SYNC TO YM
   Create YM playlist "set_<name>" with set tracks
        ↓
   User listens, likes/dislikes tracks

4. SYNC FROM YM (feedback)
   Read likes/dislikes for tracks IN the set playlist:
     • liked + in playlist → pinned (must stay)
     • disliked → excluded (remove from set)
     • manually removed from playlist → excluded
     • manually added to playlist → pinned

5. REBUILD
   GA re-runs with constraints:
     • pinned tracks must be in chromosome
     • excluded tracks banned from pool
     • free slots → GA selects replacements from pool
        ↓
   New DjSetVersion, sync back to YM

6. EXPORT (when satisfied)
   export_m3u → VLC / Rekordbox
   export_json → DJ cheat sheet
```

### Unified GA Fitness

```text
fitness(chromosome) = (
    w_transition  * mean_transition_quality   # 0.35
  + w_template    * template_slot_fit         # 0.25
  + w_energy_arc  * energy_arc_adherence      # 0.20
  + w_variety     * variety_penalty           # 0.10
  + w_bpm_smooth  * bpm_smoothness            # 0.10
)
```

**template_slot_fit** (new component):
For each track at position i, compare against template.slots[i]:
- mood_match: exact=1.0, adjacent intensity=0.5, other=0.0
- energy_match: 1.0 - |lufs - slot.energy_target| / 8.0
- bpm_match: 1.0 if in range, else penalty by distance

slot_score = 0.5 * mood + 0.3 * energy + 0.2 * bpm
template_slot_fit = mean(slot_scores)

**TrackData.mood** must be populated via mood classifier before GA runs.
**TrackData.artist_id** should be wired from track model for variety penalty.

### GA Constraints for Rebuild

```python
class GAConstraints:
    pinned_track_ids: set[int]    # must be in chromosome
    excluded_track_ids: set[int]  # banned from pool
```

- Population init: every individual includes all pinned tracks
- Mutation _mutate_replace: never replaces pinned, never inserts excluded
- Crossover: preserves pinned tracks in offspring

### Pre-filter (before GA)

Reduce pool from 500+ to ~100-150 tracks:
- BPM within template's overall range (min slot bpm - 5, max slot bpm + 5)
- Has audio features computed
- Not in excluded set
- Status = active (not archived)

### Sync Mechanism

**sync_playlist (YM ↔ DB)**:
- Compare YM playlist tracks vs dj_playlist_items
- New in YM → add to DB, queue download + analysis
- Removed from YM → mark as removed in DB
- New in DB → add to YM playlist (bidirectional)

**sync_set_to_ym**:
- Create/update YM playlist named "set_{set_name}"
- Store ym_playlist_id on dj_sets record
- Set tracks in YM playlist to match current set version order

**sync_set_from_ym**:
- Fetch tracks in YM set playlist
- Fetch user's liked_track_ids and disliked_track_ids
- For each track in set playlist:
  - liked ∩ in_playlist → pinned=true on dj_set_items
  - disliked → mark excluded, remove from set
  - manually removed from playlist → mark excluded
  - manually added to playlist → pinned=true

### Data Model Changes

```sql
-- dj_sets additions
ALTER TABLE dj_sets ADD COLUMN ym_playlist_id INTEGER;
ALTER TABLE dj_sets ADD COLUMN template_name VARCHAR(50);
ALTER TABLE dj_sets ADD COLUMN source_playlist_id INTEGER REFERENCES dj_playlists(playlist_id);

-- dj_set_items additions
ALTER TABLE dj_set_items ADD COLUMN pinned BOOLEAN DEFAULT FALSE;
```

Excluded tracks are simply removed from dj_set_items (no column needed — absence = excluded). History tracked via dj_set_versions.

## MCP Tools

### Changed

| Tool | Change |
|------|--------|
| `build_set` | New signature: playlist_id + template + set_name. Runs pre-filter → mood classify → unified GA. Creates DjSet in DB. |
| `rebuild_set` | **New**. Takes set_id, reads pinned/excluded from latest version, re-runs GA with constraints. Creates new version. |
| `sync_playlist` | **New**. Bidirectional YM ↔ DB sync for source playlist. |
| `sync_set_to_ym` | **New**. Push set to YM as "set_*" playlist. |
| `sync_set_from_ym` | **New**. Read likes/dislikes from YM set playlist, update pinned/excluded. |

### Removed

| Tool | Reason |
|------|--------|
| `curate_set` | Absorbed into build_set GA fitness (template_slot_fit component) |
| `adjust_set` | Replaced by rebuild_set with feedback loop |

### Unchanged

| Tool | Notes |
|------|-------|
| `review_set` | Read-only analysis |
| `score_transitions` | Detailed pair scores |
| `export_set_m3u` | M3U export |
| `export_set_json` | JSON export |
| `analyze_library_gaps` | Library vs template comparison |
| `classify_tracks` | Read-only mood distribution analytics |

## Domain Knowledge (Techno Set Building)

### Key Parameters

```python
# BPM
BPM_TRANSITION_MAX_DELTA = 5.0       # max jump per transition
TECHNO_BPM_OPENER = (120, 125)
TECHNO_BPM_PEAK = (128, 135)

# Energy (LUFS-mapped to 0-1)
ENERGY_TRANSITION_MAX_DELTA = 0.30    # jump >0.30 feels abrupt
ENERGY_OPENER_MAX = 0.60              # opener should not exceed 6/10
ENERGY_MONOTONY_STREAK = 3            # 3+ same energy → penalty

# Harmonic (Camelot)
CAMELOT_SAFE_DISTANCE = 1             # 0=same, 1=adjacent
CAMELOT_ENERGY_BOOST = 2              # ±2 on wheel = energy boost
CAMELOT_DANGER_ZONE = 4               # ≥4 → avoid

# Variety
SAME_MOOD_STREAK_PENALTY = 3          # 3 consecutive → -0.3
SAME_KEY_STREAK_PENALTY = 3           # 3 consecutive → -0.2
SAME_ARTIST_WINDOW = 5                # same artist within 5 tracks → penalty

# Set sizing
POOL_TO_SET_RATIO = 2.5               # pool size / set size
TRACKS_PER_HOUR = (15, 20)            # 15-20 tracks per 60 min

# LUFS (techno)
LUFS_AMBIENT = -14.0
LUFS_PEAK = -6.0
LUFS_TARGET = -8.0
```

### Set Structure Rules

- Max 3 peaks per set, each followed by breakdown
- Opener energy ≤ 0.6 (professional etiquette)
- Energy changes ≤ 0.3 per transition (except intentional breakdowns)
- BPM corridor: start low (120-125), end high (128-135) for classic arc
- Techno: rhythm > melody, so harmonic compatibility less critical than in house
- Long transitions preferred (2-8 min overlap in techno)

## Non-Goals (YAGNI)

- Real-time sync / webhook from YM (manual sync_* calls)
- Automatic MP3 analysis on sync (separate step)
- Multi-set comparison or merging
- Collaborative set building
- Rekordbox/Traktor direct export (M3U covers most)
