---
description: Expand a playlist with similar tracks and build an optimized DJ set
---

# Expand Playlist

Expand an existing playlist with similar tracks and create a DJ set
with optimized track ordering.

## Parameters

- **playlist_name**: Name of the playlist to expand
- **count**: Number of similar tracks to find (default: 20)
- **style**: Target musical style (default: "dark techno")

## Workflow

1. **Analyze playlist** — Review the playlist's audio profile
   (BPM range, keys, energy levels) via REST API or resources.

2. **Find similar tracks** — `dj_find_similar_tracks` with the playlist ID
   and desired count. The tool uses LLM-assisted search to find matching tracks.

3. **Build DJ set** — `dj_build_set` to create an optimized set using the
   genetic algorithm. Use the default `classic` energy arc.

4. **Verify quality** — `dj_score_transitions` to check transition scores.
   Look for average score > 0.7.

5. **Improve if needed** — If average transition score < 0.7,
   use `dj_rebuild_set` to regenerate with weak tracks excluded
   and good tracks pinned.

## Tips

- Start with `count=10` for quick results, increase for more variety
- Compatible Camelot keys improve harmonic transitions
- Energy flow matters — avoid sudden jumps > 3 LUFS between tracks
