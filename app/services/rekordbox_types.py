"""Data classes for Rekordbox XML export.

Typed, frozen structures that represent Rekordbox XML elements.
Used as input to the pure ``export_rekordbox_xml()`` generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RekordboxCuePoint:
    """A POSITION_MARK element in Rekordbox XML.

    Represents cue points (Type=0), fade-in/out (Type=1/2),
    load points (Type=3), and loops (Type=4).
    """

    position_s: float
    """Position in seconds (Start attribute)."""

    cue_type: int
    """0=cue, 1=fadein, 2=fadeout, 3=load, 4=loop."""

    hotcue_num: int
    """Slot number: -1=memory, 0-7=hot cue A-H."""

    name: str = ""
    end_s: float | None = None
    """End position (only for loops and fade points)."""

    red: int = 0
    green: int = 0
    blue: int = 0


@dataclass(frozen=True)
class RekordboxTempo:
    """A TEMPO element in Rekordbox XML (beatgrid segment)."""

    position_s: float
    """Inizio — position in seconds."""

    bpm: float
    metro: str = "4/4"
    beat: int = 1
    """Battito — beat number within the bar (1-based)."""


@dataclass(frozen=True)
class RekordboxTrackData:
    """All data for a single TRACK element in Rekordbox XML."""

    track_id: int
    name: str
    artist: str
    duration_s: int
    location: str
    """File URI: ``file://localhost/path/to/file.mp3``."""

    bpm: float | None = None
    tonality: str | None = None
    """Musical key string: ``"Am"``, ``"Cm"``."""

    album: str = ""
    genre: str = ""
    label: str = ""
    year: int = 0
    date_added: str = ""
    """Format: ``yyyy-mm-dd``."""

    comments: str = ""
    colour: str = ""
    """Hex RGB: ``"0xFF0000"``."""

    kind: str = "MP3 File"
    size: int = 0
    bitrate: int = 320
    sample_rate: int = 44100

    tempos: list[RekordboxTempo] = field(default_factory=list)
    position_marks: list[RekordboxCuePoint] = field(default_factory=list)
