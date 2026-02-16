# Rekordbox XML Export Design

**Date:** 2026-02-16
**Status:** Draft
**Scope:** Add Rekordbox XML (`DJ_PLAYLISTS`) export for DJ sets with full metadata

## Problem

Current export (`export_set_m3u`) generates Extended M3U with custom `#EXTDJ-*` tags. While backward-compatible, no DJ software reads these tags — M3U carries only track order. DJ software (Rekordbox, djay Pro, Traktor, Mixxx) stores cue points, loops, beatgrid, and mix points in proprietary formats.

Rekordbox XML (`DJ_PLAYLISTS`) is the de-facto interchange format. It's imported by:
- **Rekordbox** — native
- **djay Pro** — via library import
- **Mixxx** — built-in Rekordbox XML parser
- **Traktor** — via converters (DJCU, Rekord Buddy, dj-data-converter)
- **DJ.Studio** — native import

## Decision

Add `export_rekordbox_xml()` pure function in `app/services/set_export.py` + MCP tool `export_set_rekordbox` in `app/mcp/workflows/export_tools.py`.

Uses `xml.etree.ElementTree` (stdlib) — no new dependencies.

## XML Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="DJ Techno Set Builder" Version="0.1.0" Company=""/>
  <COLLECTION Entries="{N}">
    <TRACK TrackID="..." ... >
      <TEMPO .../>
      <POSITION_MARK .../>
    </TRACK>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="1">
      <NODE Name="{set_name}" Type="1" KeyType="0" Entries="{N}">
        <TRACK Key="{TrackID}"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
```

## Data Mapping

### TRACK Attributes

| Rekordbox Attribute | Source | DB Table | Notes |
|---|---|---|---|
| `TrackID` | `track_id` | `tracks` | |
| `Name` | `title` | `tracks` | |
| `Artist` | joined artist names | `track_artists` → `artists` | Comma-separated |
| `Composer` | — | — | Empty string |
| `Album` | album title | `track_albums` → `albums` | First album |
| `Grouping` | — | — | Empty string |
| `Genre` | genre name | `track_genres` → `genres` | First genre |
| `Kind` | `"MP3 File"` | — | Default; could infer from extension |
| `Size` | `0` | — | No file access |
| `TotalTime` | `duration_ms // 1000` | `tracks` | Seconds (integer) |
| `DiscNumber` | `0` | — | |
| `TrackNumber` | `0` | — | |
| `Year` | album year | `albums` | |
| `AverageBpm` | `bpm` | `track_audio_features_computed` | Format `"136.00"` |
| `DateModified` | — | — | Empty |
| `DateAdded` | `created_at` | `tracks` | Format `yyyy-mm-dd` |
| `BitRate` | `320` | — | Default MP3 |
| `SampleRate` | `44100` | — | Default |
| `Comments` | DJ notes | `dj_set_items.notes` | From set context |
| `PlayCount` | `0` | — | |
| `LastPlayed` | — | — | Empty |
| `Rating` | `0` | — | 0=no rating, 51/102/153/204/255 = 1-5 stars |
| `Location` | generated path | — | `file://localhost/{base_path}/{NNN}.%20{title}.mp3` |
| `Remixer` | — | — | Empty string |
| `Tonality` | key name | `track_audio_features_computed` → `keys` | Musical key: `"Am"`, `"Cm"` |
| `Label` | label name | `track_labels` → `labels` | First label |
| `Mix` | — | — | Empty string |
| `Colour` | — | — | Optional: energy-based color mapping |

### Location Format

```text
file://localhost/Users/dj/Music/001.%20Artist%20-%20Title.mp3
```

- URL-encoded path (spaces = `%20`)
- POSIX separators only
- `file://localhost/` prefix required
- Base path configurable via tool parameter

### TEMPO (Beatgrid)

| Attribute | Source | DB Table |
|---|---|---|
| `Inizio` | `first_downbeat_ms / 1000` | `dj_beatgrid` |
| `Bpm` | `bpm` | `dj_beatgrid` |
| `Metro` | `"4/4"` | — | Default for techno |
| `Battito` | `1` | — | First beat |

For variable tempo tracks: multiple `TEMPO` elements from `dj_beatgrid_change_points`.

### POSITION_MARK (Cues, Loops, Mix Points)

| Scenario | Type | Num | Source Table | Mapping |
|---|---|---|---|---|
| Hot Cue A-H | `0` | `0-7` | `dj_cue_points` | `cue_kind=CUE`, `hotcue_index >= 0` |
| Memory Cue | `0` | `-1` | `dj_cue_points` | `cue_kind=CUE`, `hotcue_index < 0 or NULL` |
| Fade-In (Mix In) | `1` | `-1` | `dj_cue_points` | `cue_kind=FADE_IN`; fallback: `dj_set_items.mix_in_ms` |
| Fade-Out (Mix Out) | `2` | `-1` | `dj_cue_points` | `cue_kind=FADE_OUT`; fallback: `dj_set_items.mix_out_ms` |
| Load Point | `3` | `-1` | `dj_cue_points` | `cue_kind=LOAD` |
| Hot Loop | `4` | `0-7` | `dj_saved_loops` | `hotcue_index >= 0` |
| Memory Loop | `4` | `-1` | `dj_saved_loops` | `hotcue_index < 0 or NULL` |
| Section → Memory Cue | `0` | `-1` | `track_sections` | Auto: intro/drop/outro boundaries |

#### Color mapping (cue_points / loops → RGB)

`color_rgb` (24-bit int) → `Red`, `Green`, `Blue` (0-255 each):

```python
red = (color_rgb >> 16) & 0xFF
green = (color_rgb >> 8) & 0xFF
blue = color_rgb & 0xFF
```

#### Mix In/Out from set items (fallback)

When `dj_cue_points` has no FADE_IN/FADE_OUT for a track, generate from `dj_set_items`:
- Fade-In: `Start = mix_in_ms / 1000`, `End = mix_in_ms / 1000 + 16` (16s default zone)
- Fade-Out: `Start = mix_out_ms / 1000`, `End = duration_s` (to end of track)

#### Section-to-Cue conversion

Auto-detected sections (`track_sections`) → memory cues at section boundaries:

| Section Type | Cue Name |
|---|---|
| INTRO (0) | `"Intro"` |
| BUILDUP (1) | `"Build"` |
| DROP (2) | `"Drop"` |
| BREAKDOWN (3) | `"Break"` |
| OUTRO (4) | `"Outro"` |

Only first boundary of each section type becomes a cue (avoid clutter).

## Architecture

```text
export_tools.py (MCP)
    ├── Collects: tracks, artists, albums, genres, labels
    ├── Collects: audio features (BPM, key, energy)
    ├── Collects: cue points, saved loops, beatgrid
    ├── Collects: sections (for auto-cues)
    ├── Collects: set items (mix in/out, EQ, notes)
    ↓
set_export.py (pure function)
    export_rekordbox_xml(
        tracks: list[RekordboxTrackData],
        set_name: str,
        base_path: str = "/Music",
    ) → str (XML)
    ↓
xml.etree.ElementTree (stdlib)
```

### Input Data Structure

```python
@dataclass(frozen=True)
class RekordboxCuePoint:
    position_s: float        # Position in seconds
    cue_type: int            # 0=cue, 1=fadein, 2=fadeout, 3=load, 4=loop
    hotcue_num: int          # -1=memory, 0-7=hot cue slot
    name: str = ""
    end_s: float | None = None  # Only for loops and fade points
    red: int = 0
    green: int = 0
    blue: int = 0

@dataclass(frozen=True)
class RekordboxTempo:
    position_s: float        # Inizio
    bpm: float
    metro: str = "4/4"
    beat: int = 1            # Battito

@dataclass(frozen=True)
class RekordboxTrackData:
    track_id: int
    name: str
    artist: str
    duration_s: int
    location: str
    bpm: float | None = None
    tonality: str | None = None  # Musical key string: "Am", "Cm"
    album: str = ""
    genre: str = ""
    label: str = ""
    year: int = 0
    date_added: str = ""     # yyyy-mm-dd
    comments: str = ""
    colour: str = ""         # "0xRRGGBB"
    tempos: list[RekordboxTempo] = field(default_factory=list)
    position_marks: list[RekordboxCuePoint] = field(default_factory=list)
```

## New Batch Service Methods

Currently missing — needed to avoid N+1 queries:

| Method | Repository | Returns |
|---|---|---|
| `get_cues_by_track_ids(ids)` | `DjCuePointRepository` | `dict[int, list[DjCuePoint]]` |
| `get_loops_by_track_ids(ids)` | `DjSavedLoopRepository` | `dict[int, list[DjSavedLoop]]` |
| `get_canonical_beatgrids(ids)` | `DjBeatgridRepository` | `dict[int, DjBeatgrid]` |
| `get_latest_sections(ids)` | `TrackSectionRepository` | `dict[int, list[TrackSection]]` |
| `get_track_albums(ids)` | `TrackService` | `dict[int, list[str]]` |
| `get_track_genres(ids)` | `TrackService` | `dict[int, list[str]]` |
| `get_track_labels(ids)` | `TrackService` | `dict[int, list[str]]` |

`get_track_artists(ids)` already exists in `TrackService`.

## MCP Tool Signature

```python
@mcp.tool(
    annotations={"readOnlyHint": True},
    tags={"export"},
)
async def export_set_rekordbox(
    set_id: int,
    version_id: int,
    ctx: Context,
    include_cues: bool = True,
    include_loops: bool = True,
    include_beatgrid: bool = True,
    include_mix_points: bool = True,
    include_sections_as_cues: bool = True,
    include_load_point: bool = True,
    base_path: str = "/Music",
    set_svc: DjSetService = Depends(get_set_service),
    track_svc: TrackService = Depends(get_track_service),
    features_svc: AudioFeaturesService = Depends(get_features_service),
) -> ExportResult:
    """Export a set version as Rekordbox XML (DJ_PLAYLISTS).

    Produces a complete XML file compatible with Rekordbox, djay Pro,
    Mixxx, and Traktor (via converter).  Includes:
    - Full COLLECTION with track metadata (BPM, key, artist, album, genre, label)
    - TEMPO elements (beatgrid from dj_beatgrid, variable tempo support)
    - POSITION_MARK: hot cues, memory cues, loops, fade-in/out (mix points), load point
    - Auto-generated memory cues from track section boundaries (intro/drop/outro)
    - PLAYLISTS tree with set name

    Args:
        set_id: DJ set ID (for validation).
        version_id: Set version to export.
        include_cues: Include hot + memory cue points.
        include_loops: Include saved loops (hot + memory).
        include_beatgrid: Include TEMPO elements from beatgrid.
        include_mix_points: Include Fade-In/Fade-Out (mix in/out) markers.
        include_sections_as_cues: Convert auto-detected sections to memory cues.
        include_load_point: Include Load Point marker.
        base_path: Base path prefix for file URIs (default "/Music").
    """
```

## Limitations

- **Active Loop**: Not supported in Rekordbox XML format (only in ANLZ binary files)
- **Waveform data**: Not exportable to XML
- **Song structure / phrases**: Rekordbox XML does not include phrase analysis
- **File paths**: Generated paths (no actual audio files) — user maps to real files
- **Track color**: Could auto-assign by energy level, but defaults to empty

## Testing Strategy

- **Unit tests** for `export_rekordbox_xml()` with known input → validate XML structure
- **Validate against Rekordbox**: parse output with `pyrekordbox.RekordboxXml`
- **Import test**: manual import into Rekordbox / djay Pro to verify cues/loops/grid

## References

- [Official Rekordbox XML spec (PDF)](https://cdn.rekordbox.com/files/20200410160904/xml_format_list.pdf)
- [pyrekordbox XML format docs](https://pyrekordbox.readthedocs.io/en/latest/formats/xml.html)
- [Mixxx wiki: Rekordbox Cue Storage Format](https://github.com/mixxxdj/mixxx/wiki/Rekordbox-Cue-Storage-Format)
- [DJ Link Analysis: ANLZ format](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html)
