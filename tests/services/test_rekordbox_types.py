"""Tests for Rekordbox XML data classes."""

import pytest

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
            position_s=64.0,
            cue_type=0,
            hotcue_num=0,
            name="Drop",
            red=255,
            green=0,
            blue=0,
        )
        assert cue.hotcue_num == 0
        assert cue.red == 255

    def test_loop_has_end(self):
        cue = RekordboxCuePoint(
            position_s=96.0,
            cue_type=4,
            hotcue_num=-1,
            end_s=104.0,
            name="Loop A",
        )
        assert cue.end_s == 104.0

    def test_frozen(self):
        cue = RekordboxCuePoint(position_s=0.0, cue_type=0, hotcue_num=-1)
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
            track_id=1,
            name="Exhale",
            artist="Amelie Lens",
            duration_s=420,
            location="file://localhost/Music/001.%20Exhale.mp3",
        )
        assert td.bpm is None
        assert td.tempos == []
        assert td.position_marks == []

    def test_with_all_fields(self):
        td = RekordboxTrackData(
            track_id=1,
            name="Exhale",
            artist="Amelie Lens",
            duration_s=420,
            location="file://localhost/Music/001.%20Exhale.mp3",
            bpm=136.0,
            tonality="Am",
            album="Album",
            genre="Techno",
            label="Lenske",
            year=2025,
            date_added="2025-12-01",
            comments="Peak time",
            colour="0xFF0000",
            tempos=[RekordboxTempo(position_s=0.098, bpm=136.0)],
            position_marks=[
                RekordboxCuePoint(position_s=0.0, cue_type=0, hotcue_num=0, name="Intro"),
            ],
        )
        assert td.bpm == 136.0
        assert len(td.tempos) == 1
        assert len(td.position_marks) == 1
