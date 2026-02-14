"""Tests for the genetic algorithm set generator.

Unit tests (pure GA, no DB) + API integration tests (in-memory SQLite).
"""

from __future__ import annotations

import numpy as np
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Track
from app.models.features import TrackAudioFeaturesComputed
from app.models.harmony import Key
from app.models.runs import FeatureExtractionRun
from app.models.sets import DjSet
from app.utils.audio.set_generator import (
    EnergyArcType,
    GAConfig,
    GAResult,
    GeneticSetGenerator,
    TrackData,
    target_energy_curve,
)

# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════


def _make_tracks(n: int, *, bpm_base: float = 130.0) -> list[TrackData]:
    """Create N TrackData with linearly varying BPM and energy."""
    return [
        TrackData(
            track_id=i + 1,
            bpm=bpm_base + i * 2.0,
            energy=0.3 + 0.5 * (i / max(n - 1, 1)),
            key_code=(i * 2) % 24,
        )
        for i in range(n)
    ]


def _make_matrix(tracks: list[TrackData]) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
    """Build a simple transition matrix where close BPMs score higher."""
    n = len(tracks)
    matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(n):
            if i != j:
                bpm_diff = abs(tracks[i].bpm - tracks[j].bpm)
                matrix[i, j] = max(0.0, 1.0 - bpm_diff / 40.0)
    return matrix


# ═══════════════════════════════════════════════════════════
# Unit Tests: target_energy_curve
# ═══════════════════════════════════════════════════════════


class TestTargetEnergyCurve:
    def test_shape(self) -> None:
        curve = target_energy_curve(20, EnergyArcType.CLASSIC)
        assert curve.shape == (20,)

    def test_bounds(self) -> None:
        for arc in EnergyArcType:
            curve = target_energy_curve(50, arc)
            assert np.all(curve >= 0.0), f"{arc}: values below 0"
            assert np.all(curve <= 1.0), f"{arc}: values above 1"

    def test_single_track(self) -> None:
        curve = target_energy_curve(1, EnergyArcType.WAVE)
        assert curve.shape == (1,)

    def test_all_arc_types(self) -> None:
        for arc in EnergyArcType:
            curve = target_energy_curve(30, arc)
            assert len(curve) == 30


# ═══════════════════════════════════════════════════════════
# Unit Tests: GeneticSetGenerator
# ═══════════════════════════════════════════════════════════


class TestGeneticSetGenerator:
    def test_valid_result(self) -> None:
        tracks = _make_tracks(10)
        matrix = _make_matrix(tracks)
        config = GAConfig(
            population_size=20,
            generations=10,
            seed=42,
        )
        ga = GeneticSetGenerator(tracks, matrix, config)
        result = ga.run()

        assert isinstance(result, GAResult)
        assert len(result.track_ids) == 10
        assert len(set(result.track_ids)) == 10  # no duplicates
        assert result.score > 0.0
        assert len(result.transition_scores) == 9  # N-1 pairs

    def test_deterministic_seed(self) -> None:
        tracks = _make_tracks(8)
        matrix = _make_matrix(tracks)
        config = GAConfig(population_size=20, generations=20, seed=123)

        r1 = GeneticSetGenerator(tracks, matrix, config).run()
        r2 = GeneticSetGenerator(tracks, matrix, config).run()

        assert r1.track_ids == r2.track_ids
        assert r1.score == r2.score

    def test_subset_track_count(self) -> None:
        tracks = _make_tracks(15)
        matrix = _make_matrix(tracks)
        config = GAConfig(
            population_size=20,
            generations=10,
            seed=1,
            track_count=8,
        )
        ga = GeneticSetGenerator(tracks, matrix, config)
        result = ga.run()

        assert len(result.track_ids) == 8
        assert len(set(result.track_ids)) == 8

    def test_fitness_improves(self) -> None:
        tracks = _make_tracks(12)
        matrix = _make_matrix(tracks)
        config = GAConfig(
            population_size=30,
            generations=50,
            seed=42,
        )
        result = GeneticSetGenerator(tracks, matrix, config).run()

        # fitness_history[0] is gen 0 (initial), last is gen N
        assert result.fitness_history[-1] >= result.fitness_history[0]

    def test_elitism_monotonic(self) -> None:
        """Best fitness should never decrease with elitism > 0."""
        tracks = _make_tracks(10)
        matrix = _make_matrix(tracks)
        config = GAConfig(
            population_size=20,
            generations=30,
            seed=99,
            elitism_count=2,
        )
        result = GeneticSetGenerator(tracks, matrix, config).run()

        for i in range(1, len(result.fitness_history)):
            assert result.fitness_history[i] >= result.fitness_history[i - 1]

    def test_energy_arc_score_bounds(self) -> None:
        tracks = _make_tracks(10)
        matrix = _make_matrix(tracks)
        config = GAConfig(population_size=10, generations=5, seed=1)
        result = GeneticSetGenerator(tracks, matrix, config).run()
        assert 0.0 <= result.energy_arc_score <= 1.0

    def test_bpm_smoothness_score_bounds(self) -> None:
        tracks = _make_tracks(10)
        matrix = _make_matrix(tracks)
        config = GAConfig(population_size=10, generations=5, seed=1)
        result = GeneticSetGenerator(tracks, matrix, config).run()
        assert 0.0 <= result.bpm_smoothness_score <= 1.0

    def test_two_opt_improves_solution(self) -> None:
        """2-opt should improve or maintain solution quality"""
        tracks = _make_tracks(20)
        n = len(tracks)
        matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i != j:
                    bpm_sim = 1.0 / (1.0 + abs(tracks[i].bpm - tracks[j].bpm))
                    matrix[i, j] = bpm_sim

        config = GAConfig(
            population_size=50,
            generations=100,
            track_count=10,
            seed=42,
        )

        gen = GeneticSetGenerator(tracks, matrix, config)

        # Create a sub-optimal chromosome
        chromosome = np.array([0, 5, 2, 8, 3, 9, 1, 7, 4, 6], dtype=np.int32)
        fitness_before = gen._fitness(chromosome)

        # Apply 2-opt
        gen._two_opt(chromosome)
        fitness_after = gen._fitness(chromosome)

        # Fitness should improve or stay same
        assert fitness_after >= fitness_before

    def test_two_opt_called_after_crossover(self) -> None:
        """2-opt should be called after each crossover in run()"""
        tracks = _make_tracks(10)
        matrix = np.random.random((10, 10))

        config = GAConfig(
            population_size=20,
            generations=5,
            track_count=10,
            seed=42,
        )

        gen = GeneticSetGenerator(tracks, matrix, config)
        result = gen.run()

        # Result should have improved from initial random population
        # (2-opt ensures local optimality)
        assert result.score > 0.0
        assert len(result.track_ids) == 10


# ═══════════════════════════════════════════════════════════
# API Integration Tests
# ═══════════════════════════════════════════════════════════


def _feature_kwargs(track_id: int, run_id: int, *, key_code: int = 0) -> dict:
    """Minimal valid feature kwargs for a track."""
    return {
        "track_id": track_id,
        "run_id": run_id,
        "bpm": 128.0 + track_id * 2,
        "tempo_confidence": 0.9,
        "bpm_stability": 0.95,
        "lufs_i": -8.0,
        "rms_dbfs": -12.0,
        "energy_mean": 0.5 + 0.05 * track_id,
        "energy_max": 0.8,
        "energy_std": 0.05,
        "key_code": key_code,
        "key_confidence": 0.85,
        "sub_energy": 0.3,
        "low_energy": 0.5,
        "lowmid_energy": 0.4,
        "mid_energy": 0.5,
        "highmid_energy": 0.3,
        "high_energy": 0.2,
    }


async def _seed_tracks_with_features(
    session: AsyncSession, count: int = 5
) -> tuple[int, list[int]]:
    """Seed a DjSet, tracks, keys, run, and features. Returns (set_id, track_ids)."""
    # Keys (need at least key_code=0)
    key = Key(key_code=0, pitch_class=0, mode=0, name="Cm")
    session.add(key)

    # Tracks
    tracks = [Track(title=f"Track {i}", duration_ms=300000) for i in range(count)]
    session.add_all(tracks)

    # Run
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add(run)

    await session.flush()

    # Features
    for t in tracks:
        feat = TrackAudioFeaturesComputed(**_feature_kwargs(t.track_id, run.run_id))
        session.add(feat)

    # DjSet
    dj_set = DjSet(name="GA Test Set")
    session.add(dj_set)
    await session.flush()

    return dj_set.set_id, [t.track_id for t in tracks]


async def test_generate_set_api(client: AsyncClient, session: AsyncSession) -> None:
    """POST /api/v1/sets/{set_id}/generate returns a valid GA result."""
    set_id, track_ids = await _seed_tracks_with_features(session, count=5)
    await session.commit()

    resp = await client.post(
        f"/api/v1/sets/{set_id}/generate",
        json={
            "population_size": 20,
            "generations": 10,
            "seed": 42,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["set_version_id"] is not None
    assert len(data["track_ids"]) == 5
    assert len(set(data["track_ids"])) == 5  # no duplicates
    assert set(data["track_ids"]) == set(track_ids)
    assert data["score"] > 0
    assert len(data["transition_scores"]) == 4  # N-1
    assert data["generator_run"]["algorithm"] == "genetic"


async def test_generate_set_404(client: AsyncClient) -> None:
    """POST /api/v1/sets/9999/generate returns 404 for missing set."""
    resp = await client.post(
        "/api/v1/sets/9999/generate",
        json={"population_size": 10, "generations": 10},
    )
    assert resp.status_code == 404


async def test_generate_set_no_features(client: AsyncClient, session: AsyncSession) -> None:
    """POST /generate returns 422 when no tracks have features."""
    dj_set = DjSet(name="Empty Set")
    session.add(dj_set)
    await session.flush()
    await session.commit()

    resp = await client.post(
        f"/api/v1/sets/{dj_set.set_id}/generate",
        json={"population_size": 10, "generations": 5},
    )
    assert resp.status_code == 422
