---
description: "Расширить плейлист: discover → import → download → analyze → distribute"
allowed-tools: ["Bash", "Read", "mcp__dj-techno__dj_get_playlist", "mcp__sqlite-db__read_query"]
---

# Fill Playlist Pipeline

Run the full fill_and_verify.py pipeline to expand a YM playlist with similar techno tracks.

## Usage

```bash
# Default: expand kind=1280 with target=50 new tracks
uv run python scripts/fill_and_verify.py --kind 1280 --target 50 --workers 4 --batch 5

# With arguments from user: /fill-playlist 1280 100
uv run python scripts/fill_and_verify.py --kind $ARGUMENTS --workers 4 --batch 5
```

## What it does

1. Picks seed tracks from the playlist (weighted by age)
2. Discovers similar tracks via YM API
3. Filters by techno metadata (genre, duration, no remixes)
4. Imports to local DB
5. Downloads MP3 from YM
6. Runs full audio analysis (BPM, LUFS, energy, spectral, kick, onset)
7. Applies feedback gate (disliked → block, liked → bypass audio gate)
8. Routes passing tracks to 15 subgenre playlists
9. Adds to source playlist

## After completion

Check results:
```bash
# Playlist stats
make mcp-call TOOL=dj_audit_playlist ARGS='{"playlist_id": 24}'

# Subgenre distribution
make mcp-call TOOL=dj_distribute_to_subgenres ARGS='{"playlist_id": 24}'
```
