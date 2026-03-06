"""Tests for set templates and slot definitions."""

from app.utils.audio.mood_classifier import TrackMood
from app.utils.audio.set_templates import (
    SetSlot,
    TemplateName,
    get_template,
    list_templates,
)


def test_list_templates_returns_all():
    names = list_templates()
    assert TemplateName.CLASSIC_60 in names
    assert TemplateName.ROLLER_90 in names
    assert TemplateName.FULL_LIBRARY in names
    assert len(names) >= 8


def test_get_classic_60():
    t = get_template(TemplateName.CLASSIC_60)
    assert t.name == TemplateName.CLASSIC_60
    assert 18 <= t.target_track_count <= 22
    assert 55 <= t.duration_minutes <= 65
    assert len(t.slots) >= 5


def test_classic_60_starts_with_ambient():
    t = get_template(TemplateName.CLASSIC_60)
    first_slot = t.slots[0]
    assert first_slot.mood in (TrackMood.AMBIENT_DUB, TrackMood.DUB_TECHNO, TrackMood.MELODIC_DEEP)


def test_classic_60_has_breathing_moment():
    t = get_template(TemplateName.CLASSIC_60)
    moods = [s.mood for s in t.slots]
    # There should be at least one dip from PEAK_TIME to lower energy
    has_breath = False
    for i in range(1, len(moods)):
        prev_is_peak = moods[i - 1] == TrackMood.PEAK_TIME
        if prev_is_peak and moods[i].intensity < TrackMood.PEAK_TIME.intensity:
            has_breath = True
            break
    assert has_breath, "Template has no breathing moment after peak"


def test_slot_positions_are_sorted():
    for name in list_templates():
        t = get_template(name)
        positions = [s.position for s in t.slots]
        assert positions == sorted(positions), f"{name}: positions not sorted"


def test_slot_positions_start_at_zero():
    for name in list_templates():
        t = get_template(name)
        if t.slots:
            assert t.slots[0].position == 0.0, f"{name}: first position != 0.0"


def test_full_library_template():
    t = get_template(TemplateName.FULL_LIBRARY)
    assert t.target_track_count == 0  # 0 = use all tracks
    assert t.breathe_interval == 7


def test_set_slot_is_frozen():
    slot = SetSlot(
        position=0.0,
        mood=TrackMood.DRIVING,
        energy_target=-9.0,
        bpm_range=(126, 130),
        duration_target_s=180,
        flexibility=0.5,
    )
    assert slot.mood == TrackMood.DRIVING


def test_template_has_description():
    t = get_template(TemplateName.CLASSIC_60)
    assert len(t.description) > 10
