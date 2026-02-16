# Rekordbox XML Export — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Export DJ sets as Rekordbox XML (`DJ_PLAYLISTS`) with full metadata (cues, loops, beatgrid, mix points, sections).

**Architecture:** Pure function `export_rekordbox_xml()` in `app/services/set_export.py` generates XML from typed dataclasses. MCP tool `export_set_rekordbox` in `app/mcp/workflows/export_tools.py` collects data from services/repos and calls the pure function. New batch repo methods avoid N+1 queries.

**Tech Stack:** `xml.etree.ElementTree` (stdlib), `urllib.parse.quote` (stdlib). No new deps.

**Design doc:** `docs/plans/2026-02-16-rekordbox-xml-export-design.md`

---

## Task 1: Rekordbox Data Classes

Add frozen dataclasses for structured input to the XML generator.

**Files:**
- Create: `app/services/rekordbox_types.py`
- Test: `tests/services/test_rekordbox_types.py`

**Step 1: Write the failing test**

```python
# tests/services/test_rekordbox_types.py
"""Tests for Rekordbox XML data classes."""

from app.services.rekordbox_types import (
    RekordboxCuePoint,
    RekordboxTempo,
    RekordboxTrackData,
)

class TestRekordboxCuePoint:
    def test_defaults(self):
        cue = RekordboxCuePoint(position_s=32.0, cue_type=0, hotcue_num=-1)
        assert cue.name == ""
        assert cue.end_s is None
        assert cue.red == 0
        assert cue.green == 0
        assert cue.blue == 0

    def test_hot_cue_with_color(self):
        cue = RekordboxCuePoint(
            position_s=64.0, cue_type=0, hotcue_num=0,
            name="Drop", red=255, green=0, blue=0,
        )
        assert cue.hotcue_num == 0
        assert cue.red == 255

    def test_loop_has_end(self):
        cue = RekordboxCuePoint(
            position_s=96.0, cue_type=4, hotcue_num=-1,
            end_s=104.0, name="Loop A",
        )
        assert cue.end_s == 104.0

    def test_frozen(self):
        cue = RekordboxCuePoint(position_s=0.0, cue_type=0, hotcue_num=-1)
        import pytest
        with pytest.raises(AttributeError):
            cue.position_s = 1.0  # type: ignore[misc]

class TestRekordboxTempo:
    def test_defaults(self):
        t = RekordboxTempo(position_s=0.098, bpm=136.0)
        assert t.metro == "4/4"
        assert t.beat == 1

class TestRekordboxTrackData:
    def test_minimal(self):
        td = RekordboxTrackData(
            track_id=1, name="Exhale", artist="Amelie Lens",
            duration_s=420, location="file://localhost/Music/001.%20Exhale.mp3",
        )
        assert td.bpm is None
        assert td.tempos == []
        assert td.position_marks == []

    def test_with_all_fields(self):
        td = RekordboxTrackData(
            track_id=1, name="Exhale", artist="Amelie Lens",
            duration_s=420, location="file://localhost/Music/001.%20Exhale.mp3",
            bpm=136.0, tonality="Am", album="Album", genre="Techno",
            label="Lenske", year=2025, date_added="2025-12-01",
            comments="Peak time", colour="0xFF0000",
            tempos=[RekordboxTempo(position_s=0.098, bpm=136.0)],
            position_marks=[
                RekordboxCuePoint(position_s=0.0, cue_type=0, hotcue_num=0, name="Intro"),
            ],
        )
        assert td.bpm == 136.0
        assert len(td.tempos) == 1
        assert len(td.position_marks) == 1
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/test_rekordbox_types.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.rekordbox_types'`

**Step 3: Write the implementation**

```python
# app/services/rekordbox_types.py
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
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/test_rekordbox_types.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/services/rekordbox_types.py tests/services/test_rekordbox_types.py
git commit -m "feat: add Rekordbox XML data classes"
```

---

## Task 2: Pure XML Generator Function

The core: `export_rekordbox_xml()` that takes typed data and returns XML string.

**Files:**
- Modify: `app/services/set_export.py` (add function at the bottom)
- Test: `tests/services/test_set_export.py` (add new test classes)

**Step 1: Write the failing tests**

Add to `tests/services/test_set_export.py`:

```python
# At the top, add imports:
import xml.etree.ElementTree as ET

from app.services.rekordbox_types import (
    RekordboxCuePoint,
    RekordboxTempo,
    RekordboxTrackData,
)
from app.services.set_export import export_rekordbox_xml

def _parse_xml(xml_str: str) -> ET.Element:
    """Parse XML string and return root element."""
    return ET.fromstring(xml_str)

def _make_rb_track(**overrides: object) -> RekordboxTrackData:
    """Create a minimal RekordboxTrackData with optional overrides."""
    defaults = {
        "track_id": 1,
        "name": "Test Track",
        "artist": "Test Artist",
        "duration_s": 300,
        "location": "file://localhost/Music/001.%20Test.mp3",
    }
    defaults.update(overrides)
    return RekordboxTrackData(**defaults)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Rekordbox XML: structure
# ---------------------------------------------------------------------------

class TestRekordboxXMLStructure:
    """Top-level XML structure tests."""

    def test_empty_collection(self):
        xml = export_rekordbox_xml([], set_name="Empty Set")
        root = _parse_xml(xml)
        assert root.tag == "DJ_PLAYLISTS"
        assert root.attrib["Version"] == "1.0.0"

    def test_product_element(self):
        xml = export_rekordbox_xml([], set_name="Test")
        root = _parse_xml(xml)
        product = root.find("PRODUCT")
        assert product is not None
        assert product.attrib["Name"] == "DJ Techno Set Builder"

    def test_collection_entries_count(self):
        tracks = [_make_rb_track(track_id=i) for i in range(3)]
        xml = export_rekordbox_xml(tracks, set_name="Test")
        root = _parse_xml(xml)
        coll = root.find("COLLECTION")
        assert coll is not None
        assert coll.attrib["Entries"] == "3"

    def test_playlist_node(self):
        tracks = [_make_rb_track(track_id=1)]
        xml = export_rekordbox_xml(tracks, set_name="Friday Night")
        root = _parse_xml(xml)
        playlists = root.find("PLAYLISTS")
        assert playlists is not None
        root_node = playlists.find("NODE")
        assert root_node is not None
        assert root_node.attrib["Type"] == "0"
        assert root_node.attrib["Name"] == "ROOT"
        inner = root_node.find("NODE")
        assert inner is not None
        assert inner.attrib["Name"] == "Friday Night"
        assert inner.attrib["Type"] == "1"
        assert inner.attrib["Entries"] == "1"
        track_refs = inner.findall("TRACK")
        assert len(track_refs) == 1
        assert track_refs[0].attrib["Key"] == "1"

class TestRekordboxXMLTrackAttributes:
    """TRACK element attribute mapping."""

    def test_required_attributes(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(track_id=42, name="Exhale", artist="Amelie Lens",
                            duration_s=420)],
            set_name="Test",
        )
        root = _parse_xml(xml)
        track = root.find(".//COLLECTION/TRACK")
        assert track is not None
        assert track.attrib["TrackID"] == "42"
        assert track.attrib["Name"] == "Exhale"
        assert track.attrib["Artist"] == "Amelie Lens"
        assert track.attrib["TotalTime"] == "420"

    def test_optional_attributes(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(
                bpm=136.0, tonality="Am", album="Night", genre="Techno",
                label="Lenske", year=2025, date_added="2025-12-01",
                comments="Peak", colour="0xFF0000",
            )],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
        assert track.attrib["AverageBpm"] == "136.00"
        assert track.attrib["Tonality"] == "Am"
        assert track.attrib["Album"] == "Night"
        assert track.attrib["Genre"] == "Techno"
        assert track.attrib["Label"] == "Lenske"
        assert track.attrib["Year"] == "2025"
        assert track.attrib["DateAdded"] == "2025-12-01"
        assert track.attrib["Comments"] == "Peak"
        assert track.attrib["Colour"] == "0xFF0000"

    def test_location_format(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(
                location="file://localhost/Users/dj/Music/001.%20Exhale.mp3",
            )],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
        assert track.attrib["Location"] == "file://localhost/Users/dj/Music/001.%20Exhale.mp3"

class TestRekordboxXMLTempo:
    """TEMPO element (beatgrid) tests."""

    def test_single_tempo(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(
                tempos=[RekordboxTempo(position_s=0.098, bpm=136.0)],
            )],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        tempo = track.find("TEMPO")
        assert tempo is not None
        assert tempo.attrib["Inizio"] == "0.098"
        assert tempo.attrib["Bpm"] == "136.00"
        assert tempo.attrib["Metro"] == "4/4"
        assert tempo.attrib["Battito"] == "1"

    def test_variable_tempo(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(tempos=[
                RekordboxTempo(position_s=0.098, bpm=128.0),
                RekordboxTempo(position_s=120.5, bpm=130.0),
            ])],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        tempos = track.findall("TEMPO")
        assert len(tempos) == 2
        assert tempos[1].attrib["Bpm"] == "130.00"

    def test_no_tempo_means_no_element(self):
        xml = export_rekordbox_xml([_make_rb_track()], set_name="Test")
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track.find("TEMPO") is None

class TestRekordboxXMLPositionMarks:
    """POSITION_MARK element tests for all cue types."""

    def test_hot_cue(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=64.098, cue_type=0, hotcue_num=0,
                    name="Drop", red=255, green=0, blue=0,
                ),
            ])],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        pm = track.find("POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Type"] == "0"
        assert pm.attrib["Num"] == "0"
        assert pm.attrib["Name"] == "Drop"
        assert pm.attrib["Start"] == "64.098"
        assert pm.attrib["Red"] == "255"
        assert pm.attrib["Green"] == "0"
        assert pm.attrib["Blue"] == "0"

    def test_memory_cue(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=128.0, cue_type=0, hotcue_num=-1,
                    name="Break",
                ),
            ])],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm.attrib["Num"] == "-1"
        # Memory cues should NOT have Red/Green/Blue
        assert "Red" not in pm.attrib

    def test_fade_in(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=0.098, cue_type=1, hotcue_num=-1,
                    end_s=32.098,
                ),
            ])],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm.attrib["Type"] == "1"
        assert pm.attrib["Start"] == "0.098"
        assert pm.attrib["End"] == "32.098"

    def test_fade_out(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=384.0, cue_type=2, hotcue_num=-1,
                    end_s=420.0,
                ),
            ])],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm.attrib["Type"] == "2"
        assert pm.attrib["End"] == "420.000"

    def test_load_point(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=0.098, cue_type=3, hotcue_num=-1,
                ),
            ])],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm.attrib["Type"] == "3"

    def test_loop(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=192.098, cue_type=4, hotcue_num=2,
                    end_s=200.098, name="Build Loop",
                    red=255, green=128, blue=0,
                ),
            ])],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm.attrib["Type"] == "4"
        assert pm.attrib["Start"] == "192.098"
        assert pm.attrib["End"] == "200.098"
        assert pm.attrib["Num"] == "2"
        assert pm.attrib["Name"] == "Build Loop"

    def test_memory_loop(self):
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=[
                RekordboxCuePoint(
                    position_s=96.0, cue_type=4, hotcue_num=-1,
                    end_s=104.0, name="Breakdown",
                ),
            ])],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm.attrib["Num"] == "-1"
        assert "Red" not in pm.attrib

    def test_multiple_marks_ordered(self):
        marks = [
            RekordboxCuePoint(position_s=0.0, cue_type=3, hotcue_num=-1),
            RekordboxCuePoint(position_s=0.0, cue_type=0, hotcue_num=-1, name="Intro"),
            RekordboxCuePoint(position_s=64.0, cue_type=0, hotcue_num=0, name="Drop",
                              red=255, green=0, blue=0),
            RekordboxCuePoint(position_s=0.0, cue_type=1, hotcue_num=-1, end_s=32.0),
            RekordboxCuePoint(position_s=384.0, cue_type=2, hotcue_num=-1, end_s=420.0),
            RekordboxCuePoint(position_s=192.0, cue_type=4, hotcue_num=-1, end_s=200.0),
        ]
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=marks)], set_name="Test",
        )
        pms = _parse_xml(xml).findall(".//COLLECTION/TRACK/POSITION_MARK")
        assert len(pms) == 6

class TestRekordboxXMLComprehensive:
    """Full-featured export test."""

    def test_full_set(self):
        tracks = [
            RekordboxTrackData(
                track_id=1, name="Exhale", artist="Amelie Lens",
                duration_s=420,
                location="file://localhost/Music/001.%20Amelie%20Lens%20-%20Exhale.mp3",
                bpm=136.0, tonality="Am", genre="Techno", label="Lenske",
                year=2025, date_added="2025-12-01", colour="0xFF0000",
                tempos=[RekordboxTempo(position_s=0.098, bpm=136.0)],
                position_marks=[
                    RekordboxCuePoint(position_s=0.098, cue_type=3, hotcue_num=-1),
                    RekordboxCuePoint(position_s=0.098, cue_type=0, hotcue_num=-1,
                                      name="Intro"),
                    RekordboxCuePoint(position_s=64.098, cue_type=0, hotcue_num=0,
                                      name="Drop", red=255, green=0, blue=0),
                    RekordboxCuePoint(position_s=0.098, cue_type=1, hotcue_num=-1,
                                      end_s=32.098),
                    RekordboxCuePoint(position_s=384.0, cue_type=2, hotcue_num=-1,
                                      end_s=420.0),
                    RekordboxCuePoint(position_s=192.0, cue_type=4, hotcue_num=-1,
                                      end_s=200.0, name="Build"),
                ],
            ),
            RekordboxTrackData(
                track_id=2, name="Remembrance", artist="ANNA",
                duration_s=390,
                location="file://localhost/Music/002.%20ANNA%20-%20Remembrance.mp3",
                bpm=138.0, tonality="Cm",
            ),
        ]
        xml = export_rekordbox_xml(tracks, set_name="Friday Night Techno")
        root = _parse_xml(xml)

        # Structure
        assert root.tag == "DJ_PLAYLISTS"
        coll = root.find("COLLECTION")
        assert coll.attrib["Entries"] == "2"
        xml_tracks = coll.findall("TRACK")
        assert len(xml_tracks) == 2

        # First track has all metadata
        t1 = xml_tracks[0]
        assert t1.attrib["AverageBpm"] == "136.00"
        assert t1.find("TEMPO") is not None
        assert len(t1.findall("POSITION_MARK")) == 6

        # Second track is minimal
        t2 = xml_tracks[1]
        assert t2.attrib["AverageBpm"] == "138.00"
        assert t2.find("TEMPO") is None
        assert len(t2.findall("POSITION_MARK")) == 0

        # Playlist references
        playlist = root.find(".//PLAYLISTS/NODE/NODE")
        assert playlist.attrib["Name"] == "Friday Night Techno"
        refs = playlist.findall("TRACK")
        assert [r.attrib["Key"] for r in refs] == ["1", "2"]

    def test_valid_xml_declaration(self):
        xml = export_rekordbox_xml([], set_name="Test")
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/services/test_set_export.py -k "Rekordbox" -v
```

Expected: FAIL — `ImportError: cannot import name 'export_rekordbox_xml'`

**Step 3: Write the implementation**

Add to `app/services/set_export.py` after the JSON section:

```python
# ---------------------------------------------------------------------------
# Rekordbox XML export
# ---------------------------------------------------------------------------

import xml.etree.ElementTree as ET

from app.services.rekordbox_types import RekordboxTrackData

def export_rekordbox_xml(
    tracks: list[RekordboxTrackData],
    *,
    set_name: str,
    product_name: str = "DJ Techno Set Builder",
    product_version: str = "0.1.0",
) -> str:
    """Generate Rekordbox XML (DJ_PLAYLISTS) with full DJ metadata.

    Produces an XML file compatible with Rekordbox, djay Pro, Mixxx,
    and Traktor (via converter).

    Args:
        tracks: Ordered list of track data.
        set_name: Playlist / set name.
        product_name: Name for the PRODUCT element.
        product_version: Version for the PRODUCT element.

    Returns:
        UTF-8 XML string with ``<?xml ...?>`` declaration.
    """
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name=product_name,
                  Version=product_version, Company="")

    # --- COLLECTION ---
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))

    for td in tracks:
        attrs: dict[str, str] = {
            "TrackID": str(td.track_id),
            "Name": td.name,
            "Artist": td.artist,
            "Composer": "",
            "Album": td.album,
            "Grouping": "",
            "Genre": td.genre,
            "Kind": td.kind,
            "Size": str(td.size),
            "TotalTime": str(td.duration_s),
            "DiscNumber": "0",
            "TrackNumber": "0",
            "Year": str(td.year) if td.year else "0",
            "DateAdded": td.date_added,
            "BitRate": str(td.bitrate),
            "SampleRate": str(td.sample_rate),
            "Comments": td.comments,
            "PlayCount": "0",
            "Rating": "0",
            "Location": td.location,
            "Remixer": "",
            "Label": td.label,
            "Mix": "",
        }
        if td.bpm is not None:
            attrs["AverageBpm"] = f"{td.bpm:.2f}"
        if td.tonality:
            attrs["Tonality"] = td.tonality
        if td.colour:
            attrs["Colour"] = td.colour

        track_el = ET.SubElement(collection, "TRACK", **attrs)

        # TEMPO elements (beatgrid)
        for tempo in td.tempos:
            ET.SubElement(track_el, "TEMPO",
                          Inizio=f"{tempo.position_s:.3f}",
                          Bpm=f"{tempo.bpm:.2f}",
                          Metro=tempo.metro,
                          Battito=str(tempo.beat))

        # POSITION_MARK elements
        for pm in td.position_marks:
            pm_attrs: dict[str, str] = {
                "Name": pm.name,
                "Type": str(pm.cue_type),
                "Start": f"{pm.position_s:.3f}",
                "Num": str(pm.hotcue_num),
            }
            if pm.end_s is not None:
                pm_attrs["End"] = f"{pm.end_s:.3f}"
            # Color only for hot cues (Num >= 0)
            if pm.hotcue_num >= 0:
                pm_attrs["Red"] = str(pm.red)
                pm_attrs["Green"] = str(pm.green)
                pm_attrs["Blue"] = str(pm.blue)
            ET.SubElement(track_el, "POSITION_MARK", **pm_attrs)

    # --- PLAYLISTS ---
    playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(playlists, "NODE",
                              Type="0", Name="ROOT", Count="1")
    playlist_node = ET.SubElement(root_node, "NODE",
                                  Name=set_name, Type="1",
                                  KeyType="0",
                                  Entries=str(len(tracks)))
    for td in tracks:
        ET.SubElement(playlist_node, "TRACK", Key=str(td.track_id))

    # Serialize with XML declaration
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    from io import BytesIO
    buf = BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue().decode("UTF-8")
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/services/test_set_export.py -k "Rekordbox" -v
```

Expected: ALL PASS

**Step 5: Lint check**

```bash
uv run ruff check app/services/set_export.py app/services/rekordbox_types.py
uv run mypy app/services/set_export.py app/services/rekordbox_types.py
```

**Step 6: Commit**

```bash
git add app/services/set_export.py app/services/rekordbox_types.py \
       tests/services/test_set_export.py tests/services/test_rekordbox_types.py
git commit -m "feat: add export_rekordbox_xml() pure function with tests"
```

---

## Task 3: Batch Repository Methods

New repos for DjCuePoint, DjSavedLoop, DjBeatgrid with batch `get_by_track_ids()`.
Extend existing repos for sections, genres, labels, albums.

**Files:**
- Create: `app/repositories/dj_cue_points.py`
- Create: `app/repositories/dj_saved_loops.py`
- Create: `app/repositories/dj_beatgrid.py`
- Modify: `app/repositories/sections.py` (add batch method)
- Modify: `app/repositories/tracks.py` (add genre/label/album batch methods)
- Test: `tests/repositories/test_batch_methods.py`

**Step 1: Write failing tests**

```python
# tests/repositories/test_batch_methods.py
"""Tests for batch repository methods used by Rekordbox XML export.

These tests verify the SQL layer returns correct groupings.
Uses in-memory SQLite from conftest.py fixtures.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Artist, Genre, Label, Release, Track,
    TrackArtist, TrackGenre, TrackRelease,
)
from app.models.dj import DjBeatgrid, DjCuePoint, DjSavedLoop
from app.models.sections import TrackSection
from app.repositories.dj_beatgrid import DjBeatgridRepository
from app.repositories.dj_cue_points import DjCuePointRepository
from app.repositories.dj_saved_loops import DjSavedLoopRepository
from app.repositories.sections import SectionsRepository
from app.repositories.tracks import TrackRepository

@pytest.fixture
async def two_tracks(session: AsyncSession) -> tuple[int, int]:
    """Create two tracks and return their IDs."""
    t1 = Track(track_id=100, title="Track A", duration_ms=300_000)
    t2 = Track(track_id=200, title="Track B", duration_ms=400_000)
    session.add_all([t1, t2])
    await session.flush()
    return t1.track_id, t2.track_id

class TestDjCuePointRepository:
    async def test_get_by_track_ids_empty(self, session: AsyncSession):
        repo = DjCuePointRepository(session)
        result = await repo.get_by_track_ids([])
        assert result == {}

    async def test_get_by_track_ids(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, tid2 = two_tracks
        session.add_all([
            DjCuePoint(track_id=tid1, position_ms=0, cue_kind=0, hotcue_index=0),
            DjCuePoint(track_id=tid1, position_ms=64000, cue_kind=0, hotcue_index=1),
            DjCuePoint(track_id=tid2, position_ms=32000, cue_kind=0),
        ])
        await session.flush()

        repo = DjCuePointRepository(session)
        result = await repo.get_by_track_ids([tid1, tid2])
        assert len(result[tid1]) == 2
        assert len(result[tid2]) == 1

    async def test_missing_tracks_absent(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        session.add(DjCuePoint(track_id=tid1, position_ms=0, cue_kind=0))
        await session.flush()

        repo = DjCuePointRepository(session)
        result = await repo.get_by_track_ids([tid1, 999])
        assert tid1 in result
        assert 999 not in result

class TestDjSavedLoopRepository:
    async def test_get_by_track_ids(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        session.add(DjSavedLoop(
            track_id=tid1, in_ms=96000, out_ms=104000, length_ms=8000,
        ))
        await session.flush()

        repo = DjSavedLoopRepository(session)
        result = await repo.get_by_track_ids([tid1])
        assert len(result[tid1]) == 1
        assert result[tid1][0].in_ms == 96000

class TestDjBeatgridRepository:
    async def test_get_canonical_by_track_ids(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, tid2 = two_tracks
        session.add_all([
            DjBeatgrid(track_id=tid1, source_app=1, bpm=136.0,
                       first_downbeat_ms=98, is_canonical=True),
            DjBeatgrid(track_id=tid1, source_app=2, bpm=136.0,
                       first_downbeat_ms=100, is_canonical=False),
            DjBeatgrid(track_id=tid2, source_app=1, bpm=140.0,
                       first_downbeat_ms=50, is_canonical=True),
        ])
        await session.flush()

        repo = DjBeatgridRepository(session)
        result = await repo.get_canonical_by_track_ids([tid1, tid2])
        assert result[tid1].bpm == 136.0
        assert result[tid1].first_downbeat_ms == 98  # canonical one
        assert result[tid2].bpm == 140.0

    async def test_no_canonical_returns_empty(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        session.add(DjBeatgrid(
            track_id=tid1, source_app=1, bpm=136.0,
            first_downbeat_ms=98, is_canonical=False,
        ))
        await session.flush()

        repo = DjBeatgridRepository(session)
        result = await repo.get_canonical_by_track_ids([tid1])
        assert tid1 not in result

class TestSectionsRepositoryBatch:
    async def test_get_latest_by_track_ids(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        # Need a feature_extraction_run for FK
        from app.models.runs import FeatureExtractionRun
        run = FeatureExtractionRun(
            track_id=tid1, pipeline_name="test", pipeline_version="1",
            status=2,  # completed
        )
        session.add(run)
        await session.flush()

        session.add_all([
            TrackSection(
                track_id=tid1, run_id=run.run_id,
                start_ms=0, end_ms=32000, section_type=0,
                section_duration_ms=32000,
            ),
            TrackSection(
                track_id=tid1, run_id=run.run_id,
                start_ms=32000, end_ms=96000, section_type=2,
                section_duration_ms=64000,
            ),
        ])
        await session.flush()

        repo = SectionsRepository(session)
        result = await repo.get_latest_by_track_ids([tid1])
        assert len(result[tid1]) == 2

class TestTrackRepositoryBatch:
    async def test_get_genres_for_tracks(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        g = Genre(name="Techno")
        session.add(g)
        await session.flush()
        session.add(TrackGenre(track_id=tid1, genre_id=g.genre_id))
        await session.flush()

        repo = TrackRepository(session)
        result = await repo.get_genres_for_tracks([tid1])
        assert result[tid1] == ["Techno"]

    async def test_get_labels_for_tracks(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        label = Label(name="Drumcode")
        session.add(label)
        await session.flush()
        release = Release(title="EP", label_id=label.label_id)
        session.add(release)
        await session.flush()
        session.add(TrackRelease(track_id=tid1, release_id=release.release_id))
        await session.flush()

        repo = TrackRepository(session)
        result = await repo.get_labels_for_tracks([tid1])
        assert result[tid1] == ["Drumcode"]

    async def test_get_albums_for_tracks(
        self, session: AsyncSession, two_tracks: tuple[int, int],
    ):
        tid1, _ = two_tracks
        release = Release(title="Night Sessions")
        session.add(release)
        await session.flush()
        session.add(TrackRelease(track_id=tid1, release_id=release.release_id))
        await session.flush()

        repo = TrackRepository(session)
        result = await repo.get_albums_for_tracks([tid1])
        assert result[tid1] == ["Night Sessions"]
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/repositories/test_batch_methods.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement repositories**

```python
# app/repositories/dj_cue_points.py
"""Repository for DJ cue points with batch loading."""

from sqlalchemy import select

from app.models.dj import DjCuePoint
from app.repositories.base import BaseRepository

class DjCuePointRepository(BaseRepository[DjCuePoint]):
    model = DjCuePoint

    async def get_by_track_ids(
        self, track_ids: list[int],
    ) -> dict[int, list[DjCuePoint]]:
        """Batch-load cue points for given track IDs.

        Returns dict[track_id] -> list of DjCuePoint, ordered by position.
        """
        if not track_ids:
            return {}
        stmt = (
            select(DjCuePoint)
            .where(DjCuePoint.track_id.in_(track_ids))
            .order_by(DjCuePoint.track_id, DjCuePoint.position_ms)
        )
        result = await self.session.execute(stmt)
        cues_map: dict[int, list[DjCuePoint]] = {}
        for cue in result.scalars():
            cues_map.setdefault(cue.track_id, []).append(cue)
        return cues_map
```

```python
# app/repositories/dj_saved_loops.py
"""Repository for DJ saved loops with batch loading."""

from sqlalchemy import select

from app.models.dj import DjSavedLoop
from app.repositories.base import BaseRepository

class DjSavedLoopRepository(BaseRepository[DjSavedLoop]):
    model = DjSavedLoop

    async def get_by_track_ids(
        self, track_ids: list[int],
    ) -> dict[int, list[DjSavedLoop]]:
        """Batch-load saved loops for given track IDs.

        Returns dict[track_id] -> list of DjSavedLoop, ordered by in_ms.
        """
        if not track_ids:
            return {}
        stmt = (
            select(DjSavedLoop)
            .where(DjSavedLoop.track_id.in_(track_ids))
            .order_by(DjSavedLoop.track_id, DjSavedLoop.in_ms)
        )
        result = await self.session.execute(stmt)
        loops_map: dict[int, list[DjSavedLoop]] = {}
        for loop in result.scalars():
            loops_map.setdefault(loop.track_id, []).append(loop)
        return loops_map
```

```python
# app/repositories/dj_beatgrid.py
"""Repository for DJ beatgrids with batch loading."""

from sqlalchemy import select

from app.models.dj import DjBeatgrid
from app.repositories.base import BaseRepository

class DjBeatgridRepository(BaseRepository[DjBeatgrid]):
    model = DjBeatgrid

    async def get_canonical_by_track_ids(
        self, track_ids: list[int],
    ) -> dict[int, DjBeatgrid]:
        """Batch-load canonical beatgrids for given track IDs.

        Returns dict[track_id] -> DjBeatgrid (only is_canonical=True).
        Tracks without a canonical beatgrid are absent from the dict.
        """
        if not track_ids:
            return {}
        stmt = (
            select(DjBeatgrid)
            .where(
                DjBeatgrid.track_id.in_(track_ids),
                DjBeatgrid.is_canonical.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        return {bg.track_id: bg for bg in result.scalars()}
```

Extend `app/repositories/sections.py`:

```python
    async def get_latest_by_track_ids(
        self, track_ids: list[int],
    ) -> dict[int, list[TrackSection]]:
        """Batch-load sections for given track IDs (latest run per track).

        Returns dict[track_id] -> list of TrackSection, ordered by start_ms.
        """
        if not track_ids:
            return {}
        # Get all sections, grouped by track_id, ordered by start_ms.
        # For simplicity, return all runs — caller filters if needed.
        stmt = (
            select(self.model)
            .where(self.model.track_id.in_(track_ids))
            .order_by(self.model.track_id, self.model.start_ms)
        )
        result = await self.session.execute(stmt)
        sections_map: dict[int, list[TrackSection]] = {}
        for section in result.scalars():
            sections_map.setdefault(section.track_id, []).append(section)
        return sections_map
```

Extend `app/repositories/tracks.py` with two new methods:

```python
    async def get_genres_for_tracks(
        self, track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load genre names for given track IDs."""
        if not track_ids:
            return {}
        from app.models.catalog import Genre, TrackGenre
        stmt = (
            select(TrackGenre.track_id, Genre.name)
            .join(Genre, TrackGenre.genre_id == Genre.genre_id)
            .where(TrackGenre.track_id.in_(track_ids))
            .order_by(TrackGenre.track_id)
        )
        result = await self.session.execute(stmt)
        genres_map: dict[int, list[str]] = {}
        for tid, name in result:
            genres_map.setdefault(tid, []).append(name)
        return genres_map

    async def get_labels_for_tracks(
        self, track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load label names for given track IDs (via releases)."""
        if not track_ids:
            return {}
        from app.models.catalog import Label, Release, TrackRelease
        stmt = (
            select(TrackRelease.track_id, Label.name)
            .join(Release, TrackRelease.release_id == Release.release_id)
            .join(Label, Release.label_id == Label.label_id)
            .where(TrackRelease.track_id.in_(track_ids))
            .order_by(TrackRelease.track_id)
            .distinct()
        )
        result = await self.session.execute(stmt)
        labels_map: dict[int, list[str]] = {}
        for tid, name in result:
            labels_map.setdefault(tid, []).append(name)
        return labels_map

    async def get_albums_for_tracks(
        self, track_ids: list[int],
    ) -> dict[int, list[str]]:
        """Batch-load album/release titles for given track IDs."""
        if not track_ids:
            return {}
        from app.models.catalog import Release, TrackRelease
        stmt = (
            select(TrackRelease.track_id, Release.title)
            .join(Release, TrackRelease.release_id == Release.release_id)
            .where(TrackRelease.track_id.in_(track_ids))
            .order_by(TrackRelease.track_id)
        )
        result = await self.session.execute(stmt)
        albums_map: dict[int, list[str]] = {}
        for tid, title in result:
            albums_map.setdefault(tid, []).append(title)
        return albums_map
```

**Step 4: Run tests**

```bash
uv run pytest tests/repositories/test_batch_methods.py -v
```

**Step 5: Lint**

```bash
uv run ruff check app/repositories/dj_cue_points.py app/repositories/dj_saved_loops.py \
    app/repositories/dj_beatgrid.py app/repositories/sections.py app/repositories/tracks.py
uv run mypy app/repositories/dj_cue_points.py app/repositories/dj_saved_loops.py \
    app/repositories/dj_beatgrid.py
```

**Step 6: Commit**

```bash
git add app/repositories/dj_cue_points.py app/repositories/dj_saved_loops.py \
       app/repositories/dj_beatgrid.py app/repositories/sections.py \
       app/repositories/tracks.py tests/repositories/test_batch_methods.py
git commit -m "feat: add batch repository methods for Rekordbox export"
```

---

## Task 4: Key Name Mapping

Add `get_key_names(key_codes)` to KeyRepository for musical key name lookup.

**Files:**
- Modify: `app/repositories/keys.py`
- Test: `tests/repositories/test_batch_methods.py` (add test)

**Step 1: Write the failing test**

Add to `tests/repositories/test_batch_methods.py`:

```python
from app.models.harmony import Key
from app.repositories.keys import KeyRepository

class TestKeyRepositoryBatch:
    async def test_get_key_names(self, session: AsyncSession):
        session.add_all([
            Key(key_code=18, pitch_class=9, mode=0, name="Am", camelot="8A"),
            Key(key_code=0, pitch_class=0, mode=0, name="Cm", camelot="5A"),
        ])
        await session.flush()

        repo = KeyRepository(session)
        result = await repo.get_key_names([18, 0])
        assert result[18] == "Am"
        assert result[0] == "Cm"

    async def test_get_key_names_empty(self, session: AsyncSession):
        repo = KeyRepository(session)
        result = await repo.get_key_names([])
        assert result == {}
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/repositories/test_batch_methods.py::TestKeyRepositoryBatch -v
```

**Step 3: Implement**

Add to `app/repositories/keys.py`:

```python
from sqlalchemy import select

from app.models.harmony import Key
from app.repositories.base import BaseRepository

class KeyRepository(BaseRepository[Key]):
    model = Key

    async def get_key_names(
        self, key_codes: list[int],
    ) -> dict[int, str]:
        """Batch-load musical key names for given key codes.

        Returns dict[key_code] -> name (e.g. 18 -> "Am").
        """
        if not key_codes:
            return {}
        stmt = (
            select(Key.key_code, Key.name)
            .where(Key.key_code.in_(key_codes))
        )
        result = await self.session.execute(stmt)
        return dict(result.all())
```

**Step 4: Run tests + lint**

```bash
uv run pytest tests/repositories/test_batch_methods.py::TestKeyRepositoryBatch -v
uv run ruff check app/repositories/keys.py
```

**Step 5: Commit**

```bash
git add app/repositories/keys.py tests/repositories/test_batch_methods.py
git commit -m "feat: add KeyRepository.get_key_names() batch method"
```

---

## Task 5: MCP Tool + DI Wiring

Wire up `export_set_rekordbox` MCP tool that collects data from all repos and calls the pure function.

**Files:**
- Modify: `app/mcp/workflows/export_tools.py` (add tool inside `register_export_tools`)
- Modify: `app/mcp/dependencies.py` (add new repo DI providers)

**Step 1: Update dependencies.py**

Add imports and new provider functions to `app/mcp/dependencies.py`:

```python
# New imports:
from app.repositories.dj_beatgrid import DjBeatgridRepository
from app.repositories.dj_cue_points import DjCuePointRepository
from app.repositories.dj_saved_loops import DjSavedLoopRepository
from app.repositories.keys import KeyRepository

# New factory: returns a tuple of repos for the export tool
def get_export_repos(
    session: AsyncSession = Depends(get_session),
) -> tuple[
    DjCuePointRepository,
    DjSavedLoopRepository,
    DjBeatgridRepository,
    SectionsRepository,
    KeyRepository,
]:
    """Build all repositories needed for Rekordbox XML export."""
    return (
        DjCuePointRepository(session),
        DjSavedLoopRepository(session),
        DjBeatgridRepository(session),
        SectionsRepository(session),
        KeyRepository(session),
    )
```

**Step 2: Add the MCP tool to export_tools.py**

Add inside `register_export_tools()`, after `export_set_json`:

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

        Produces an XML file compatible with Rekordbox, djay Pro,
        Mixxx, and Traktor (via converter).  Includes:
        - Full COLLECTION with track metadata (BPM, key, artist, album, genre, label)
        - TEMPO elements (beatgrid, variable tempo support)
        - POSITION_MARK: hot cues, memory cues, loops, fade-in/out, load point
        - Auto-generated memory cues from section boundaries (intro/drop/outro)
        - PLAYLISTS tree with set name

        Args:
            set_id: DJ set ID (for validation).
            version_id: Set version to export.
            include_cues: Include hot + memory cue points.
            include_loops: Include saved loops (hot + memory).
            include_beatgrid: Include TEMPO elements from beatgrid.
            include_mix_points: Include Fade-In/Fade-Out markers.
            include_sections_as_cues: Convert detected sections to memory cues.
            include_load_point: Include Load Point marker.
            base_path: Base path prefix for file URIs.
        """
        from urllib.parse import quote

        from app.mcp.dependencies import get_export_repos
        from app.repositories.dj_beatgrid import DjBeatgridRepository
        from app.repositories.dj_cue_points import DjCuePointRepository
        from app.repositories.dj_saved_loops import DjSavedLoopRepository
        from app.repositories.keys import KeyRepository
        from app.repositories.sections import SectionsRepository
        from app.services.rekordbox_types import (
            RekordboxCuePoint,
            RekordboxTempo,
            RekordboxTrackData,
        )
        from app.services.set_export import export_rekordbox_xml

        # Section type enum mapping for cue names
        SECTION_NAMES: dict[int, str] = {
            0: "Intro", 1: "Build", 2: "Drop",
            3: "Break", 4: "Outro",
        }

        dj_set = await set_svc.get(set_id)
        items_list = await set_svc.list_items(version_id, offset=0, limit=500)
        items = sorted(items_list.items, key=lambda i: i.sort_index)
        track_ids = [item.track_id for item in items]

        # --- Batch-load all data (no N+1) ---
        artists_map = await track_svc.get_track_artists(track_ids)

        # Repos from session via features_svc (shares same session)
        session = features_svc.features_repo.session
        cue_repo = DjCuePointRepository(session)
        loop_repo = DjSavedLoopRepository(session)
        bg_repo = DjBeatgridRepository(session)
        sec_repo = SectionsRepository(session)
        key_repo = KeyRepository(session)

        cues_map = await cue_repo.get_by_track_ids(track_ids) if include_cues else {}
        loops_map = await loop_repo.get_by_track_ids(track_ids) if include_loops else {}
        bg_map = await bg_repo.get_canonical_by_track_ids(track_ids) if include_beatgrid else {}
        sections_map = (
            await sec_repo.get_latest_by_track_ids(track_ids)
            if include_sections_as_cues else {}
        )

        # Batch-load genres, labels, albums
        from app.repositories.tracks import TrackRepository
        track_repo = TrackRepository(session)
        genres_map = await track_repo.get_genres_for_tracks(track_ids)
        labels_map = await track_repo.get_labels_for_tracks(track_ids)
        albums_map = await track_repo.get_albums_for_tracks(track_ids)

        # Batch-load key names
        key_codes: set[int] = set()
        features_map: dict[int, Any] = {}
        for item in items:
            with contextlib.suppress(NotFoundError):
                feat = await features_svc.get_latest(item.track_id)
                features_map[item.track_id] = feat
                key_codes.add(feat.key_code)
        key_names = await key_repo.get_key_names(list(key_codes)) if key_codes else {}

        # --- Build RekordboxTrackData list ---
        rb_tracks: list[RekordboxTrackData] = []
        for pos, item in enumerate(items, 1):
            title = f"Track {item.track_id}"
            duration_s = 0
            date_added = ""
            with contextlib.suppress(NotFoundError):
                track = await track_svc.get(item.track_id)
                title = track.title
                duration_s = track.duration_ms // 1000
                if hasattr(track, "created_at") and track.created_at:
                    date_added = track.created_at.strftime("%Y-%m-%d")

            artists = artists_map.get(item.track_id, [])
            display = _build_display_name(title, artists)
            safe = _safe_filename(display)
            location = f"file://localhost{base_path}/{quote(f'{pos:03d}. {safe}.mp3')}"

            # Audio features
            feat = features_map.get(item.track_id)
            bpm = feat.bpm if feat else None
            tonality = key_names.get(feat.key_code) if feat else None

            # Tempos from beatgrid
            tempos: list[RekordboxTempo] = []
            bg = bg_map.get(item.track_id)
            if bg:
                tempos.append(RekordboxTempo(
                    position_s=bg.first_downbeat_ms / 1000.0,
                    bpm=bg.bpm,
                ))
                # TODO: variable tempo change points if bg.is_variable_tempo

            # Position marks
            marks: list[RekordboxCuePoint] = []

            # Cue points
            for cue in cues_map.get(item.track_id, []):
                is_hot = cue.hotcue_index is not None and cue.hotcue_index >= 0
                r, g, b = 0, 0, 0
                if cue.color_rgb is not None:
                    r = (cue.color_rgb >> 16) & 0xFF
                    g = (cue.color_rgb >> 8) & 0xFF
                    b = cue.color_rgb & 0xFF

                # Map cue_kind to Rekordbox Type
                rb_type = 0  # default: cue
                if cue.cue_kind == 3:    # FADE_IN
                    rb_type = 1
                elif cue.cue_kind == 4:  # FADE_OUT
                    rb_type = 2
                elif cue.cue_kind == 1:  # LOAD
                    rb_type = 3
                elif cue.cue_kind in (5, 6):  # LOOP_IN, LOOP_OUT — skip, handled by loops
                    continue

                marks.append(RekordboxCuePoint(
                    position_s=cue.position_ms / 1000.0,
                    cue_type=rb_type,
                    hotcue_num=cue.hotcue_index if is_hot else -1,
                    name=cue.label or "",
                    red=r, green=g, blue=b,
                ))

            # Saved loops
            for loop in loops_map.get(item.track_id, []):
                is_hot = loop.hotcue_index is not None and loop.hotcue_index >= 0
                r, g, b = 0, 0, 0
                if loop.color_rgb is not None:
                    r = (loop.color_rgb >> 16) & 0xFF
                    g = (loop.color_rgb >> 8) & 0xFF
                    b = loop.color_rgb & 0xFF
                marks.append(RekordboxCuePoint(
                    position_s=loop.in_ms / 1000.0,
                    cue_type=4,
                    hotcue_num=loop.hotcue_index if is_hot else -1,
                    end_s=loop.out_ms / 1000.0,
                    name=loop.label or "",
                    red=r, green=g, blue=b,
                ))

            # Mix points (fade-in/out from set items as fallback)
            if include_mix_points:
                has_fadein = any(m.cue_type == 1 for m in marks)
                has_fadeout = any(m.cue_type == 2 for m in marks)
                if not has_fadein and item.mix_in_ms is not None:
                    marks.append(RekordboxCuePoint(
                        position_s=item.mix_in_ms / 1000.0,
                        cue_type=1, hotcue_num=-1,
                        end_s=item.mix_in_ms / 1000.0 + 16,
                    ))
                if not has_fadeout and item.mix_out_ms is not None:
                    marks.append(RekordboxCuePoint(
                        position_s=item.mix_out_ms / 1000.0,
                        cue_type=2, hotcue_num=-1,
                        end_s=float(duration_s),
                    ))

            # Section boundaries → memory cues
            if include_sections_as_cues:
                seen_types: set[int] = set()
                for section in sections_map.get(item.track_id, []):
                    if section.section_type in seen_types:
                        continue
                    name = SECTION_NAMES.get(section.section_type)
                    if name:
                        seen_types.add(section.section_type)
                        marks.append(RekordboxCuePoint(
                            position_s=section.start_ms / 1000.0,
                            cue_type=0, hotcue_num=-1, name=name,
                        ))

            # Load point (first downbeat or first cue)
            if include_load_point:
                has_load = any(m.cue_type == 3 for m in marks)
                if not has_load:
                    load_pos = bg.first_downbeat_ms / 1000.0 if bg else 0.0
                    marks.append(RekordboxCuePoint(
                        position_s=load_pos,
                        cue_type=3, hotcue_num=-1,
                    ))

            rb_tracks.append(RekordboxTrackData(
                track_id=item.track_id,
                name=title,
                artist=", ".join(artists),
                duration_s=duration_s,
                location=location,
                bpm=bpm,
                tonality=tonality,
                genre=next(iter(genres_map.get(item.track_id, [])), ""),
                label=next(iter(labels_map.get(item.track_id, [])), ""),
                album=next(iter(albums_map.get(item.track_id, [])), ""),
                date_added=date_added,
                comments=item.notes or "",
                tempos=tempos,
                position_marks=marks,
            ))

        xml_content = export_rekordbox_xml(rb_tracks, set_name=dj_set.name)

        return ExportResult(
            set_id=set_id,
            format="rekordbox_xml",
            track_count=len(items),
            content=xml_content,
        )
```

**Step 3: Run all export tests**

```bash
uv run pytest tests/mcp/test_workflow_export.py tests/services/test_set_export.py -v
```

**Step 4: Lint**

```bash
uv run ruff check app/mcp/workflows/export_tools.py app/mcp/dependencies.py
uv run mypy app/mcp/workflows/export_tools.py app/mcp/dependencies.py
```

**Step 5: Commit**

```bash
git add app/mcp/workflows/export_tools.py app/mcp/dependencies.py
git commit -m "feat: add export_set_rekordbox MCP tool with full DJ metadata"
```

---

## Task 6: MCP Integration Tests

Verify the tool is registered, read-only, tagged, and namespaced.

**Files:**
- Modify: `tests/mcp/test_workflow_export.py` (add tests)

**Step 1: Add tests**

```python
async def test_rekordbox_tool_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.get_tools()
    names = [t.name for t in tools]
    assert "export_set_rekordbox" in names

async def test_rekordbox_tool_is_readonly(workflow_mcp: FastMCP):
    tools = await workflow_mcp.get_tools()
    rb_tool = next(t for t in tools if t.name == "export_set_rekordbox")
    assert rb_tool.annotations.get("readOnlyHint") is True

async def test_rekordbox_tool_has_export_tag(workflow_mcp: FastMCP):
    tools = await workflow_mcp.get_tools()
    rb_tool = next(t for t in tools if t.name == "export_set_rekordbox")
    assert "export" in rb_tool.tags
```

**Step 2: Run**

```bash
uv run pytest tests/mcp/test_workflow_export.py -v
```

**Step 3: Commit**

```bash
git add tests/mcp/test_workflow_export.py
git commit -m "test: add Rekordbox XML MCP tool integration tests"
```

---

## Task 7: Final Lint + Full Test Suite

**Step 1: Full lint pass**

```bash
uv run ruff check && uv run ruff format --check
uv run mypy app/
```

Fix any issues.

**Step 2: Full test suite**

```bash
uv run pytest -v
```

**Step 3: Fix and commit any lint/test fixes**

```bash
git add -A && git commit -m "chore: lint and format fixes for Rekordbox export"
```

---

## Summary

| Task | Description | New Files | Modified Files |
|------|-------------|-----------|----------------|
| 1 | Data classes | `rekordbox_types.py`, test | — |
| 2 | Pure XML function | test | `set_export.py` |
| 3 | Batch repos | 3 new repos, test | `sections.py`, `tracks.py` |
| 4 | Key name mapping | test | `keys.py` |
| 5 | MCP tool + DI | — | `export_tools.py`, `dependencies.py` |
| 6 | MCP integration tests | — | `test_workflow_export.py` |
| 7 | Final lint + full suite | — | — |

**Total: ~7 commits, ~400-500 lines of new code, ~300 lines of tests.**
