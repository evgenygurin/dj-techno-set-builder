# Professional Techno Set Workflow — Design Document

**Date:** 2026-02-17
**Author:** Claude Sonnet 4.5
**Status:** Approved

## Overview

Automated workflow for creating professional-quality techno DJ sets from Yandex Music playlists. Uses existing MCP tools and services with checkpointed execution for reliability and control.

## Requirements

### User Story
> "Create a professional techno set from my Yandex Music playlist 'Techno develop Recs'. Download tracks, analyze for good mixing, generate an optimized set, and export for Rekordbox."

### Key Requirements
1. **Source**: Yandex Music playlist "Techno develop Recs"
2. **Storage**: Create new directory under `sets/<set-name>/` with MP3s + exports
3. **Set Size**: Auto-determine optimal size (15-25 tracks, 90-120 minutes)
4. **Energy Arc**: Classic (warm-up → peak → cool-down)
5. **Analysis**: Adaptive (quick for all, deep for finalists)
6. **Export**: Rekordbox XML + M3U + JSON guide

### Success Criteria
- ✅ Set duration: 90-120 minutes
- ✅ BPM range: 125-135 (techno standard)
- ✅ Harmonic compatibility: Camelot-optimized transitions
- ✅ Energy flow: adheres to classic arc
- ✅ Rekordbox-ready: imports cleanly with all metadata

## Approach Selection

**Chosen Approach:** MCP-based workflow with checkpoints

**Why:**
- Uses existing, battle-tested services (no new code needed for core logic)
- Provides control at each stage via JSON checkpoints
- Easy to debug and retry from any point
- Faster implementation than creating new MCP tool

**Alternatives Rejected:**
- **CLI script (no checkpoints)**: Too fragile, can't recover from mid-workflow failures
- **New MCP tool**: Over-engineering for one-off workflow, takes longer to implement

## Architecture

### High-Level Flow

```text
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator Script                        │
│              (complete_workflow.py)                          │
└────────┬────────────────────────────────────────────┬────────┘
         │                                             │
         │  Calls services sequentially               │  Saves
         │  (YM, Download, Analysis, SetGen, Export)  │  checkpoints
         ↓                                             ↓
┌────────────────────┐                      ┌──────────────────┐
│   Existing         │                      │  Checkpoint      │
│   Services         │                      │  JSON Files      │
├────────────────────┤                      ├──────────────────┤
│ • YMClient         │                      │ • playlist.json  │
│ • DownloadService  │                      │ • stage1.json    │
│ • TrackAnalysis    │                      │ • finalists.json │
│ • SetGeneration    │                      │ • stage2.json    │
│ • SetExport        │                      │ • result.json    │
└────────────────────┘                      └──────────────────┘
         │                                             │
         ↓                                             ↓
┌────────────────────────────────────────────────────────────┐
│                    Storage Layer                            │
├─────────────────────┬──────────────────────────────────────┤
│  Database (SQLite)  │  File System (iCloud)                │
│  • Tracks           │  sets/<set-name>/                    │
│  • AudioFeatures    │  ├─ tracks/*.mp3                     │
│  • DjSets           │  ├─ <set-name>.xml (Rekordbox)       │
│  • DjSetItems       │  ├─ <set-name>.m3u8                  │
│                     │  ├─ <set-name>_guide.json            │
│                     │  └─ checkpoints/*.json               │
└─────────────────────┴──────────────────────────────────────┘
```

### Components

#### 1. Orchestrator Script (`scripts/complete_workflow.py`)
- Python CLI script for sequential execution
- Uses existing services (not MCP tools directly — local execution)
- Saves JSON checkpoints after each stage
- Handles errors and supports resume-from-checkpoint

#### 2. Existing Services (reused, no changes)
- **YandexMusicClient**: fetch playlist, track metadata
- **DownloadService**: download MP3s with retry
- **TrackAnalysisService**: audio feature extraction (BPM, key, energy, spectral, etc.)
- **SetGenerationService**: GA optimization for track ordering
- **set_export module**: Rekordbox XML, M3U, JSON export

#### 3. Checkpoint System
- JSON files after each stage for review and recovery
- Allows restart from last successful stage on failure
- Stored in `sets/<set-name>/checkpoints/`

## Data Flow (8 Stages)

### Stage 1: Fetch Playlist
```text
Input:  playlist_name = "Techno develop Recs"
Tool:   YandexMusicClient.get_playlist()
Output: playlist.json (track_ids, titles, artists)
Save:   sets/<set-name>/checkpoints/playlist.json
```

### Stage 2: Download Tracks
```bash
Input:  track_ids from Stage 1
Tool:   DownloadService.download_tracks_batch()
Config: prefer_bitrate=320, library_path=sets/<set-name>/tracks/
Output: MP3 files in sets/<set-name>/tracks/
Save:   sets/<set-name>/checkpoints/downloads.json (stats)
```

### Stage 3: Import Metadata
```bash
Input:  track_ids
Tool:   TrackService (ensure tracks exist in DB)
Output: Track records in database
Note:   No checkpoint (DB state is persistent)
```

### Stage 4: Quick Analysis (All Tracks)
```bash
Input:  Downloaded MP3 file paths
Tool:   TrackAnalysisService.analyze_track() for each
Extract: BPM, key, energy (LUFS), spectral, beats, groove
Output: AudioFeatures records in DB
Save:   sets/<set-name>/checkpoints/analysis_stage1.json
```

### Stage 5: Filter & Select Finalists
```bash
Input:  analysis_stage1.json
Criteria:
  • BPM: 125-135 (techno range)
  • Key: prefer minor (1A-12A in Camelot)
  • Energy: -14 to -8 LUFS (club-ready)
  • Duration: 5-10 minutes (proper techno)
Selection:
  • Score all pairs for transition compatibility
  • Select top 15-25 tracks targeting 90-120 min total
Save:   sets/<set-name>/checkpoints/finalists.json
Note:   **REVIEW POINT** — user can edit this file before Stage 6
```

### Stage 6: Deep Analysis (Finalists Only)
```bash
Input:  finalists.json (edited or original)
Tool:   TrackAnalysisService with use_ml=True
Extract: Stems (Demucs), kick prominence, harmonic-to-noise ratio (HNR)
Output: Enhanced AudioFeatures in DB
Save:   sets/<set-name>/checkpoints/analysis_stage2.json
```

### Stage 7: Generate Set
```bash
Input:  Finalists with deep analysis features
Tool:   SetGenerationService.generate_set()
Config:
  • energy_arc: "classic"
  • target_duration: 105 minutes (middle of 90-120)
Algorithm:
  • Genetic Algorithm (GA) optimization
  • Fitness = transition_score + energy_arc_adherence
Output:
  • DjSet record in DB
  • DjSetVersion with GA metadata
  • DjSetItems (ordered track list)
Save:   sets/<set-name>/checkpoints/set_result.json
```

### Stage 8: Export
```text
Input:  set_id from Stage 7
Tool:   set_export.export_rekordbox_xml()
        set_export.export_m3u()
        set_export.export_json_guide()
Output:
  • sets/<set-name>/<set-name>.xml (Rekordbox)
  • sets/<set-name>/<set-name>.m3u8 (Extended M3U)
  • sets/<set-name>/<set-name>_guide.json (DJ cheat sheet)
Result: Ready to import into Rekordbox
```

## Error Handling & Recovery

### Retry Strategy
| Stage | Error Type | Strategy |
|-------|------------|----------|
| 1 (YM API) | Network failure | 2 retries, 5s delay |
| 2 (Download) | Track download fail | 3 retries per track, exponential backoff (1s, 2s, 4s) |
| 4, 6 (Analysis) | Audio processing error | Skip track, log error, continue |
| 7 (Set Gen) | Insufficient tracks | Abort with clear message |

### Checkpoint Recovery
```python
# Orchestrator checks for existing checkpoints
if os.path.exists("checkpoints/analysis_stage1.json"):
    print("✓ Found Stage 4 checkpoint, resuming from Stage 5...")
    # Load from checkpoint instead of re-running stages 1-4
```

### Validation Gates
- **Stage 1**: Playlist must exist and contain ≥20 tracks
- **Stage 2**: At least 15 tracks must download successfully
- **Stage 5**: Finalists must total 90-120 minutes
- **Stage 7**: Generated set must meet energy arc criteria

### Error Logging
- All errors logged to `sets/<set-name>/workflow.log`
- Failed track IDs saved in checkpoint files
- Summary report printed at end with success/failure counts

## Configuration

### Hardcoded Constants (Techno-specific)
```python
TECHNO_BPM_RANGE = (125, 135)
TECHNO_KEYS_CAMELOT = ["1A", "2A", "3A", ..., "12A"]  # Minor keys
CLUB_ENERGY_RANGE = (-14, -8)  # LUFS
TRACK_DURATION_RANGE = (300, 600)  # seconds (5-10 minutes)
```

### Tunables (CLI arguments)
```python
--playlist-name "Techno develop Recs"
--set-duration 105  # minutes (default: middle of 90-120)
--finalist-range 15 25  # min-max finalists
--energy-arc classic  # classic | progressive | roller | wave
--bitrate 320  # kbps
--use-deep-analysis  # flag (default: True for adaptive mode)
```

## Testing Strategy

### Unit Tests (existing, reused)
- ✅ `DownloadService` already tested
- ✅ `TrackAnalysisService` already tested
- ✅ `SetGenerationService` already tested
- ✅ `set_export` functions already tested

### Integration Test (new)
```python
# tests/workflows/test_complete_workflow.py
async def test_workflow_with_mock_playlist():
    """End-to-end test with 5 synthetic tracks."""
    # Use synthetic audio fixtures (tests/utils/conftest.py)
    # Mock YM client to return fake playlist
    # Verify all 8 checkpoints created
    # Verify final exports (XML, M3U, JSON) exist and valid
    # Clean up test output directory
```

### Manual Testing Checklist
- [ ] Run workflow with real "Techno develop Recs" playlist
- [ ] Verify `finalists.json` contains expected tracks
- [ ] Import Rekordbox XML into Rekordbox — no errors
- [ ] Load M3U into djay Pro — plays correctly with metadata
- [ ] Review JSON guide — transitions make sense

## File Structure

```text
/Users/laptop/Library/Mobile Documents/com~apple~CloudDocs/dj-techno-set-builder/
└── sets/
    └── techno-professional-2026-02-17/
        ├── tracks/
        │   ├── 12345_fire_eyes.mp3
        │   ├── 12346_acid_rain.mp3
        │   └── ...
        ├── checkpoints/
        │   ├── playlist.json
        │   ├── downloads.json
        │   ├── analysis_stage1.json
        │   ├── finalists.json         ← REVIEW POINT
        │   ├── analysis_stage2.json
        │   └── set_result.json
        ├── techno-professional-2026-02-17.xml      ← Rekordbox
        ├── techno-professional-2026-02-17.m3u8     ← Extended M3U
        ├── techno-professional-2026-02-17_guide.json
        └── workflow.log
```

## Implementation Notes

### Set Name Generation
```python
set_name = f"techno-professional-{datetime.now().strftime('%Y-%m-%d')}"
```

### Yandex Music Playlist Lookup
- User ID: 250905515
- Playlist: "Techno develop Recs"
- Fetch via: `ym_client.get_playlists_list()` → filter by name

### Finalist Selection Algorithm
```python
def select_finalists(tracks, target_duration=105):
    # 1. Filter by techno criteria (BPM, key, energy, duration)
    # 2. Score all pairs for transition compatibility
    # 3. Use greedy algorithm to select tracks maximizing avg transition score
    # 4. Stop when total duration ≥ target_duration
    # 5. Return top 15-25 tracks
```

### Recovery from Checkpoint
```python
def load_checkpoint(stage_name):
    path = f"checkpoints/{stage_name}.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None
```

## Dependencies

**No new dependencies** — all existing services reused.

**Required extras:**
- `audio`: essentia, soundfile, scipy, numpy, librosa (for Stage 4, 6)
- `ml`: demucs, torch (for Stage 6 deep analysis)

Install: `uv sync --extra audio --extra ml`

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| YM API rate limiting | Workflow fails at Stage 1 | Retry with backoff, cache playlist data |
| Download failures (>50%) | Insufficient tracks for set | Retry logic, fail early with clear message |
| Analysis crashes on malformed audio | Incomplete feature data | Skip track, log error, continue with others |
| GA doesn't converge | Poor set quality | Use reasonable defaults, log GA stats |
| User edits `finalists.json` incorrectly | Stage 6 fails | Validate JSON schema before loading |

## Future Enhancements (Out of Scope)

- [ ] Interactive CLI with TUI (textual) for checkpoint review
- [ ] Multi-playlist blending
- [ ] Custom energy arc profiles (user-defined curves)
- [ ] Real-time streaming analysis (avoid full download)
- [ ] MCP tool wrapper (`create_professional_set`) for reusability

## Approval

**Design Status:** ✅ Approved
**Next Step:** Create implementation plan via `writing-plans` skill
