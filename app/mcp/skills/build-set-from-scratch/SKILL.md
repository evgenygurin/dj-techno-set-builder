---
description: Build a complete DJ set from scratch given a genre and duration
---

# Build Set From Scratch

Create a full DJ set starting from zero — search for tracks, import them,
and optimize the ordering.

## Parameters

- **genre**: Target genre (e.g., "dark techno", "melodic techno", "acid")
- **duration_minutes**: Target set duration (default: 60)
- **energy_arc**: Energy shape — classic, progressive, roller, or wave

## Workflow

1. **Search tracks** — `ym_search_yandex_music` with the target genre.
   Search for enough tracks to fill the duration
   (estimate ~5 min per track, so 12 tracks for 60 min).

2. **Import tracks** — `dj_import_tracks` with the found track IDs.
   This adds them to the local database.

3. **Expand selection** — `dj_find_similar_tracks` to discover additional
   tracks that complement the initial selection.

4. **Build set** — `dj_build_set` with the desired `energy_arc`.
   The genetic algorithm optimizes track ordering for smooth transitions.

5. **Score and iterate** — `dj_score_transitions` → review →
   `dj_adjust_set` if scores are low.

## Energy Arcs

- **classic**: Warm up → peak → cool down
- **progressive**: Steady build from start to finish
- **roller**: Maintain high energy throughout
- **wave**: Multiple peaks and valleys
