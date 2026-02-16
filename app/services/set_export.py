"""M3U and JSON export for DJ sets.

Generates files for djay Pro import (M3U8) and a human-readable
transition guide (JSON) as a DJ cheat sheet.

Pure functions — no DB dependencies.
"""

from __future__ import annotations

import json
from typing import Any

from app.utils.audio._types import TransitionRecommendation


def export_m3u(tracks: list[dict[str, Any]]) -> str:
    """Generate M3U8 playlist for djay Pro import.

    Args:
        tracks: List of dicts with keys: title, duration_s, path.

    Returns:
        M3U8-formatted string.
    """
    lines = ["#EXTM3U"]
    for track in tracks:
        duration = int(track.get("duration_s", 0))
        title = track.get("title", "Unknown")
        path = track.get("path", "")
        lines.append(f"#EXTINF:{duration},{title}")
        lines.append(path)
    return "\n".join(lines) + "\n"


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
        tracks: Ordered list of track dicts (title, path).
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

    guide = {
        "set_name": set_name,
        "energy_arc": energy_arc,
        "quality_score": quality_score,
        "transitions": guide_transitions,
    }

    return json.dumps(guide, indent=2, ensure_ascii=False)
