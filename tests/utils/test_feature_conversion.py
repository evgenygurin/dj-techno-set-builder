"""Tests for orm_features_to_track_features() with sections parameter."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.audio.feature_conversion import orm_features_to_track_features


def _make_feat(**overrides: object) -> MagicMock:
    """Create a minimal TrackAudioFeaturesComputed mock."""
    feat = MagicMock()
    feat.bpm = 128.0
    feat.lufs_i = -14.0
    feat.key_code = 0
    feat.chroma_entropy = 0.7
    feat.key_confidence = None
    feat.low_energy = 0.3
    feat.mid_energy = 0.5
    feat.high_energy = 0.2
    feat.mfcc_vector = None
    feat.centroid_mean_hz = 2000.0
    feat.onset_rate_mean = 5.0
    feat.kick_prominence = 0.5
    feat.hnr_mean_db = 0.0
    feat.slope_db_per_oct = 0.0
    feat.hp_ratio = 0.5
    for k, v in overrides.items():
        setattr(feat, k, v)
    return feat


def _make_section(section_type: int, start_ms: int, end_ms: int) -> MagicMock:
    """Create a minimal TrackSection mock."""
    sec = MagicMock()
    sec.section_type = section_type
    sec.start_ms = start_ms
    sec.end_ms = end_ms
    return sec


# SectionType int values: 0=intro, 1=buildup, 2=drop, 3=breakdown, 4=outro
INTRO_TYPE = 0
OUTRO_TYPE = 4
BUILDUP_TYPE = 1


def test_no_sections_gives_none_fields() -> None:
    """Regression: without sections, first/last remain None."""
    feat = _make_feat()
    tf = orm_features_to_track_features(feat, sections=None)
    assert tf.first_section is None
    assert tf.last_section is None


def test_sections_populated_intro_outro() -> None:
    """intro->outro pair maps to correct first/last section names."""
    feat = _make_feat()
    intro = _make_section(INTRO_TYPE, start_ms=0, end_ms=32000)
    outro = _make_section(OUTRO_TYPE, start_ms=180000, end_ms=210000)
    tf = orm_features_to_track_features(feat, sections=[outro, intro])  # reversed
    assert tf.first_section == "intro"
    assert tf.last_section == "outro"


def test_sections_sorted_by_start_ms() -> None:
    """Sections should be sorted by start_ms regardless of input order."""
    feat = _make_feat()
    buildup = _make_section(BUILDUP_TYPE, start_ms=30000, end_ms=60000)
    intro = _make_section(INTRO_TYPE, start_ms=0, end_ms=30000)
    tf = orm_features_to_track_features(feat, sections=[buildup, intro])
    assert tf.first_section == "intro"
    assert tf.last_section == "buildup"


def test_invalid_section_type_silently_ignored() -> None:
    """Unknown section_type int (e.g. 99) should not raise — fields stay None."""
    feat = _make_feat()
    invalid = _make_section(99, start_ms=0, end_ms=30000)
    tf = orm_features_to_track_features(feat, sections=[invalid])
    assert tf.first_section is None
    assert tf.last_section is None


def test_empty_sections_list_gives_none() -> None:
    """Empty list should behave like None."""
    feat = _make_feat()
    tf = orm_features_to_track_features(feat, sections=[])
    assert tf.first_section is None
    assert tf.last_section is None
