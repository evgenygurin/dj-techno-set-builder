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
from app.services.transition_scoring import (
    HardConstraints,
    TrackFeatures,
    TransitionScoringService,
    effective_bpm_diff,
)
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

    from app.utils.audio.camelot import camelot_distance, camelot_score

    for i in range(24):
        for j in range(24):
            dist = camelot_distance(i, j)
            weight = camelot_score(i, j)
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
        # Phase 2 fields
        feat.chroma_entropy = None
        feat.mfcc_vector = None
        feat.kick_prominence = None
        feat.hnr_mean_db = None
        feat.slope_db_per_oct = None
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

    def test_chroma_entropy_preferred_over_key_confidence(self) -> None:
        """When chroma_entropy is set, it should be used for harmonic_density."""
        feat = self._mock_feat(chroma_entropy=0.42, key_confidence=0.85)
        tf = orm_features_to_track_features(feat)
        assert tf.harmonic_density == 0.42

    def test_chroma_entropy_fallback_to_key_confidence(self) -> None:
        """When chroma_entropy is None, fall back to key_confidence."""
        feat = self._mock_feat(chroma_entropy=None, key_confidence=0.85)
        tf = orm_features_to_track_features(feat)
        assert tf.harmonic_density == 0.85

    def test_new_phase2_fields_mapped(self) -> None:
        """kick_prominence, hnr_mean_db, slope_db_per_oct should be mapped."""
        feat = self._mock_feat(
            kick_prominence=0.7,
            hnr_mean_db=12.5,
            slope_db_per_oct=-3.2,
            mfcc_vector=(
                "[1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0, 9.0, -10.0, 11.0, -12.0, 13.0]"
            ),
        )
        tf = orm_features_to_track_features(feat)
        assert tf.kick_prominence == 0.7
        assert tf.hnr_db == 12.5
        assert tf.spectral_slope == -3.2
        assert tf.mfcc_vector is not None
        assert len(tf.mfcc_vector) == 13

    def test_new_phase2_fields_fallbacks(self) -> None:
        """None values should use safe defaults."""
        feat = self._mock_feat(
            kick_prominence=None,
            hnr_mean_db=None,
            slope_db_per_oct=None,
            mfcc_vector=None,
            chroma_entropy=None,
        )
        tf = orm_features_to_track_features(feat)
        assert tf.kick_prominence == 0.5
        assert tf.hnr_db == 0.0
        assert tf.spectral_slope == 0.0
        assert tf.mfcc_vector is None

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
        assert set(result.keys()) == {
            "total",
            "bpm",
            "harmonic",
            "energy",
            "spectral",
            "groove",
            "structure",
        }

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
# Hard constraints & filter-then-rank (Phase 1B)
# ═══════════════════════════════════════════════════════════


def _make_tf(**overrides: object) -> TrackFeatures:
    """Build a TrackFeatures with sensible defaults, overriding as needed."""
    defaults: dict[str, object] = {
        "bpm": 130.0,
        "energy_lufs": -8.0,
        "key_code": 0,
        "harmonic_density": 0.7,
        "centroid_hz": 2000.0,
        "band_ratios": [0.4, 0.35, 0.25],
        "onset_rate": 6.0,
    }
    defaults.update(overrides)
    return TrackFeatures(**defaults)  # type: ignore[arg-type]


class TestEffectiveBpmDiff:
    """Verify BPM difference accounting for double/half-time."""

    def test_same_bpm(self) -> None:
        assert effective_bpm_diff(130.0, 130.0) == 0.0

    def test_small_diff(self) -> None:
        assert effective_bpm_diff(128.0, 130.0) == 2.0

    def test_half_time(self) -> None:
        # 140 vs 70 → half-time match
        assert effective_bpm_diff(140.0, 70.0) == 0.0

    def test_double_time(self) -> None:
        # 65 vs 130 → 65*2=130, diff=0
        assert effective_bpm_diff(65.0, 130.0) == 0.0

    def test_near_half_time(self) -> None:
        # 140 vs 72 → normal diff=68, half diff=|140-144|=4, double diff=|140-36|=104
        assert effective_bpm_diff(140.0, 72.0) == pytest.approx(4.0)

    def test_symmetry(self) -> None:
        assert effective_bpm_diff(128.0, 140.0) == effective_bpm_diff(140.0, 128.0)


class TestHardConstraints:
    """Verify the hard-reject filter in TransitionScoringService."""

    def test_identical_tracks_pass(self) -> None:
        scorer = TransitionScoringService()
        tf = _make_tf()
        assert not scorer.check_hard_constraints(tf, tf)

    def test_bpm_within_threshold_passes(self) -> None:
        scorer = TransitionScoringService()
        tf_a = _make_tf(bpm=128.0)
        tf_b = _make_tf(bpm=135.0)  # diff=7, threshold=10
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_bpm_exceeds_threshold_rejects(self) -> None:
        scorer = TransitionScoringService()
        tf_a = _make_tf(bpm=128.0)
        tf_b = _make_tf(bpm=145.0)  # diff=17 > 10
        assert scorer.check_hard_constraints(tf_a, tf_b)

    def test_bpm_half_time_rescues(self) -> None:
        """140 vs 70 should NOT be rejected (half-time match)."""
        scorer = TransitionScoringService()
        tf_a = _make_tf(bpm=140.0)
        tf_b = _make_tf(bpm=70.0)  # effective diff=0
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_camelot_within_threshold_passes(self) -> None:
        scorer = TransitionScoringService()
        # key_code 0=Cm(5A) → key_code 12=F#m(11A): distance=6 ≥ 5 → reject
        # key_code 0=Cm(5A) → key_code 4=Dm(7A): distance=2 → pass
        tf_a = _make_tf(key_code=0)
        tf_b = _make_tf(key_code=4)
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_camelot_exceeds_threshold_rejects(self) -> None:
        scorer = TransitionScoringService()
        # 5A → 11A: distance=6 ≥ 5
        tf_a = _make_tf(key_code=0)
        tf_b = _make_tf(key_code=12)
        assert scorer.check_hard_constraints(tf_a, tf_b)

    def test_camelot_at_boundary_rejects(self) -> None:
        """Distance exactly == max_camelot_distance should reject."""
        scorer = TransitionScoringService()
        # Cm(5A) → Bm(10A): distance=5 ≥ 5 → reject
        tf_a = _make_tf(key_code=0)
        tf_b = _make_tf(key_code=22)  # 10A
        from app.utils.audio.camelot import camelot_distance

        assert camelot_distance(0, 22) == 5  # confirm distance
        assert scorer.check_hard_constraints(tf_a, tf_b)

    def test_energy_within_threshold_passes(self) -> None:
        scorer = TransitionScoringService()
        tf_a = _make_tf(energy_lufs=-8.0)
        tf_b = _make_tf(energy_lufs=-12.0)  # diff=4, threshold=6
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_energy_exceeds_threshold_rejects(self) -> None:
        scorer = TransitionScoringService()
        tf_a = _make_tf(energy_lufs=-6.0)
        tf_b = _make_tf(energy_lufs=-14.0)  # diff=8 > 6
        assert scorer.check_hard_constraints(tf_a, tf_b)

    def test_score_transition_returns_zero_on_reject(self) -> None:
        """score_transition must return 0.0 for hard-rejected pairs."""
        scorer = TransitionScoringService()
        tf_a = _make_tf(bpm=128.0)
        tf_b = _make_tf(bpm=160.0)  # diff=32 >> 10
        assert scorer.score_transition(tf_a, tf_b) == 0.0

    def test_score_transition_nonzero_when_passing(self) -> None:
        scorer = TransitionScoringService()
        tf = _make_tf()
        assert scorer.score_transition(tf, tf) > 0.0


class TestHardConstraintsCustomisation:
    """Verify that constraints can be disabled or customised."""

    def test_disable_bpm_constraint(self) -> None:
        hc = HardConstraints(max_bpm_diff=None)
        scorer = TransitionScoringService(hard_constraints=hc)
        tf_a = _make_tf(bpm=100.0)
        tf_b = _make_tf(bpm=200.0)  # diff=100 — would normally reject
        # BPM disabled, but camelot and energy are same → should pass
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_disable_camelot_constraint(self) -> None:
        hc = HardConstraints(max_camelot_distance=None)
        scorer = TransitionScoringService(hard_constraints=hc)
        tf_a = _make_tf(key_code=0)
        tf_b = _make_tf(key_code=12)  # tritone — would normally reject
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_disable_energy_constraint(self) -> None:
        hc = HardConstraints(max_energy_delta_lufs=None)
        scorer = TransitionScoringService(hard_constraints=hc)
        tf_a = _make_tf(energy_lufs=-5.0)
        tf_b = _make_tf(energy_lufs=-20.0)  # diff=15 — would normally reject
        assert not scorer.check_hard_constraints(tf_a, tf_b)

    def test_disable_all_constraints(self) -> None:
        hc = HardConstraints(
            max_bpm_diff=None,
            max_camelot_distance=None,
            max_energy_delta_lufs=None,
        )
        scorer = TransitionScoringService(hard_constraints=hc)
        tf_a = _make_tf(bpm=60.0, key_code=0, energy_lufs=-5.0)
        tf_b = _make_tf(bpm=180.0, key_code=12, energy_lufs=-20.0)
        assert not scorer.check_hard_constraints(tf_a, tf_b)
        assert scorer.score_transition(tf_a, tf_b) > 0.0

    def test_tighten_bpm_threshold(self) -> None:
        hc = HardConstraints(max_bpm_diff=3.0)
        scorer = TransitionScoringService(hard_constraints=hc)
        tf_a = _make_tf(bpm=130.0)
        tf_b = _make_tf(bpm=134.0)  # diff=4 > 3
        assert scorer.check_hard_constraints(tf_a, tf_b)

    def test_short_circuits_on_first_violation(self) -> None:
        """BPM is checked first — if it rejects, camelot/energy don't matter."""
        scorer = TransitionScoringService()
        # BPM diff = 50, but camelot and energy are fine
        tf_a = _make_tf(bpm=100.0, key_code=0, energy_lufs=-8.0)
        tf_b = _make_tf(bpm=150.0, key_code=0, energy_lufs=-8.0)
        assert scorer.check_hard_constraints(tf_a, tf_b)
        assert scorer.score_transition(tf_a, tf_b) == 0.0


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

    features_map = {
        feat_a.track_id: feat_a,
        feat_b.track_id: feat_b,
    }
    matrix = await svc._build_transition_matrix_scored(tracks, features_map)

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
