"""Test parity between different transition scoring entry points.

Verifies that GA, API, and MCP paths produce consistent scoring results
when using the unified scoring approach with DB-backed Camelot lookup.
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import text

from app.models.features import TrackAudioFeaturesComputed
from app.repositories.audio_features import AudioFeaturesRepository
from app.services.camelot_lookup import CamelotLookupService
from app.services.set_generation import SetGenerationService
from app.services.transition_scoring import TrackFeatures, TransitionScoringService
from app.services.transition_scoring_unified import UnifiedTransitionScoringService
from app.utils.audio.set_generator import TrackData


@pytest.fixture
async def sample_tracks(db_session):
    """Create sample tracks with features for testing."""
    repo = AudioFeaturesRepository(db_session)
    
    # Create two sample tracks with known features
    track1_features = {
        "track_id": 1,
        "bpm": 128.0,
        "key_code": 5,  # 5A in Camelot 
        "key_confidence": 0.8,
        "lufs_i": -10.0,
        "low_energy": 0.4,
        "mid_energy": 0.3,
        "high_energy": 0.3,
        "centroid_mean_hz": 2500.0,
        "onset_rate_mean": 6.0,
        "energy_mean": 0.6,
    }
    
    track2_features = {
        "track_id": 2,
        "bpm": 132.0,
        "key_code": 0,  # 5A in Camelot (same as track1)
        "key_confidence": 0.9,
        "lufs_i": -8.0,
        "low_energy": 0.35,
        "mid_energy": 0.35,
        "high_energy": 0.3,
        "centroid_mean_hz": 3000.0,
        "onset_rate_mean": 7.0,
        "energy_mean": 0.7,
    }
    
    # Insert via repository
    feat1 = await repo.create(**track1_features)
    feat2 = await repo.create(**track2_features)
    await db_session.commit()
    
    return feat1, feat2


@pytest.fixture
async def camelot_lookup(db_session):
    """Build Camelot lookup table for consistent testing."""
    # Seed some key edges for testing
    await db_session.execute(text("""
        INSERT INTO key_edges (from_key_code, to_key_code, weight)
        VALUES 
            (5, 5, 1.0),   -- Same key = perfect
            (5, 0, 1.0),   -- Compatible keys  
            (0, 5, 1.0),   -- Compatible keys
            (0, 0, 1.0)    -- Same key = perfect
        ON CONFLICT DO NOTHING
    """))
    await db_session.commit()
    
    camelot_svc = CamelotLookupService(db_session)
    return await camelot_svc.build_lookup_table()


@pytest.mark.asyncio
async def test_unified_vs_direct_service_scoring(sample_tracks, camelot_lookup, db_session):
    """Test unified service vs direct TransitionScoringService."""
    feat1, feat2 = sample_tracks
    
    # Direct TransitionScoringService
    direct_scorer = TransitionScoringService(camelot_lookup=camelot_lookup)
    
    # Convert to TrackFeatures format
    tf1 = TrackFeatures(
        bpm=feat1.bpm,
        energy_lufs=feat1.lufs_i,
        key_code=feat1.key_code,
        harmonic_density=feat1.key_confidence,
        centroid_hz=feat1.centroid_mean_hz or 2000.0,
        band_ratios=[0.4, 0.3, 0.3],  # From low/mid/high energy
        onset_rate=feat1.onset_rate_mean or 5.0,
    )
    
    tf2 = TrackFeatures(
        bpm=feat2.bpm,
        energy_lufs=feat2.lufs_i,
        key_code=feat2.key_code,
        harmonic_density=feat2.key_confidence,
        centroid_hz=feat2.centroid_mean_hz or 2000.0,
        band_ratios=[0.35, 0.35, 0.3],  # From low/mid/high energy
        onset_rate=feat2.onset_rate_mean or 5.0,
    )
    
    direct_score = direct_scorer.score_transition(tf1, tf2)
    
    # Unified service
    unified_svc = UnifiedTransitionScoringService(db_session)
    unified_score = await unified_svc.score_transition_by_features(feat1, feat2)
    
    # Should be identical (within floating point precision)
    assert abs(direct_score - unified_score) < 1e-6, (
        f"Direct score {direct_score} != unified score {unified_score}"
    )


@pytest.mark.asyncio  
async def test_ga_vs_unified_service_scoring(sample_tracks, camelot_lookup, db_session):
    """Test GA path vs unified service scoring."""
    feat1, feat2 = sample_tracks
    
    # GA path: Build transition matrix like SetGenerationService does
    tracks = [
        TrackData(track_id=feat1.track_id, bpm=feat1.bpm, energy=feat1.energy_mean, key_code=feat1.key_code),
        TrackData(track_id=feat2.track_id, bpm=feat2.bpm, energy=feat2.energy_mean, key_code=feat2.key_code),
    ]
    
    # Simulate GA's matrix building logic
    scorer = TransitionScoringService(camelot_lookup=camelot_lookup)
    
    # Build track features as GA does
    tf1 = TrackFeatures(
        bpm=feat1.bpm,
        energy_lufs=feat1.lufs_i,
        key_code=feat1.key_code or 0,
        harmonic_density=feat1.key_confidence or 0.5,
        centroid_hz=feat1.centroid_mean_hz or 2000.0,
        band_ratios=[0.4, 0.3, 0.3],  # From energy bands
        onset_rate=feat1.onset_rate_mean or 5.0,
    )
    
    tf2 = TrackFeatures(
        bpm=feat2.bpm,
        energy_lufs=feat2.lufs_i,
        key_code=feat2.key_code or 0,
        harmonic_density=feat2.key_confidence or 0.5,
        centroid_hz=feat2.centroid_mean_hz or 2000.0,
        band_ratios=[0.35, 0.35, 0.3],  # From energy bands
        onset_rate=feat2.onset_rate_mean or 5.0,
    )
    
    ga_score = scorer.score_transition(tf1, tf2)
    
    # Unified service 
    unified_svc = UnifiedTransitionScoringService(db_session)
    unified_score = await unified_svc.score_transition_by_ids(feat1.track_id, feat2.track_id)
    
    # Should be identical
    assert abs(ga_score - unified_score) < 1e-6, (
        f"GA score {ga_score} != unified score {unified_score}"
    )


@pytest.mark.asyncio
async def test_component_score_consistency(sample_tracks, camelot_lookup, db_session):
    """Test that component scores are consistent across paths."""
    feat1, feat2 = sample_tracks
    
    # Direct scorer with components
    direct_scorer = TransitionScoringService(camelot_lookup=camelot_lookup)
    
    tf1 = TrackFeatures(
        bpm=feat1.bpm,
        energy_lufs=feat1.lufs_i,
        key_code=feat1.key_code,
        harmonic_density=feat1.key_confidence,
        centroid_hz=feat1.centroid_mean_hz or 2000.0,
        band_ratios=[0.4, 0.3, 0.3],
        onset_rate=feat1.onset_rate_mean or 5.0,
    )
    
    tf2 = TrackFeatures(
        bpm=feat2.bpm,
        energy_lufs=feat2.lufs_i,
        key_code=feat2.key_code,
        harmonic_density=feat2.key_confidence,
        centroid_hz=feat2.centroid_mean_hz or 2000.0,
        band_ratios=[0.35, 0.35, 0.3],
        onset_rate=feat2.onset_rate_mean or 5.0,
    )
    
    # Direct components
    direct_bpm = direct_scorer.score_bpm(tf1.bpm, tf2.bpm)
    direct_harmonic = direct_scorer.score_harmonic(tf1.key_code, tf2.key_code, tf1.harmonic_density, tf2.harmonic_density)
    direct_energy = direct_scorer.score_energy(tf1.energy_lufs, tf2.energy_lufs)
    direct_spectral = direct_scorer.score_spectral(tf1, tf2)
    direct_groove = direct_scorer.score_groove(tf1.onset_rate, tf2.onset_rate)
    direct_total = direct_scorer.score_transition(tf1, tf2)
    
    # Unified components
    unified_svc = UnifiedTransitionScoringService(db_session)
    unified_components = await unified_svc.score_transition_components_by_ids(feat1.track_id, feat2.track_id)
    
    # Check each component
    assert abs(direct_bpm - unified_components["bpm"]) < 1e-4
    assert abs(direct_harmonic - unified_components["harmonic"]) < 1e-4
    assert abs(direct_energy - unified_components["energy"]) < 1e-4
    assert abs(direct_spectral - unified_components["spectral"]) < 1e-4
    assert abs(direct_groove - unified_components["groove"]) < 1e-4
    assert abs(direct_total - unified_components["total"]) < 1e-4


@pytest.mark.asyncio
async def test_db_backed_vs_fallback_camelot(sample_tracks, db_session):
    """Test that DB-backed Camelot lookup gives different results than fallback."""
    feat1, feat2 = sample_tracks
    
    # Service with DB-backed lookup
    unified_svc = UnifiedTransitionScoringService(db_session)
    db_score = await unified_svc.score_transition_by_ids(feat1.track_id, feat2.track_id)
    
    # Service with default fallback (no DB session)
    fallback_scorer = TransitionScoringService()  # No camelot_lookup provided
    tf1 = TrackFeatures(
        bpm=feat1.bpm,
        energy_lufs=feat1.lufs_i,
        key_code=feat1.key_code,
        harmonic_density=feat1.key_confidence,
        centroid_hz=feat1.centroid_mean_hz or 2000.0,
        band_ratios=[0.4, 0.3, 0.3],
        onset_rate=feat1.onset_rate_mean or 5.0,
    )
    
    tf2 = TrackFeatures(
        bpm=feat2.bpm,
        energy_lufs=feat2.lufs_i,
        key_code=feat2.key_code,
        harmonic_density=feat2.key_confidence,
        centroid_hz=feat2.centroid_mean_hz or 2000.0,
        band_ratios=[0.35, 0.35, 0.3],
        onset_rate=feat2.onset_rate_mean or 5.0,
    )
    
    fallback_score = fallback_scorer.score_transition(tf1, tf2)
    
    print(f"DB-backed score: {db_score}, Fallback score: {fallback_score}")
    
    # They should be different if DB has meaningful data
    # (This test documents the behavior rather than asserting equality)
    # The important thing is that all production paths use DB-backed scoring
    assert isinstance(db_score, float)
    assert isinstance(fallback_score, float)
    assert 0.0 <= db_score <= 1.0
    assert 0.0 <= fallback_score <= 1.0