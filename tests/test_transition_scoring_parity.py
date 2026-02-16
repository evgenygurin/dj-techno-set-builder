"""Test parity between different transition scoring entry points.

Verifies that GA, API, and MCP paths produce consistent scoring results
when using the unified scoring approach with DB-backed Camelot lookup.

Uses conftest.py ``session`` fixture (in-memory SQLite).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.features import TrackAudioFeaturesComputed
from app.models.harmony import Key, KeyEdge
from app.models.runs import FeatureExtractionRun
from app.services.camelot_lookup import CamelotLookupService
from app.services.transition_scoring import TrackFeatures, TransitionScoringService
from app.services.transition_scoring_unified import (
    UnifiedTransitionScoringService,
    _score_components,
)
from app.utils.audio.feature_conversion import orm_features_to_track_features

# ═══════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════


def _feature_kwargs(track_id: int, run_id: int) -> dict:
    """Build a complete kwargs dict for TrackAudioFeaturesComputed."""
    return {
        "track_id": track_id,
        "run_id": run_id,
        "bpm": 128.0 + track_id * 4,
        "tempo_confidence": 0.9,
        "bpm_stability": 0.95,
        "lufs_i": -8.0 - track_id,
        "rms_dbfs": -12.0,
        "energy_mean": 0.5 + 0.05 * track_id,
        "energy_max": 0.8,
        "energy_std": 0.05,
        "key_code": (track_id * 4) % 24,
        "key_confidence": 0.85,
        "sub_energy": 0.3,
        "low_energy": 0.5,
        "lowmid_energy": 0.4,
        "mid_energy": 0.4,
        "highmid_energy": 0.3,
        "high_energy": 0.2,
        "centroid_mean_hz": 2000.0 + track_id * 200,
        "onset_rate_mean": 5.0 + track_id * 0.5,
    }


async def _seed_keys_and_edges(session: AsyncSession) -> None:
    """Seed Key + KeyEdge rows needed by FK constraints."""
    names = [
        "Cm",
        "C",
        "C#m",
        "Db",
        "Dm",
        "D",
        "Ebm",
        "Eb",
        "Em",
        "E",
        "Fm",
        "F",
        "F#m",
        "F#",
        "Gm",
        "G",
        "G#m",
        "Ab",
        "Am",
        "A",
        "Bbm",
        "Bb",
        "Bm",
        "B",
    ]
    for key_code in range(24):
        pitch_class = key_code // 2
        mode = key_code % 2
        session.add(
            Key(key_code=key_code, pitch_class=pitch_class, mode=mode, name=names[key_code])
        )
    await session.flush()

    from app.utils.audio.camelot import camelot_distance

    for i in range(24):
        for j in range(24):
            dist = camelot_distance(i, j)
            weight = max(0.0, 1.0 - dist / 6.0)
            session.add(
                KeyEdge(
                    from_key_code=i,
                    to_key_code=j,
                    distance=float(dist),
                    weight=weight,
                    rule="test-seed",
                )
            )
    await session.flush()


async def _seed_two_tracks(
    session: AsyncSession,
) -> tuple[TrackAudioFeaturesComputed, TrackAudioFeaturesComputed]:
    """Create 2 tracks + features. Returns (feat_a, feat_b)."""
    await _seed_keys_and_edges(session)

    t1 = Track(title="Track A", duration_ms=300_000)
    t2 = Track(title="Track B", duration_ms=300_000)
    session.add_all([t1, t2])

    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add(run)
    await session.flush()

    feat_a = TrackAudioFeaturesComputed(**_feature_kwargs(t1.track_id, run.run_id))
    feat_b = TrackAudioFeaturesComputed(**_feature_kwargs(t2.track_id, run.run_id))
    session.add_all([feat_a, feat_b])
    await session.flush()
    return feat_a, feat_b


# ═══════════════════════════════════════════════════════════
# Pure unit tests (no DB)
# ═══════════════════════════════════════════════════════════


class TestFallbackLookup:
    """Verify TransitionScoringService fallback Camelot lookup."""

    def test_completeness(self) -> None:
        """Fallback table covers all 576 key pairs."""
        scorer = TransitionScoringService()
        assert len(scorer.camelot_lookup) == 576

    def test_same_key_is_one(self) -> None:
        scorer = TransitionScoringService()
        for k in range(24):
            assert scorer.camelot_lookup[(k, k)] == 1.0

    def test_symmetry(self) -> None:
        """Distance is symmetric, so scores should be too."""
        scorer = TransitionScoringService()
        for i in range(24):
            for j in range(24):
                assert scorer.camelot_lookup[(i, j)] == scorer.camelot_lookup[(j, i)]

    def test_values_in_range(self) -> None:
        scorer = TransitionScoringService()
        for v in scorer.camelot_lookup.values():
            assert 0.0 <= v <= 1.0


class TestOrmFeatureConversion:
    """Verify orm_features_to_track_features canonical converter."""

    @staticmethod
    def _mock_feat(**overrides) -> MagicMock:
        feat = MagicMock(spec=TrackAudioFeaturesComputed)
        feat.bpm = 140.0
        feat.lufs_i = -9.0
        feat.key_code = 18
        feat.key_confidence = 0.85
        feat.low_energy = 0.5
        feat.mid_energy = 0.4
        feat.high_energy = 0.2
        feat.centroid_mean_hz = 2000.0
        feat.onset_rate_mean = 5.0
        for k, v in overrides.items():
            setattr(feat, k, v)
        return feat

    def test_basic_mapping(self) -> None:
        feat = self._mock_feat()
        tf = orm_features_to_track_features(feat)
        assert tf.bpm == 140.0
        assert tf.energy_lufs == -9.0
        assert tf.key_code == 18
        assert tf.harmonic_density == 0.85

    def test_band_ratio_normalisation(self) -> None:
        feat = self._mock_feat(low_energy=0.6, mid_energy=0.3, high_energy=0.1)
        tf = orm_features_to_track_features(feat)
        assert sum(tf.band_ratios) == pytest.approx(1.0)
        assert tf.band_ratios[0] == pytest.approx(0.6)  # low
        assert tf.band_ratios[1] == pytest.approx(0.3)  # mid
        assert tf.band_ratios[2] == pytest.approx(0.1)  # high

    def test_none_fallbacks(self) -> None:
        feat = self._mock_feat(
            key_code=None,
            key_confidence=None,
            low_energy=None,
            mid_energy=None,
            high_energy=None,
            centroid_mean_hz=None,
            onset_rate_mean=None,
        )
        tf = orm_features_to_track_features(feat)
        assert tf.key_code == 0
        assert tf.harmonic_density == 0.5
        assert tf.centroid_hz == 2000.0
        assert tf.onset_rate == 5.0
        assert sum(tf.band_ratios) == pytest.approx(1.0)

    def test_deterministic(self) -> None:
        """Same input produces identical output."""
        feat = self._mock_feat()
        a = orm_features_to_track_features(feat)
        b = orm_features_to_track_features(feat)
        assert a == b


class TestScoreComponentsHelper:
    """Verify _score_components free function produces correct dict."""

    def test_keys(self) -> None:
        scorer = TransitionScoringService()
        tf = TrackFeatures(
            bpm=130,
            energy_lufs=-8,
            key_code=0,
            harmonic_density=0.7,
            centroid_hz=2000,
            band_ratios=[0.4, 0.35, 0.25],
            onset_rate=6.0,
        )
        result = _score_components(scorer, tf, tf)
        assert set(result.keys()) == {"total", "bpm", "harmonic", "energy", "spectral", "groove"}

    def test_self_transition_is_maximal(self) -> None:
        scorer = TransitionScoringService()
        tf = TrackFeatures(
            bpm=130,
            energy_lufs=-8,
            key_code=0,
            harmonic_density=0.7,
            centroid_hz=2000,
            band_ratios=[0.4, 0.35, 0.25],
            onset_rate=6.0,
        )
        result = _score_components(scorer, tf, tf)
        assert result["bpm"] == 1.0
        assert result["energy"] == 1.0
        assert result["groove"] == 1.0
        assert result["total"] > 0.9


# ═══════════════════════════════════════════════════════════
# Integration tests (in-memory SQLite via conftest.session)
# ═══════════════════════════════════════════════════════════


async def test_unified_matches_direct_scorer(session: AsyncSession) -> None:
    """UnifiedTransitionScoringService must produce the same score as manually
    constructing TransitionScoringService + orm_features_to_track_features."""
    feat_a, feat_b = await _seed_two_tracks(session)

    # --- Direct path ---
    camelot_svc = CamelotLookupService(session)
    lookup = await camelot_svc.build_lookup_table()
    scorer = TransitionScoringService(camelot_lookup=lookup)

    tf_a = orm_features_to_track_features(feat_a)
    tf_b = orm_features_to_track_features(feat_b)
    direct_score = scorer.score_transition(tf_a, tf_b)
    direct_components = _score_components(scorer, tf_a, tf_b)

    # --- Unified path ---
    unified_svc = UnifiedTransitionScoringService(session)
    unified_score = await unified_svc.score_by_ids(feat_a.track_id, feat_b.track_id)
    unified_components = await unified_svc.score_components_by_ids(
        feat_a.track_id,
        feat_b.track_id,
    )

    # Total scores must match exactly
    assert direct_score == pytest.approx(unified_score, abs=1e-6)
    # Component scores must match (unified rounds to 4 decimals)
    for key in ("bpm", "harmonic", "energy", "spectral", "groove", "total"):
        assert direct_components[key] == pytest.approx(unified_components[key], abs=1e-4), (
            f"Component {key} mismatch: direct={direct_components[key]}, "
            f"unified={unified_components[key]}"
        )


async def test_unified_score_by_features_matches_score_by_ids(
    session: AsyncSession,
) -> None:
    """score_by_features and score_by_ids must agree for the same pair."""
    feat_a, feat_b = await _seed_two_tracks(session)

    unified_svc = UnifiedTransitionScoringService(session)
    by_ids = await unified_svc.score_by_ids(feat_a.track_id, feat_b.track_id)
    by_feats = await unified_svc.score_by_features(feat_a, feat_b)

    assert by_ids == pytest.approx(by_feats, abs=1e-6)


async def test_unified_components_by_features_matches_by_ids(
    session: AsyncSession,
) -> None:
    """Component dicts from both paths must agree."""
    feat_a, feat_b = await _seed_two_tracks(session)

    unified_svc = UnifiedTransitionScoringService(session)
    comp_ids = await unified_svc.score_components_by_ids(
        feat_a.track_id,
        feat_b.track_id,
    )
    comp_feats = await unified_svc.score_components_by_features(feat_a, feat_b)

    for key in ("bpm", "harmonic", "energy", "spectral", "groove", "total"):
        assert comp_ids[key] == pytest.approx(comp_feats[key], abs=1e-6)


async def test_ga_matrix_uses_same_scoring(session: AsyncSession) -> None:
    """GA's _build_transition_matrix_scored must produce the same value
    as UnifiedTransitionScoringService for the same track pair."""
    feat_a, feat_b = await _seed_two_tracks(session)

    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
    from app.services.set_generation import SetGenerationService
    from app.utils.audio.set_generator import TrackData

    svc = SetGenerationService(
        set_repo=DjSetRepository(session),
        version_repo=DjSetVersionRepository(session),
        item_repo=DjSetItemRepository(session),
        features_repo=AudioFeaturesRepository(session),
    )

    tracks = [
        TrackData(
            track_id=feat_a.track_id,
            bpm=feat_a.bpm,
            energy=feat_a.energy_mean or 0.5,
            key_code=feat_a.key_code or 0,
        ),
        TrackData(
            track_id=feat_b.track_id,
            bpm=feat_b.bpm,
            energy=feat_b.energy_mean or 0.5,
            key_code=feat_b.key_code or 0,
        ),
    ]

    matrix = await svc._build_transition_matrix_scored(tracks)

    # Unified path
    unified_svc = UnifiedTransitionScoringService(session)
    unified_score = await unified_svc.score_by_ids(
        feat_a.track_id,
        feat_b.track_id,
    )

    assert matrix[0, 1] == pytest.approx(unified_score, abs=1e-6), (
        f"GA matrix[0,1]={matrix[0, 1]} != unified={unified_score}"
    )


async def test_db_backed_lookup_matches_fallback_with_same_edges(
    session: AsyncSession,
) -> None:
    """When DB key_edges mirror camelot_distance, DB lookup and fallback
    must produce identical Camelot scores."""
    await _seed_keys_and_edges(session)

    camelot_svc = CamelotLookupService(session)
    db_lookup = await camelot_svc.build_lookup_table()

    fallback_lookup = TransitionScoringService._build_fallback_lookup()

    for pair, db_val in db_lookup.items():
        fb_val = fallback_lookup.get(pair, 0.5)
        assert db_val == pytest.approx(fb_val, abs=1e-6), (
            f"Pair {pair}: DB={db_val}, fallback={fb_val}"
        )


async def test_missing_features_raises_value_error(session: AsyncSession) -> None:
    """UnifiedTransitionScoringService raises ValueError for missing tracks."""
    await _seed_keys_and_edges(session)
    unified_svc = UnifiedTransitionScoringService(session)

    with pytest.raises(ValueError, match="No features found"):
        await unified_svc.score_by_ids(9999, 9998)


async def test_score_bounds(session: AsyncSession) -> None:
    """All scores must be in [0, 1]."""
    feat_a, feat_b = await _seed_two_tracks(session)

    unified_svc = UnifiedTransitionScoringService(session)
    score = await unified_svc.score_by_ids(feat_a.track_id, feat_b.track_id)
    assert 0.0 <= score <= 1.0

    components = await unified_svc.score_components_by_ids(
        feat_a.track_id,
        feat_b.track_id,
    )
    for key, val in components.items():
        assert 0.0 <= val <= 1.0, f"Component {key}={val} out of [0,1]"
