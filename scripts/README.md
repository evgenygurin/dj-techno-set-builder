# Complete Techno Set Workflow

Automated workflow for creating professional techno DJ sets from Yandex Music playlists.

## Overview

8-stage pipeline with checkpoint recovery:

1. **Fetch Playlist** — Get tracks from Yandex Music
2. **Import Metadata** — Store track info in database
3. **Download Tracks** — Download MP3 files
4. **Quick Analysis** — Analyze BPM, key, energy (no ML)
5. **Select Finalists** — Filter to 15-25 best tracks
6. **Deep Analysis** — ML analysis with Demucs stem separation
7. **Generate Set** — Create DJ set with optimal track order
8. **Export** — Export to M3U/JSON formats

## Usage

### Basic Usage

```bash
# Run complete workflow (default playlist: "Techno develop")
uv run python scripts/complete_workflow.py
```

### Custom Options

```bash
# Custom playlist
uv run python scripts/complete_workflow.py --playlist "My Techno Playlist"

# Custom output directory
uv run python scripts/complete_workflow.py \
  --playlist "My Playlist" \
  --base-dir /path/to/output
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--playlist` | "Techno develop" | Yandex Music playlist name |
| `--base-dir` | iCloud directory | Base directory for output |

## Checkpoints

Each stage saves a checkpoint JSON file. If the workflow is interrupted, re-running will skip completed stages.

**Checkpoint files:**
- `sets/techno-professional-YYYY-MM-DD/checkpoints/playlist.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/metadata.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/downloads.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/quick_analysis.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/finalists.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/deep_analysis.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/generated_set.json`
- `sets/techno-professional-YYYY-MM-DD/checkpoints/exports.json`

## Output

Generated files:

```text
sets/techno-professional-YYYY-MM-DD/
├── tracks/                 # Downloaded MP3 files
│   ├── 12345_artist_title.mp3
│   └── ...
├── checkpoints/            # Recovery checkpoints
│   ├── playlist.json
│   └── ...
├── workflow.log            # Execution log
├── techno-professional-YYYY-MM-DD.m3u    # M3U playlist
└── techno-professional-YYYY-MM-DD.json   # Track metadata
```

## Requirements

### Environment

- Python 3.12+
- Yandex Music token in `.env` file
- Database migrations applied

### Database Tables

Required tables:
- `tracks` — Track metadata
- `provider_track_ids` — Provider links
- `dj_library_items` — Downloaded files
- `track_audio_features_computed` — Audio features
- `feature_extraction_runs` — Analysis runs
- `dj_sets`, `dj_set_versions`, `dj_set_items` — Sets

## Workflow Details

### Stage 1: Fetch Playlist

- Connects to Yandex Music API
- Fetches user playlists
- Finds target playlist by name
- Extracts track IDs

**Output:** List of track IDs

### Stage 2: Import Metadata

- Fetches track metadata from YM API
- Creates `Track` records
- Links to provider via `ProviderTrackId`

**Output:** Import statistics (imported, skipped, failed)

### Stage 3: Download Tracks

- Downloads MP3 files from Yandex Music
- Saves to `tracks/` directory
- Stores in `dj_library_items` table
- Calculates SHA256 hash

**Output:** Download statistics + total MB

### Stage 4: Quick Analysis

- Analyzes BPM, key, energy, spectral features
- Uses `TrackAnalysisService` (no ML)
- Stores in `track_audio_features_computed`

**Output:** Analysis statistics

### Stage 5: Select Finalists

- Filters tracks with valid features
- Simplified: selects first 20 tracks
- TODO: Add techno criteria (BPM 125-135, energy >0.6)

**Output:** List of finalist track IDs (15-25)

### Stage 6: Deep Analysis

- ML analysis with Demucs stem separation
- Beat detection and structure segmentation
- Only for finalist tracks (optimized)

**Output:** Deep analysis statistics

### Stage 7: Generate Set

- Creates `DjSet` with target duration (1 hour)
- Creates `DjSetVersion` (v1)
- Adds tracks as `DjSetItems` with sort order
- TODO: Genetic algorithm for optimal ordering

**Output:** Set version ID

### Stage 8: Export

- Exports to M3U (file paths)
- Exports to JSON (metadata + paths)
- TODO: Rekordbox XML export

**Output:** Export paths

## Error Handling

Workflow logs to `workflow.log` in the set directory.

On failure:
- Exception is logged with stack trace
- Workflow exits with error
- Checkpoints preserve completed stages
- Re-run to continue from last checkpoint

## Testing

Run integration tests:

```bash
# All workflow tests
uv run pytest tests/scripts/ -v

# Specific test
uv run pytest tests/scripts/test_complete_workflow.py::test_stage_1_fetch_playlist -v
```

## TODOs

### Stage 5: Select Finalists
- [ ] Implement proper techno criteria filtering
- [ ] BPM range: 125-135
- [ ] Energy threshold: >0.6
- [ ] Key compatibility scoring

### Stage 7: Generate Set
- [ ] Implement genetic algorithm for track ordering
- [ ] Optimize for energy arc
- [ ] Optimize for harmonic mixing
- [ ] Constraint satisfaction (duration, BPM range)

### Stage 8: Export
- [ ] Rekordbox XML export
- [ ] Traktor NML export
- [ ] Serato crate export

## Architecture

```text
WorkflowOrchestrator
  ├── CheckpointManager (JSON recovery)
  ├── Stage 1: YandexMusicClient
  ├── Stage 2: TrackRepository + ProviderTrackId
  ├── Stage 3: DownloadService
  ├── Stage 4: TrackAnalysisService (quick)
  ├── Stage 5: AudioFeaturesRepository
  ├── Stage 6: TrackAnalysisService (full ML)
  ├── Stage 7: DjSetRepository + DjSetVersionRepository
  └── Stage 8: Export (M3U/JSON)
```

## Examples

### Resume After Failure

If workflow fails at Stage 5:

```bash
# Fix issue (e.g., add missing dependency)
# Re-run — will skip Stages 1-4 (checkpoints exist)
uv run python scripts/complete_workflow.py
```

### Clean Start

```bash
# Remove checkpoints to start fresh
rm -rf "sets/techno-professional-YYYY-MM-DD/checkpoints"
uv run python scripts/complete_workflow.py
```

### Inspect Checkpoints

```bash
# View checkpoint data
cat sets/techno-professional-YYYY-MM-DD/checkpoints/finalists.json | jq
```

## Performance

Approximate timings (214 tracks):

| Stage | Time | Notes |
|-------|------|-------|
| 1. Fetch Playlist | 1-2s | API call |
| 2. Import Metadata | 10-15s | Batch API + DB writes |
| 3. Download Tracks | 5-10 min | Network-bound |
| 4. Quick Analysis | 10-15 min | CPU-bound |
| 5. Select Finalists | <1s | DB query |
| 6. Deep Analysis | 30-60 min | ML-bound (20 tracks) |
| 7. Generate Set | <1s | DB writes |
| 8. Export | <1s | File writes |

**Total:** ~45-85 minutes for 214 tracks

Checkpoint system allows resuming if interrupted.
