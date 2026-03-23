"""Tests for set curation service."""

from unittest.mock import MagicMock

from app.services.dj.curation import SetCurationService
from app.domain.audio.classifier.classifier import TrackMood


def _make_mock_feature(
    track_id: int,
    bpm: float = 130.0,
    lufs_i: float = -9.0,
    kick_prominence: float = 0.5,
    centroid_mean_hz: float = 2500.0,
    onset_rate_mean: float = 5.0,
    hp_ratio: float = 2.0,
    key_code: int = 4,
    *,
    flux_mean: float = 0.18,
    flux_std: float = 0.10,
    energy_std: float = 0.13,
    energy_mean: float = 0.22,
    lra_lu: float = 6.6,
    crest_factor_db: float = 13.3,
    flatness_mean: float = 0.06,
) -> MagicMock:
    """Create mock feature with realistic P50 defaults from real data (N=583)."""
    feat = MagicMock()
    feat.track_id = track_id
    feat.bpm = bpm
    feat.lufs_i = lufs_i
    feat.kick_prominence = kick_prominence
    feat.centroid_mean_hz = centroid_mean_hz
    feat.onset_rate_mean = onset_rate_mean
    feat.hp_ratio = hp_ratio
    feat.key_code = key_code
    feat.key_confidence = 0.8
    feat.chroma_entropy = 0.98
    feat.flux_mean = flux_mean
    feat.flux_std = flux_std
    feat.energy_std = energy_std
    feat.energy_mean = energy_mean
    feat.lra_lu = lra_lu
    feat.crest_factor_db = crest_factor_db
    feat.flatness_mean = flatness_mean
    return feat


def test_classify_features_list():
    features = [
        # Ambient dub: slow, quiet, low centroid, high LRA, low onset
        _make_mock_feature(
            1,
            bpm=122,
            lufs_i=-13,
            centroid_mean_hz=1200.0,
            onset_rate_mean=3.0,
            hp_ratio=3.5,
            kick_prominence=0.2,
            lra_lu=10.0,
        ),
        # Peak time: loud, high kick, high energy
        _make_mock_feature(
            2,
            bpm=132,
            lufs_i=-6,
            kick_prominence=0.85,
            energy_mean=0.35,
            onset_rate_mean=6.0,
        ),
        # Driving: mid-range defaults are driving territory
        _make_mock_feature(3, bpm=130, lufs_i=-9),
    ]
    svc = SetCurationService()
    classified = svc.classify_features(features)
    assert classified[1] == TrackMood.AMBIENT_DUB
    assert classified[2] == TrackMood.PEAK_TIME
    assert classified[3] == TrackMood.DRIVING


def test_mood_distribution():
    features = [_make_mock_feature(i, bpm=130, lufs_i=-9) for i in range(10)]
    svc = SetCurationService()
    classified = svc.classify_features(features)
    dist = svc.mood_distribution(classified)
    assert sum(dist.values()) == 10


def test_select_candidates_returns_correct_count():
    # Create diverse features
    features = []
    for i in range(50):
        bpm = 122.0 + i * 0.5
        lufs = -13.0 + i * 0.15
        features.append(
            _make_mock_feature(
                i,
                bpm=bpm,
                lufs_i=lufs,
                kick_prominence=0.3 + i * 0.01,
                centroid_mean_hz=1500 + i * 50,
                onset_rate_mean=3.0 + i * 0.1,
                hp_ratio=1.5 + i * 0.05,
            )
        )
    svc = SetCurationService()
    candidates = svc.select_candidates(features, template_name="classic_60")
    # CLASSIC_60 has 20 slots
    assert len(candidates) <= 20
    assert len(candidates) >= 10  # at least half filled


def test_select_candidates_no_duplicates():
    features = [_make_mock_feature(i, bpm=125 + i % 5, lufs_i=-10 + i % 3) for i in range(40)]
    svc = SetCurationService()
    candidates = svc.select_candidates(features, template_name="classic_60")
    track_ids = [c.track_id for c in candidates]
    assert len(track_ids) == len(set(track_ids))


def test_select_candidates_respects_exclude():
    features = [_make_mock_feature(i, bpm=130, lufs_i=-9) for i in range(30)]
    svc = SetCurationService()
    excluded = {0, 1, 2, 3, 4}
    candidates = svc.select_candidates(features, template_name="classic_60", exclude_ids=excluded)
    for c in candidates:
        assert c.track_id not in excluded
