"""Tests for M3U and JSON set export."""

import json

from app.services.set_export import export_json_guide, export_m3u
from app.utils.audio._types import TransitionRecommendation, TransitionType

# ── M3U export ──


def test_export_m3u_format():
    """M3U should follow EXTM3U format with EXTINF lines."""
    tracks = [
        {"title": "Artist A - Track One", "duration_s": 432, "path": "/music/track1.mp3"},
        {"title": "Artist B - Track Two", "duration_s": 398, "path": "/music/track2.mp3"},
    ]
    result = export_m3u(tracks)
    lines = result.strip().split("\n")
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "#EXTINF:432,Artist A - Track One"
    assert lines[2] == "/music/track1.mp3"
    assert lines[3] == "#EXTINF:398,Artist B - Track Two"
    assert lines[4] == "/music/track2.mp3"


def test_export_m3u_empty():
    """Empty track list should return just header."""
    result = export_m3u([])
    assert result.strip() == "#EXTM3U"


# ── JSON guide export ──


def test_export_json_guide_structure():
    """JSON guide should contain set metadata and transitions."""
    tracks = [
        {"title": "Artist A - Track One", "path": "/music/track1.mp3"},
        {"title": "Artist B - Track Two", "path": "/music/track2.mp3"},
        {"title": "Artist C - Track Three", "path": "/music/track3.mp3"},
    ]
    transitions = [
        {
            "score": 0.87,
            "bpm_delta": 1.2,
            "energy_delta": 0.5,
            "camelot": "5A -> 5A",
            "recommendation": TransitionRecommendation(
                transition_type=TransitionType.DRUM_SWAP,
                confidence=0.82,
                reason="Track B has stronger kick",
                alt_type=TransitionType.EQ,
            ),
        },
        {
            "score": 0.75,
            "bpm_delta": 2.0,
            "energy_delta": 1.5,
            "camelot": "5A -> 6A",
            "recommendation": TransitionRecommendation(
                transition_type=TransitionType.FILTER,
                confidence=0.7,
                reason="BPM difference 2.0",
            ),
        },
    ]

    result = export_json_guide(
        set_name="Friday Night Techno",
        energy_arc="classic",
        quality_score=0.84,
        tracks=tracks,
        transitions=transitions,
    )

    data = json.loads(result)
    assert data["set_name"] == "Friday Night Techno"
    assert data["energy_arc"] == "classic"
    assert data["quality_score"] == 0.84
    assert len(data["transitions"]) == 2

    t0 = data["transitions"][0]
    assert t0["position"] == 1
    assert t0["from"] == "Artist A - Track One"
    assert t0["to"] == "Artist B - Track Two"
    assert t0["type"] == "drum_swap"
    assert t0["type_confidence"] == 0.82
    assert t0["reason"] == "Track B has stronger kick"
    assert t0["alt_type"] == "eq"


def test_export_json_guide_no_transitions():
    """Single track = no transitions in JSON."""
    tracks = [{"title": "Solo Track", "path": "/music/solo.mp3"}]
    result = export_json_guide(
        set_name="Test",
        energy_arc="progressive",
        quality_score=0.5,
        tracks=tracks,
        transitions=[],
    )
    data = json.loads(result)
    assert data["transitions"] == []
