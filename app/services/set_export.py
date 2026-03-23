"""M3U, JSON, and Rekordbox XML export for DJ sets.

Generates:
- **Extended M3U8** for djay Pro / VLC / rekordbox import with:
  - ``#PLAYLIST:`` header with set name
  - ``#EXTINF:`` with duration and display title
  - ``#EXTART:`` / ``#EXTGENRE:`` per track
  - ``#EXTVLCOPT:start-time`` / ``stop-time`` for mix in/out points
  - ``#EXTDJ-*`` custom directives for BPM, key, energy, cue points,
    loops, transitions, sections, and planned EQ
- **JSON transition guide** as a DJ cheat sheet with full scoring,
  transition recommendations, cue points, and set analytics.
- **Rekordbox XML** (``DJ_PLAYLISTS``) with full metadata: tracks,
  beatgrid (TEMPO), cue points, loops, mix points, load point
  (POSITION_MARK), and playlist tree.

Custom ``#EXTDJ-*`` lines follow the M3U convention: players that do
not recognise them simply skip them (safe backward compatibility).

Pure functions -- no DB dependencies.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any

from app.audio._types import TransitionRecommendation
from app.services.rekordbox_types import RekordboxTrackData

# ---------------------------------------------------------------------------
# M3U export
# ---------------------------------------------------------------------------


def export_m3u(
    tracks: list[dict[str, Any]],
    *,
    set_name: str | None = None,
    transitions: list[dict[str, Any]] | None = None,
) -> str:
    """Generate Extended M3U8 playlist with full DJ metadata.

    Args:
        tracks: Ordered list of track dicts.  Recognised keys:
            **required**: ``title``, ``duration_s``, ``path``
            **optional**: ``artists``, ``genre``, ``bpm``, ``key``,
            ``energy``, ``mix_in_s``, ``mix_out_s``, ``cue_points``,
            ``loops``, ``sections``, ``planned_eq``, ``notes``
        set_name: Optional playlist display name (``#PLAYLIST:`` header).
        transitions: Optional list of transition dicts between consecutive
            tracks.  Each dict may contain ``type``, ``score``,
            ``confidence``, ``reason``, ``alt_type``, ``bpm_delta``,
            ``energy_delta``, ``camelot``, ``mix_out_s``, ``mix_in_s``.

    Returns:
        UTF-8 M3U8-formatted string.
    """
    lines: list[str] = ["#EXTM3U"]

    if set_name:
        lines.append(f"#PLAYLIST:{set_name}")

    for idx, track in enumerate(tracks):
        duration = int(track.get("duration_s", 0))
        title = track.get("title", "Unknown")
        path = track.get("path", "")
        artists = track.get("artists", "")
        genre = track.get("genre", "")

        # --- Standard Extended M3U tags ---
        lines.append(f"#EXTINF:{duration},{title}")

        if artists:
            lines.append(f"#EXTART:{artists}")
        if genre:
            lines.append(f"#EXTGENRE:{genre}")

        # --- VLC options: start-time / stop-time (mix in/out) ---
        mix_in_s = track.get("mix_in_s")
        mix_out_s = track.get("mix_out_s")
        if mix_in_s is not None:
            lines.append(f"#EXTVLCOPT:start-time={_fmt_time(mix_in_s)}")
        if mix_out_s is not None:
            lines.append(f"#EXTVLCOPT:stop-time={_fmt_time(mix_out_s)}")

        # --- DJ metadata: BPM, key, energy ---
        bpm = track.get("bpm")
        key = track.get("key")
        energy = track.get("energy")
        if bpm is not None:
            lines.append(f"#EXTDJ-BPM:{bpm}")
        if key is not None:
            lines.append(f"#EXTDJ-KEY:{key}")
        if energy is not None:
            lines.append(f"#EXTDJ-ENERGY:{energy}")

        # --- Cue points ---
        cue_points: list[dict[str, Any]] = track.get("cue_points", [])
        for cue in cue_points:
            cue_name = cue.get("name", "")
            cue_time = _fmt_time(cue.get("time_s", 0))
            cue_type = cue.get("type", "hot")  # hot | memory
            cue_color = cue.get("color", "")
            parts = [f"time={cue_time}", f"type={cue_type}"]
            if cue_name:
                parts.append(f"name={cue_name}")
            if cue_color:
                parts.append(f"color={cue_color}")
            lines.append(f"#EXTDJ-CUE:{','.join(parts)}")

        # --- Loops ---
        loops: list[dict[str, Any]] = track.get("loops", [])
        for loop in loops:
            loop_in = _fmt_time(loop.get("start_s", 0))
            loop_out = _fmt_time(loop.get("end_s", 0))
            loop_name = loop.get("name", "")
            parts = [f"in={loop_in}", f"out={loop_out}"]
            if loop_name:
                parts.append(f"name={loop_name}")
            lines.append(f"#EXTDJ-LOOP:{','.join(parts)}")

        # --- Sections (intro, drop, breakdown, outro etc.) ---
        sections: list[dict[str, Any]] = track.get("sections", [])
        for section in sections:
            sec_type = section.get("type", "unknown")
            sec_start = _fmt_time(section.get("start_s", 0))
            sec_end = _fmt_time(section.get("end_s", 0))
            sec_energy = section.get("energy")
            parts = [f"type={sec_type}", f"start={sec_start}", f"end={sec_end}"]
            if sec_energy is not None:
                parts.append(f"energy={sec_energy}")
            lines.append(f"#EXTDJ-SECTION:{','.join(parts)}")

        # --- Planned EQ (low / mid / high adjustments) ---
        planned_eq: dict[str, Any] | None = track.get("planned_eq")
        if planned_eq:
            eq_parts = [f"{k}={v}" for k, v in planned_eq.items()]
            lines.append(f"#EXTDJ-EQ:{','.join(eq_parts)}")

        # --- Notes ---
        notes = track.get("notes")
        if notes:
            lines.append(f"#EXTDJ-NOTE:{notes}")

        # --- Transition TO NEXT track (placed before the file path) ---
        if transitions and idx < len(transitions):
            trans = transitions[idx]
            lines.append(_format_transition_line(trans))

        # File path (always last for this track entry)
        lines.append(path)

    return "\n".join(lines) + "\n"


def _format_transition_line(trans: dict[str, Any]) -> str:
    """Format a single ``#EXTDJ-TRANSITION:`` line."""
    parts: list[str] = []
    if "type" in trans:
        parts.append(f"type={trans['type']}")
    if "score" in trans:
        parts.append(f"score={trans['score']}")
    if "confidence" in trans:
        parts.append(f"confidence={trans['confidence']}")
    if "bpm_delta" in trans:
        parts.append(f"bpm_delta={trans['bpm_delta']}")
    if "energy_delta" in trans:
        parts.append(f"energy_delta={trans['energy_delta']}")
    if "camelot" in trans:
        parts.append(f"camelot={trans['camelot']}")
    if "reason" in trans:
        parts.append(f"reason={trans['reason']}")
    if "alt_type" in trans:
        parts.append(f"alt_type={trans['alt_type']}")
    if "mix_out_s" in trans:
        parts.append(f"mix_out={_fmt_time(trans['mix_out_s'])}")
    if "mix_in_s" in trans:
        parts.append(f"mix_in={_fmt_time(trans['mix_in_s'])}")
    return f"#EXTDJ-TRANSITION:{','.join(parts)}" if parts else "#EXTDJ-TRANSITION:fade"


def _fmt_time(seconds: float | int | None) -> str:
    """Format seconds as a decimal string (e.g. ``128.500``)."""
    if seconds is None:
        return "0"
    return f"{float(seconds):.3f}"


# ---------------------------------------------------------------------------
# JSON guide export
# ---------------------------------------------------------------------------


def export_json_guide(
    *,
    set_name: str,
    energy_arc: str,
    quality_score: float,
    tracks: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> str:
    """Generate JSON transition guide as DJ cheat sheet.

    Args:
        set_name: Name of the DJ set.
        energy_arc: Energy arc type used (classic/progressive/roller/wave).
        quality_score: Overall set quality score [0, 1].
        tracks: Ordered list of track dicts (title, path, bpm, key, etc.).
        transitions: List of transition dicts with score, bpm_delta,
            energy_delta, camelot, and recommendation (TransitionRecommendation).

    Returns:
        JSON string with set metadata and per-transition recommendations.
    """
    guide_transitions: list[dict[str, Any]] = []

    for i, trans in enumerate(transitions):
        rec: TransitionRecommendation | None = trans.get("recommendation")
        entry: dict[str, Any] = {
            "position": i + 1,
            "from": tracks[i]["title"] if i < len(tracks) else "",
            "to": tracks[i + 1]["title"] if i + 1 < len(tracks) else "",
            "score": trans.get("score", 0.0),
            "bpm_delta": trans.get("bpm_delta", 0.0),
            "energy_delta": trans.get("energy_delta", 0.0),
            "camelot": trans.get("camelot", ""),
        }

        # Mix in / out points
        if "mix_out_s" in trans:
            entry["mix_out_s"] = trans["mix_out_s"]
        if "mix_in_s" in trans:
            entry["mix_in_s"] = trans["mix_in_s"]

        if rec is not None:
            entry["type"] = str(rec.transition_type)
            entry["type_confidence"] = rec.confidence
            entry["reason"] = rec.reason
            entry["alt_type"] = str(rec.alt_type) if rec.alt_type else None
        else:
            entry["type"] = "fade"
            entry["type_confidence"] = 0.0
            entry["reason"] = ""
            entry["alt_type"] = None

        guide_transitions.append(entry)

    # Track-level details for the guide
    guide_tracks: list[dict[str, Any]] = []
    for i, track in enumerate(tracks):
        t: dict[str, Any] = {
            "position": i + 1,
            "title": track.get("title", ""),
        }
        for field in (
            "artists",
            "bpm",
            "key",
            "energy",
            "duration_s",
            "mix_in_s",
            "mix_out_s",
            "genre",
        ):
            if field in track and track[field] is not None:
                t[field] = track[field]

        # Cue points and loops
        if track.get("cue_points"):
            t["cue_points"] = track["cue_points"]
        if track.get("loops"):
            t["loops"] = track["loops"]
        if track.get("sections"):
            t["sections"] = track["sections"]
        if track.get("planned_eq"):
            t["planned_eq"] = track["planned_eq"]
        if track.get("notes"):
            t["notes"] = track["notes"]

        guide_tracks.append(t)

    # Set-level analytics
    bpms: list[Any] = [t["bpm"] for t in tracks if t.get("bpm") is not None]
    energies: list[Any] = [t["energy"] for t in tracks if t.get("energy") is not None]
    scores = [t.get("score", 0.0) for t in transitions]

    analytics: dict[str, Any] = {}
    if bpms:
        analytics["bpm_range"] = [min(bpms), max(bpms)]
    if energies:
        analytics["energy_range"] = [min(energies), max(energies)]
    if scores:
        analytics["avg_transition_score"] = round(sum(scores) / len(scores), 3)
    if tracks:
        total_s = sum(t.get("duration_s", 0) for t in tracks)
        analytics["total_duration_s"] = total_s

    guide: dict[str, Any] = {
        "set_name": set_name,
        "energy_arc": energy_arc,
        "quality_score": quality_score,
        "track_count": len(tracks),
        "tracks": guide_tracks,
        "transitions": guide_transitions,
    }
    if analytics:
        guide["analytics"] = analytics

    return json.dumps(guide, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Rekordbox XML export
# ---------------------------------------------------------------------------


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
    ET.SubElement(root, "PRODUCT", Name=product_name, Version=product_version, Company="")

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

        track_el = ET.SubElement(collection, "TRACK", **attrs)  # type: ignore[arg-type]

        # TEMPO elements (beatgrid)
        for tempo in td.tempos:
            ET.SubElement(
                track_el,
                "TEMPO",
                Inizio=f"{tempo.position_s:.3f}",
                Bpm=f"{tempo.bpm:.2f}",
                Metro=tempo.metro,
                Battito=str(tempo.beat),
            )

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
            ET.SubElement(track_el, "POSITION_MARK", **pm_attrs)  # type: ignore[arg-type]

    # --- PLAYLISTS ---
    playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    playlist_node = ET.SubElement(
        root_node, "NODE", Name=set_name, Type="1", KeyType="0", Entries=str(len(tracks))
    )
    for td in tracks:
        ET.SubElement(playlist_node, "TRACK", Key=str(td.track_id))

    # Serialize with XML declaration
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    buf = BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue().decode("UTF-8")
