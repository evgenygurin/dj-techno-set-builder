"""Tests for M3U, JSON, and Rekordbox XML set export.

Covers:
- Extended M3U8 header, EXTINF, EXTART, EXTGENRE
- VLC options (start-time / stop-time for mix in/out)
- Custom #EXTDJ-* directives: BPM, KEY, ENERGY, CUE, LOOP, SECTION, EQ, NOTE
- #EXTDJ-TRANSITION between consecutive tracks
- JSON guide: metadata, transitions, analytics, cue points, loops, sections
- Rekordbox XML (DJ_PLAYLISTS): structure, tracks, tempos, position marks
- Edge cases: empty tracks, missing fields, partial data
"""

import json
import xml.etree.ElementTree as ET

from app.services.rekordbox_types import (
    RekordboxCuePoint,
    RekordboxTempo,
    RekordboxTrackData,
)
from app.services.set_export import export_json_guide, export_m3u, export_rekordbox_xml
from app.utils.audio._types import TransitionRecommendation, TransitionType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lines(result: str) -> list[str]:
    """Split export result into lines, stripping trailing newline."""
    return result.strip().split("\n")


def _make_track(**overrides: object) -> dict[str, object]:
    """Create a minimal track dict with optional overrides."""
    base: dict[str, object] = {
        "title": "Test Track",
        "duration_s": 300,
        "path": "/music/test.mp3",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# M3U: basic format
# ---------------------------------------------------------------------------


class TestM3UBasicFormat:
    """Core M3U structure tests."""

    def test_header(self):
        result = export_m3u([])
        assert result.strip() == "#EXTM3U"

    def test_single_track(self):
        tracks = [_make_track(title="Intro", duration_s=60, path="/a.mp3")]
        lines = _lines(export_m3u(tracks))
        assert lines[0] == "#EXTM3U"
        assert lines[1] == "#EXTINF:60,Intro"
        assert lines[2] == "/a.mp3"

    def test_two_tracks_ordering(self):
        tracks = [
            _make_track(title="A", duration_s=432, path="/music/track1.mp3"),
            _make_track(title="B", duration_s=398, path="/music/track2.mp3"),
        ]
        lines = _lines(export_m3u(tracks))
        assert lines[0] == "#EXTM3U"
        assert "#EXTINF:432,A" in lines
        assert "#EXTINF:398,B" in lines
        # File paths present
        assert "/music/track1.mp3" in lines
        assert "/music/track2.mp3" in lines

    def test_playlist_name_header(self):
        tracks = [_make_track()]
        result = export_m3u(tracks, set_name="Friday Night Techno")
        lines = _lines(result)
        assert lines[1] == "#PLAYLIST:Friday Night Techno"

    def test_no_playlist_name(self):
        result = export_m3u([_make_track()])
        assert "#PLAYLIST:" not in result

    def test_trailing_newline(self):
        """M3U must end with a newline."""
        result = export_m3u([_make_track()])
        assert result.endswith("\n")

    def test_duration_truncated_to_int(self):
        """Duration should be integer seconds in EXTINF."""
        tracks = [_make_track(duration_s=432.7)]
        lines = _lines(export_m3u(tracks))
        assert "#EXTINF:432,Test Track" in lines

    def test_missing_duration_defaults_to_zero(self):
        tracks = [{"title": "No Duration", "path": "/x.mp3"}]
        lines = _lines(export_m3u(tracks))
        assert "#EXTINF:0,No Duration" in lines

    def test_missing_title_defaults_to_unknown(self):
        tracks = [{"duration_s": 100, "path": "/x.mp3"}]
        lines = _lines(export_m3u(tracks))
        assert "#EXTINF:100,Unknown" in lines


# ---------------------------------------------------------------------------
# M3U: artist & genre tags
# ---------------------------------------------------------------------------


class TestM3UArtistGenre:
    def test_extart_present(self):
        tracks = [_make_track(artists="DJ Rush")]
        result = export_m3u(tracks)
        assert "#EXTART:DJ Rush" in result

    def test_extgenre_present(self):
        tracks = [_make_track(genre="Techno")]
        result = export_m3u(tracks)
        assert "#EXTGENRE:Techno" in result

    def test_no_artist_no_extart(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTART:" not in result

    def test_no_genre_no_extgenre(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTGENRE:" not in result

    def test_empty_artist_string(self):
        tracks = [_make_track(artists="")]
        result = export_m3u(tracks)
        assert "#EXTART:" not in result


# ---------------------------------------------------------------------------
# M3U: VLC options (mix in/out)
# ---------------------------------------------------------------------------


class TestM3UVlcOptions:
    """EXTVLCOPT:start-time / stop-time for mix in/out points."""

    def test_mix_in_produces_start_time(self):
        tracks = [_make_track(mix_in_s=32.5)]
        result = export_m3u(tracks)
        assert "#EXTVLCOPT:start-time=32.500" in result

    def test_mix_out_produces_stop_time(self):
        tracks = [_make_track(mix_out_s=280.0)]
        result = export_m3u(tracks)
        assert "#EXTVLCOPT:stop-time=280.000" in result

    def test_both_mix_points(self):
        tracks = [_make_track(mix_in_s=16.0, mix_out_s=290.0)]
        result = export_m3u(tracks)
        assert "#EXTVLCOPT:start-time=16.000" in result
        assert "#EXTVLCOPT:stop-time=290.000" in result

    def test_no_mix_points_no_vlc_opts(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTVLCOPT:" not in result

    def test_zero_mix_in_still_emitted(self):
        """mix_in_s=0 is a valid value (start at 0), should still emit."""
        tracks = [_make_track(mix_in_s=0)]
        result = export_m3u(tracks)
        assert "#EXTVLCOPT:start-time=0.000" in result

    def test_none_mix_in_not_emitted(self):
        """Explicit None should NOT emit a VLC option."""
        tracks = [_make_track(mix_in_s=None)]
        result = export_m3u(tracks)
        assert "#EXTVLCOPT:" not in result


# ---------------------------------------------------------------------------
# M3U: DJ metadata (BPM, key, energy)
# ---------------------------------------------------------------------------


class TestM3UDjMetadata:
    def test_bpm_tag(self):
        tracks = [_make_track(bpm=138.0)]
        result = export_m3u(tracks)
        assert "#EXTDJ-BPM:138.0" in result

    def test_key_tag(self):
        tracks = [_make_track(key="5A")]
        result = export_m3u(tracks)
        assert "#EXTDJ-KEY:5A" in result

    def test_energy_tag(self):
        tracks = [_make_track(energy=-8.5)]
        result = export_m3u(tracks)
        assert "#EXTDJ-ENERGY:-8.5" in result

    def test_no_features_no_dj_tags(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTDJ-BPM:" not in result
        assert "#EXTDJ-KEY:" not in result
        assert "#EXTDJ-ENERGY:" not in result

    def test_all_dj_metadata(self):
        tracks = [_make_track(bpm=140, key="8B", energy=-6.2)]
        result = export_m3u(tracks)
        assert "#EXTDJ-BPM:140" in result
        assert "#EXTDJ-KEY:8B" in result
        assert "#EXTDJ-ENERGY:-6.2" in result


# ---------------------------------------------------------------------------
# M3U: Cue points
# ---------------------------------------------------------------------------


class TestM3UCuePoints:
    def test_hot_cue(self):
        tracks = [
            _make_track(
                cue_points=[
                    {"time_s": 32.0, "type": "hot", "name": "Drop", "color": "#FF0000"},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-CUE:time=32.000,type=hot,name=Drop,color=#FF0000" in result

    def test_memory_cue(self):
        tracks = [
            _make_track(
                cue_points=[
                    {"time_s": 0.0, "type": "memory", "name": "Start"},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-CUE:time=0.000,type=memory,name=Start" in result

    def test_cue_without_name_and_color(self):
        tracks = [
            _make_track(
                cue_points=[
                    {"time_s": 64.5, "type": "hot"},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-CUE:time=64.500,type=hot" in result

    def test_multiple_cue_points(self):
        tracks = [
            _make_track(
                cue_points=[
                    {"time_s": 0.0, "type": "memory", "name": "Start"},
                    {"time_s": 32.0, "type": "hot", "name": "Drop 1"},
                    {"time_s": 128.0, "type": "hot", "name": "Drop 2"},
                ]
            )
        ]
        lines = _lines(export_m3u(tracks))
        cue_lines = [ln for ln in lines if ln.startswith("#EXTDJ-CUE:")]
        assert len(cue_lines) == 3

    def test_cue_default_type_is_hot(self):
        tracks = [_make_track(cue_points=[{"time_s": 10.0}])]
        result = export_m3u(tracks)
        assert "type=hot" in result

    def test_no_cue_points_no_tags(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTDJ-CUE:" not in result


# ---------------------------------------------------------------------------
# M3U: Loops
# ---------------------------------------------------------------------------


class TestM3ULoops:
    def test_basic_loop(self):
        tracks = [
            _make_track(
                loops=[
                    {"start_s": 64.0, "end_s": 96.0, "name": "Breakdown"},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-LOOP:in=64.000,out=96.000,name=Breakdown" in result

    def test_loop_without_name(self):
        tracks = [
            _make_track(
                loops=[
                    {"start_s": 128.0, "end_s": 132.0},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-LOOP:in=128.000,out=132.000" in result

    def test_multiple_loops(self):
        tracks = [
            _make_track(
                loops=[
                    {"start_s": 64.0, "end_s": 96.0},
                    {"start_s": 192.0, "end_s": 224.0},
                ]
            )
        ]
        lines = _lines(export_m3u(tracks))
        loop_lines = [ln for ln in lines if ln.startswith("#EXTDJ-LOOP:")]
        assert len(loop_lines) == 2

    def test_no_loops_no_tags(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTDJ-LOOP:" not in result


# ---------------------------------------------------------------------------
# M3U: Sections
# ---------------------------------------------------------------------------


class TestM3USections:
    def test_section_with_energy(self):
        tracks = [
            _make_track(
                sections=[
                    {"type": "drop", "start_s": 64.0, "end_s": 128.0, "energy": 0.95},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-SECTION:type=drop,start=64.000,end=128.000,energy=0.95" in result

    def test_section_without_energy(self):
        tracks = [
            _make_track(
                sections=[
                    {"type": "intro", "start_s": 0.0, "end_s": 32.0},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "#EXTDJ-SECTION:type=intro,start=0.000,end=32.000" in result

    def test_multiple_sections(self):
        tracks = [
            _make_track(
                sections=[
                    {"type": "intro", "start_s": 0, "end_s": 32},
                    {"type": "buildup", "start_s": 32, "end_s": 64},
                    {"type": "drop", "start_s": 64, "end_s": 128},
                    {"type": "breakdown", "start_s": 128, "end_s": 192},
                    {"type": "outro", "start_s": 256, "end_s": 300},
                ]
            )
        ]
        lines = _lines(export_m3u(tracks))
        sec_lines = [ln for ln in lines if ln.startswith("#EXTDJ-SECTION:")]
        assert len(sec_lines) == 5

    def test_unknown_section_type(self):
        tracks = [
            _make_track(
                sections=[
                    {"start_s": 0, "end_s": 16},
                ]
            )
        ]
        result = export_m3u(tracks)
        assert "type=unknown" in result


# ---------------------------------------------------------------------------
# M3U: Planned EQ
# ---------------------------------------------------------------------------


class TestM3UPlannedEQ:
    def test_eq_adjustments(self):
        tracks = [_make_track(planned_eq={"low": -3.0, "mid": 0.0, "high": 1.5})]
        result = export_m3u(tracks)
        assert "#EXTDJ-EQ:low=-3.0,mid=0.0,high=1.5" in result

    def test_no_eq_no_tag(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTDJ-EQ:" not in result


# ---------------------------------------------------------------------------
# M3U: Notes
# ---------------------------------------------------------------------------


class TestM3UNotes:
    def test_note_tag(self):
        tracks = [_make_track(notes="Swap bass at drop")]
        result = export_m3u(tracks)
        assert "#EXTDJ-NOTE:Swap bass at drop" in result

    def test_no_notes_no_tag(self):
        tracks = [_make_track()]
        result = export_m3u(tracks)
        assert "#EXTDJ-NOTE:" not in result


# ---------------------------------------------------------------------------
# M3U: Transitions
# ---------------------------------------------------------------------------


class TestM3UTransitions:
    def test_transition_between_tracks(self):
        tracks = [
            _make_track(title="A", path="/a.mp3"),
            _make_track(title="B", path="/b.mp3"),
        ]
        transitions = [
            {"type": "drum_swap", "score": 0.87, "confidence": 0.82},
        ]
        result = export_m3u(tracks, transitions=transitions)
        assert "#EXTDJ-TRANSITION:" in result
        assert "type=drum_swap" in result
        assert "score=0.87" in result
        assert "confidence=0.82" in result

    def test_transition_full_details(self):
        tracks = [_make_track(path="/a.mp3"), _make_track(path="/b.mp3")]
        transitions = [
            {
                "type": "eq",
                "score": 0.75,
                "confidence": 0.7,
                "bpm_delta": 2.0,
                "energy_delta": 1.5,
                "camelot": "5A -> 6A",
                "reason": "BPM close enough",
                "alt_type": "filter",
                "mix_out_s": 280.0,
                "mix_in_s": 16.0,
            }
        ]
        result = export_m3u(tracks, transitions=transitions)
        assert "type=eq" in result
        assert "bpm_delta=2.0" in result
        assert "energy_delta=1.5" in result
        assert "camelot=5A -> 6A" in result
        assert "reason=BPM close enough" in result
        assert "alt_type=filter" in result
        assert "mix_out=280.000" in result
        assert "mix_in=16.000" in result

    def test_no_transitions_no_tags(self):
        tracks = [_make_track(), _make_track()]
        result = export_m3u(tracks)
        assert "#EXTDJ-TRANSITION:" not in result

    def test_empty_transition_defaults_to_fade(self):
        tracks = [_make_track(path="/a.mp3"), _make_track(path="/b.mp3")]
        transitions = [{}]
        result = export_m3u(tracks, transitions=transitions)
        assert "#EXTDJ-TRANSITION:fade" in result

    def test_transition_only_for_existing_pairs(self):
        """3 tracks = at most 2 transitions."""
        tracks = [_make_track(path=f"/{i}.mp3") for i in range(3)]
        transitions = [
            {"type": "eq", "score": 0.8},
            {"type": "fade", "score": 0.6},
        ]
        result = export_m3u(tracks, transitions=transitions)
        lines = _lines(result)
        trans_lines = [ln for ln in lines if ln.startswith("#EXTDJ-TRANSITION:")]
        assert len(trans_lines) == 2

    def test_transition_placed_before_file_path(self):
        """Transition line should appear before the file path of its track."""
        tracks = [
            _make_track(title="A", path="/a.mp3"),
            _make_track(title="B", path="/b.mp3"),
        ]
        transitions = [{"type": "eq"}]
        lines = _lines(export_m3u(tracks, transitions=transitions))
        trans_idx = next(i for i, ln in enumerate(lines) if "#EXTDJ-TRANSITION:" in ln)
        path_idx = lines.index("/a.mp3")
        assert trans_idx < path_idx


# ---------------------------------------------------------------------------
# M3U: comprehensive / integration
# ---------------------------------------------------------------------------


class TestM3UComprehensive:
    """Full-featured track with all DJ metadata."""

    def test_full_featured_track(self):
        tracks = [
            _make_track(
                title="Slam - Industrial Strength",
                duration_s=420,
                path="/music/slam.mp3",
                artists="Slam",
                genre="Techno",
                bpm=138.0,
                key="5A",
                energy=-7.2,
                mix_in_s=0.0,
                mix_out_s=400.0,
                cue_points=[
                    {"time_s": 0.0, "type": "memory", "name": "Start"},
                    {"time_s": 64.0, "type": "hot", "name": "Drop", "color": "#FF0000"},
                ],
                loops=[
                    {"start_s": 192.0, "end_s": 224.0, "name": "Breakdown loop"},
                ],
                sections=[
                    {"type": "intro", "start_s": 0, "end_s": 32, "energy": 0.3},
                    {"type": "drop", "start_s": 64, "end_s": 128, "energy": 0.95},
                    {"type": "outro", "start_s": 384, "end_s": 420, "energy": 0.2},
                ],
                planned_eq={"low": -2.0, "mid": 0.0, "high": 1.0},
                notes="Big room energy — careful with bass",
            )
        ]
        result = export_m3u(tracks, set_name="Saturday Night")
        lines = _lines(result)

        # Header
        assert lines[0] == "#EXTM3U"
        assert lines[1] == "#PLAYLIST:Saturday Night"

        # Standard tags
        assert "#EXTINF:420,Slam - Industrial Strength" in result
        assert "#EXTART:Slam" in result
        assert "#EXTGENRE:Techno" in result

        # VLC options
        assert "#EXTVLCOPT:start-time=0.000" in result
        assert "#EXTVLCOPT:stop-time=400.000" in result

        # DJ metadata
        assert "#EXTDJ-BPM:138.0" in result
        assert "#EXTDJ-KEY:5A" in result
        assert "#EXTDJ-ENERGY:-7.2" in result

        # Cue points
        cue_lines = [ln for ln in lines if ln.startswith("#EXTDJ-CUE:")]
        assert len(cue_lines) == 2

        # Loops
        assert "#EXTDJ-LOOP:" in result

        # Sections
        sec_lines = [ln for ln in lines if ln.startswith("#EXTDJ-SECTION:")]
        assert len(sec_lines) == 3

        # EQ
        assert "#EXTDJ-EQ:low=-2.0,mid=0.0,high=1.0" in result

        # Notes
        assert "#EXTDJ-NOTE:Big room energy — careful with bass" in result

        # File path is last for the track block
        assert lines[-1] == "/music/slam.mp3"

    def test_multi_track_with_transitions(self):
        tracks = [
            _make_track(title="A", path="/a.mp3", bpm=136),
            _make_track(title="B", path="/b.mp3", bpm=138),
            _make_track(title="C", path="/c.mp3", bpm=140),
        ]
        transitions = [
            {"type": "drum_swap", "score": 0.9},
            {"type": "eq", "score": 0.8},
        ]
        result = export_m3u(tracks, transitions=transitions)
        lines = _lines(result)

        # All 3 file paths present
        assert "/a.mp3" in lines
        assert "/b.mp3" in lines
        assert "/c.mp3" in lines

        # 2 transitions
        trans_lines = [ln for ln in lines if ln.startswith("#EXTDJ-TRANSITION:")]
        assert len(trans_lines) == 2


# ---------------------------------------------------------------------------
# JSON guide: basic structure
# ---------------------------------------------------------------------------


class TestJsonGuideBasic:
    def _make_simple_guide(self, **kwargs: object) -> dict[str, object]:
        defaults: dict[str, object] = {
            "set_name": "Test Set",
            "energy_arc": "classic",
            "quality_score": 0.8,
            "tracks": [
                {"title": "Track A", "bpm": 136, "duration_s": 300},
                {"title": "Track B", "bpm": 138, "duration_s": 320},
            ],
            "transitions": [
                {
                    "score": 0.85,
                    "bpm_delta": 2.0,
                    "energy_delta": 0.5,
                    "camelot": "5A -> 5A",
                    "recommendation": TransitionRecommendation(
                        transition_type=TransitionType.DRUM_SWAP,
                        confidence=0.82,
                        reason="Compatible kick patterns",
                        alt_type=TransitionType.EQ,
                    ),
                }
            ],
        }
        defaults.update(kwargs)
        result = export_json_guide(**defaults)  # type: ignore[arg-type]
        return json.loads(result)

    def test_set_metadata(self):
        data = self._make_simple_guide()
        assert data["set_name"] == "Test Set"
        assert data["energy_arc"] == "classic"
        assert data["quality_score"] == 0.8
        assert data["track_count"] == 2

    def test_transition_fields(self):
        data = self._make_simple_guide()
        t = data["transitions"][0]
        assert t["position"] == 1
        assert t["from"] == "Track A"
        assert t["to"] == "Track B"
        assert t["score"] == 0.85
        assert t["bpm_delta"] == 2.0
        assert t["energy_delta"] == 0.5
        assert t["camelot"] == "5A -> 5A"
        assert t["type"] == "drum_swap"
        assert t["type_confidence"] == 0.82
        assert t["reason"] == "Compatible kick patterns"
        assert t["alt_type"] == "eq"

    def test_transition_without_recommendation(self):
        data = self._make_simple_guide(
            transitions=[
                {
                    "score": 0.5,
                    "bpm_delta": 3.0,
                    "energy_delta": 1.0,
                    "camelot": "5A -> 7B",
                }
            ],
        )
        t = data["transitions"][0]
        assert t["type"] == "fade"
        assert t["type_confidence"] == 0.0
        assert t["reason"] == ""
        assert t["alt_type"] is None

    def test_no_transitions_empty_list(self):
        tracks = [{"title": "Solo Track", "path": "/music/solo.mp3"}]
        result = export_json_guide(
            set_name="Solo",
            energy_arc="progressive",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        assert data["transitions"] == []


# ---------------------------------------------------------------------------
# JSON guide: track details
# ---------------------------------------------------------------------------


class TestJsonGuideTracks:
    def test_track_position(self):
        tracks = [
            {"title": "A"},
            {"title": "B"},
            {"title": "C"},
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[
                {"score": 0.7, "bpm_delta": 1, "energy_delta": 0.5, "camelot": ""},
                {"score": 0.6, "bpm_delta": 2, "energy_delta": 1.0, "camelot": ""},
            ],
        )
        data = json.loads(result)
        assert len(data["tracks"]) == 3
        assert data["tracks"][0]["position"] == 1
        assert data["tracks"][1]["position"] == 2
        assert data["tracks"][2]["position"] == 3

    def test_track_optional_fields(self):
        tracks = [
            {
                "title": "Full Track",
                "artists": "DJ Test",
                "bpm": 140,
                "key": "8A",
                "energy": -6.5,
                "duration_s": 360,
                "mix_in_s": 16.0,
                "mix_out_s": 340.0,
                "genre": "Techno",
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        t = data["tracks"][0]
        assert t["artists"] == "DJ Test"
        assert t["bpm"] == 140
        assert t["key"] == "8A"
        assert t["energy"] == -6.5
        assert t["duration_s"] == 360
        assert t["mix_in_s"] == 16.0
        assert t["mix_out_s"] == 340.0
        assert t["genre"] == "Techno"

    def test_track_cue_points_in_guide(self):
        tracks = [
            {
                "title": "Track",
                "cue_points": [
                    {"time_s": 0.0, "type": "memory", "name": "Start"},
                    {"time_s": 64.0, "type": "hot", "name": "Drop"},
                ],
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        assert len(data["tracks"][0]["cue_points"]) == 2

    def test_track_loops_in_guide(self):
        tracks = [
            {
                "title": "Track",
                "loops": [{"start_s": 64.0, "end_s": 96.0, "name": "Loop 1"}],
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        assert len(data["tracks"][0]["loops"]) == 1

    def test_track_sections_in_guide(self):
        tracks = [
            {
                "title": "Track",
                "sections": [
                    {"type": "intro", "start_s": 0, "end_s": 32},
                    {"type": "drop", "start_s": 64, "end_s": 128},
                ],
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        assert len(data["tracks"][0]["sections"]) == 2

    def test_track_planned_eq_in_guide(self):
        tracks = [
            {
                "title": "Track",
                "planned_eq": {"low": -3, "mid": 0, "high": 2},
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        assert data["tracks"][0]["planned_eq"] == {"low": -3, "mid": 0, "high": 2}

    def test_track_notes_in_guide(self):
        tracks = [
            {
                "title": "Track",
                "notes": "Watch the energy here",
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        assert data["tracks"][0]["notes"] == "Watch the energy here"

    def test_none_fields_excluded(self):
        """Fields with None value should not appear in track dict."""
        tracks = [{"title": "Track", "bpm": None, "key": None}]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[],
        )
        data = json.loads(result)
        t = data["tracks"][0]
        assert "bpm" not in t
        assert "key" not in t


# ---------------------------------------------------------------------------
# JSON guide: transition mix points
# ---------------------------------------------------------------------------


class TestJsonGuideTransitionMixPoints:
    def test_mix_points_in_transition(self):
        tracks = [{"title": "A"}, {"title": "B"}]
        transitions = [
            {
                "score": 0.8,
                "bpm_delta": 1.0,
                "energy_delta": 0.5,
                "camelot": "5A -> 5A",
                "mix_out_s": 280.0,
                "mix_in_s": 16.0,
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.8,
            tracks=tracks,
            transitions=transitions,
        )
        data = json.loads(result)
        t = data["transitions"][0]
        assert t["mix_out_s"] == 280.0
        assert t["mix_in_s"] == 16.0

    def test_no_mix_points_not_included(self):
        tracks = [{"title": "A"}, {"title": "B"}]
        transitions = [
            {
                "score": 0.5,
                "bpm_delta": 1.0,
                "energy_delta": 0.5,
                "camelot": "",
            }
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=transitions,
        )
        data = json.loads(result)
        t = data["transitions"][0]
        assert "mix_out_s" not in t
        assert "mix_in_s" not in t


# ---------------------------------------------------------------------------
# JSON guide: analytics
# ---------------------------------------------------------------------------


class TestJsonGuideAnalytics:
    def test_bpm_range(self):
        tracks = [
            {"title": "A", "bpm": 130},
            {"title": "B", "bpm": 140},
            {"title": "C", "bpm": 135},
        ]
        transitions = [
            {"score": 0.8, "bpm_delta": 5, "energy_delta": 0, "camelot": ""},
            {"score": 0.7, "bpm_delta": 5, "energy_delta": 0, "camelot": ""},
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.75,
            tracks=tracks,
            transitions=transitions,
        )
        data = json.loads(result)
        assert data["analytics"]["bpm_range"] == [130, 140]

    def test_energy_range(self):
        tracks = [
            {"title": "A", "energy": -10.0},
            {"title": "B", "energy": -5.0},
        ]
        transitions = [
            {"score": 0.7, "bpm_delta": 1, "energy_delta": 5, "camelot": ""},
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.7,
            tracks=tracks,
            transitions=transitions,
        )
        data = json.loads(result)
        assert data["analytics"]["energy_range"] == [-10.0, -5.0]

    def test_avg_transition_score(self):
        tracks = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        transitions = [
            {"score": 0.8, "bpm_delta": 0, "energy_delta": 0, "camelot": ""},
            {"score": 0.6, "bpm_delta": 0, "energy_delta": 0, "camelot": ""},
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.7,
            tracks=tracks,
            transitions=transitions,
        )
        data = json.loads(result)
        assert data["analytics"]["avg_transition_score"] == 0.7

    def test_total_duration(self):
        tracks = [
            {"title": "A", "duration_s": 300},
            {"title": "B", "duration_s": 350},
        ]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[
                {"score": 0.5, "bpm_delta": 0, "energy_delta": 0, "camelot": ""},
            ],
        )
        data = json.loads(result)
        assert data["analytics"]["total_duration_s"] == 650

    def test_analytics_with_no_bpm_tracks(self):
        """Tracks without BPM should not appear in bpm_range."""
        tracks = [{"title": "A"}, {"title": "B"}]
        result = export_json_guide(
            set_name="T",
            energy_arc="classic",
            quality_score=0.5,
            tracks=tracks,
            transitions=[
                {"score": 0.5, "bpm_delta": 0, "energy_delta": 0, "camelot": ""},
            ],
        )
        data = json.loads(result)
        assert "bpm_range" not in data.get("analytics", {})

    def test_valid_json_output(self):
        """Result must be valid JSON."""
        result = export_json_guide(
            set_name="Unicode test \u2764",
            energy_arc="wave",
            quality_score=0.9,
            tracks=[{"title": "Track with unicode"}],
            transitions=[],
        )
        data = json.loads(result)
        assert data["set_name"] == "Unicode test \u2764"
        assert data["tracks"][0]["title"] == "Track with unicode"


# ---------------------------------------------------------------------------
# JSON guide: comprehensive
# ---------------------------------------------------------------------------


class TestJsonGuideComprehensive:
    """Full-featured JSON guide with all possible data."""

    def test_full_guide(self):
        tracks = [
            {
                "title": "Slam - Industrial Strength",
                "artists": "Slam",
                "bpm": 138,
                "key": "5A",
                "energy": -7.2,
                "duration_s": 420,
                "mix_in_s": 0.0,
                "mix_out_s": 400.0,
                "genre": "Techno",
                "cue_points": [
                    {"time_s": 0, "type": "memory", "name": "Start"},
                    {"time_s": 64, "type": "hot", "name": "Drop"},
                ],
                "loops": [{"start_s": 192, "end_s": 224, "name": "Breakdown"}],
                "sections": [
                    {"type": "intro", "start_s": 0, "end_s": 32, "energy": 0.3},
                    {"type": "drop", "start_s": 64, "end_s": 128, "energy": 0.95},
                ],
                "planned_eq": {"low": -2, "mid": 0, "high": 1},
                "notes": "Big room energy",
            },
            {
                "title": "Rebekah - Fear Tactics",
                "artists": "Rebekah",
                "bpm": 140,
                "key": "6A",
                "energy": -6.0,
                "duration_s": 380,
            },
        ]
        transitions = [
            {
                "score": 0.92,
                "bpm_delta": 2.0,
                "energy_delta": 1.2,
                "camelot": "5A -> 6A",
                "mix_out_s": 400.0,
                "mix_in_s": 8.0,
                "recommendation": TransitionRecommendation(
                    transition_type=TransitionType.DRUM_SWAP,
                    confidence=0.88,
                    reason="Compatible kick + close key",
                    alt_type=TransitionType.EQ,
                ),
            }
        ]

        result = export_json_guide(
            set_name="Saturday Night",
            energy_arc="classic",
            quality_score=0.92,
            tracks=tracks,
            transitions=transitions,
        )
        data = json.loads(result)

        # Set metadata
        assert data["set_name"] == "Saturday Night"
        assert data["quality_score"] == 0.92
        assert data["track_count"] == 2

        # Track details
        t0 = data["tracks"][0]
        assert t0["title"] == "Slam - Industrial Strength"
        assert t0["cue_points"] is not None
        assert t0["loops"] is not None
        assert t0["sections"] is not None
        assert t0["planned_eq"] == {"low": -2, "mid": 0, "high": 1}
        assert t0["notes"] == "Big room energy"

        # Transition
        tr = data["transitions"][0]
        assert tr["from"] == "Slam - Industrial Strength"
        assert tr["to"] == "Rebekah - Fear Tactics"
        assert tr["type"] == "drum_swap"
        assert tr["mix_out_s"] == 400.0
        assert tr["mix_in_s"] == 8.0

        # Analytics
        assert data["analytics"]["bpm_range"] == [138, 140]
        assert data["analytics"]["energy_range"] == [-7.2, -6.0]
        assert data["analytics"]["total_duration_s"] == 800


# ---------------------------------------------------------------------------
# Rekordbox XML: helpers
# ---------------------------------------------------------------------------


def _parse_xml(xml_str: str) -> ET.Element:
    """Parse XML string and return root element."""
    return ET.fromstring(xml_str)


def _make_rb_track(**overrides: object) -> RekordboxTrackData:
    """Create a minimal RekordboxTrackData with optional overrides."""
    defaults: dict[str, object] = {
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
            [
                _make_rb_track(
                    track_id=42,
                    name="Exhale",
                    artist="Amelie Lens",
                    duration_s=420,
                )
            ],
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
            [
                _make_rb_track(
                    bpm=136.0,
                    tonality="Am",
                    album="Night",
                    genre="Techno",
                    label="Lenske",
                    year=2025,
                    date_added="2025-12-01",
                    comments="Peak",
                    colour="0xFF0000",
                )
            ],
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
            [
                _make_rb_track(
                    location="file://localhost/Users/dj/Music/001.%20Exhale.mp3",
                )
            ],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
        assert (
            track.attrib["Location"]
            == "file://localhost/Users/dj/Music/001.%20Exhale.mp3"
        )


class TestRekordboxXMLTempo:
    """TEMPO element (beatgrid) tests."""

    def test_single_tempo(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    tempos=[RekordboxTempo(position_s=0.098, bpm=136.0)],
                )
            ],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
        tempo = track.find("TEMPO")
        assert tempo is not None
        assert tempo.attrib["Inizio"] == "0.098"
        assert tempo.attrib["Bpm"] == "136.00"
        assert tempo.attrib["Metro"] == "4/4"
        assert tempo.attrib["Battito"] == "1"

    def test_variable_tempo(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    tempos=[
                        RekordboxTempo(position_s=0.098, bpm=128.0),
                        RekordboxTempo(position_s=120.5, bpm=130.0),
                    ]
                )
            ],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
        tempos = track.findall("TEMPO")
        assert len(tempos) == 2
        assert tempos[1].attrib["Bpm"] == "130.00"

    def test_no_tempo_means_no_element(self):
        xml = export_rekordbox_xml([_make_rb_track()], set_name="Test")
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
        assert track.find("TEMPO") is None


class TestRekordboxXMLPositionMarks:
    """POSITION_MARK element tests for all cue types."""

    def test_hot_cue(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=64.098,
                            cue_type=0,
                            hotcue_num=0,
                            name="Drop",
                            red=255,
                            green=0,
                            blue=0,
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        track = _parse_xml(xml).find(".//COLLECTION/TRACK")
        assert track is not None
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
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=128.0,
                            cue_type=0,
                            hotcue_num=-1,
                            name="Break",
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Num"] == "-1"
        # Memory cues should NOT have Red/Green/Blue
        assert "Red" not in pm.attrib

    def test_fade_in(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=0.098,
                            cue_type=1,
                            hotcue_num=-1,
                            end_s=32.098,
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Type"] == "1"
        assert pm.attrib["Start"] == "0.098"
        assert pm.attrib["End"] == "32.098"

    def test_fade_out(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=384.0,
                            cue_type=2,
                            hotcue_num=-1,
                            end_s=420.0,
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Type"] == "2"
        assert pm.attrib["End"] == "420.000"

    def test_load_point(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=0.098,
                            cue_type=3,
                            hotcue_num=-1,
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Type"] == "3"

    def test_loop(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=192.098,
                            cue_type=4,
                            hotcue_num=2,
                            end_s=200.098,
                            name="Build Loop",
                            red=255,
                            green=128,
                            blue=0,
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Type"] == "4"
        assert pm.attrib["Start"] == "192.098"
        assert pm.attrib["End"] == "200.098"
        assert pm.attrib["Num"] == "2"
        assert pm.attrib["Name"] == "Build Loop"

    def test_memory_loop(self):
        xml = export_rekordbox_xml(
            [
                _make_rb_track(
                    position_marks=[
                        RekordboxCuePoint(
                            position_s=96.0,
                            cue_type=4,
                            hotcue_num=-1,
                            end_s=104.0,
                            name="Breakdown",
                        ),
                    ]
                )
            ],
            set_name="Test",
        )
        pm = _parse_xml(xml).find(".//COLLECTION/TRACK/POSITION_MARK")
        assert pm is not None
        assert pm.attrib["Num"] == "-1"
        assert "Red" not in pm.attrib

    def test_multiple_marks_ordered(self):
        marks = [
            RekordboxCuePoint(position_s=0.0, cue_type=3, hotcue_num=-1),
            RekordboxCuePoint(
                position_s=0.0, cue_type=0, hotcue_num=-1, name="Intro"
            ),
            RekordboxCuePoint(
                position_s=64.0,
                cue_type=0,
                hotcue_num=0,
                name="Drop",
                red=255,
                green=0,
                blue=0,
            ),
            RekordboxCuePoint(
                position_s=0.0, cue_type=1, hotcue_num=-1, end_s=32.0
            ),
            RekordboxCuePoint(
                position_s=384.0, cue_type=2, hotcue_num=-1, end_s=420.0
            ),
            RekordboxCuePoint(
                position_s=192.0, cue_type=4, hotcue_num=-1, end_s=200.0
            ),
        ]
        xml = export_rekordbox_xml(
            [_make_rb_track(position_marks=marks)],
            set_name="Test",
        )
        pms = _parse_xml(xml).findall(".//COLLECTION/TRACK/POSITION_MARK")
        assert len(pms) == 6


class TestRekordboxXMLComprehensive:
    """Full-featured export test."""

    def test_full_set(self):
        tracks = [
            RekordboxTrackData(
                track_id=1,
                name="Exhale",
                artist="Amelie Lens",
                duration_s=420,
                location="file://localhost/Music/001.%20Amelie%20Lens%20-%20Exhale.mp3",
                bpm=136.0,
                tonality="Am",
                genre="Techno",
                label="Lenske",
                year=2025,
                date_added="2025-12-01",
                colour="0xFF0000",
                tempos=[RekordboxTempo(position_s=0.098, bpm=136.0)],
                position_marks=[
                    RekordboxCuePoint(
                        position_s=0.098, cue_type=3, hotcue_num=-1
                    ),
                    RekordboxCuePoint(
                        position_s=0.098,
                        cue_type=0,
                        hotcue_num=-1,
                        name="Intro",
                    ),
                    RekordboxCuePoint(
                        position_s=64.098,
                        cue_type=0,
                        hotcue_num=0,
                        name="Drop",
                        red=255,
                        green=0,
                        blue=0,
                    ),
                    RekordboxCuePoint(
                        position_s=0.098,
                        cue_type=1,
                        hotcue_num=-1,
                        end_s=32.098,
                    ),
                    RekordboxCuePoint(
                        position_s=384.0,
                        cue_type=2,
                        hotcue_num=-1,
                        end_s=420.0,
                    ),
                    RekordboxCuePoint(
                        position_s=192.0,
                        cue_type=4,
                        hotcue_num=-1,
                        end_s=200.0,
                        name="Build",
                    ),
                ],
            ),
            RekordboxTrackData(
                track_id=2,
                name="Remembrance",
                artist="ANNA",
                duration_s=390,
                location="file://localhost/Music/002.%20ANNA%20-%20Remembrance.mp3",
                bpm=138.0,
                tonality="Cm",
            ),
        ]
        xml = export_rekordbox_xml(tracks, set_name="Friday Night Techno")
        root = _parse_xml(xml)

        # Structure
        assert root.tag == "DJ_PLAYLISTS"
        coll = root.find("COLLECTION")
        assert coll is not None
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
        assert playlist is not None
        assert playlist.attrib["Name"] == "Friday Night Techno"
        refs = playlist.findall("TRACK")
        assert [r.attrib["Key"] for r in refs] == ["1", "2"]

    def test_valid_xml_declaration(self):
        xml = export_rekordbox_xml([], set_name="Test")
        assert xml.startswith('<?xml version=\'1.0\' encoding=\'UTF-8\'?>')
