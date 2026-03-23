from __future__ import annotations

import numpy as np

from app.domain.audio.dsp.groove import groove_similarity


class TestGrooveSimilarity:
    def test_identical_envelopes_max_similarity(self) -> None:
        env = np.array([0.1, 0.5, 0.2, 0.8, 0.1, 0.5, 0.2, 0.8], dtype=np.float32)
        score = groove_similarity(env, env)
        assert score > 0.95

    def test_opposite_envelopes_low_similarity(self) -> None:
        env_a = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0], dtype=np.float32)
        env_b = np.array([0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0], dtype=np.float32)
        score = groove_similarity(env_a, env_b)
        assert score < 0.5

    def test_result_between_0_and_1(self) -> None:
        rng = np.random.default_rng(42)
        env_a = rng.random(1000).astype(np.float32)
        env_b = rng.random(1000).astype(np.float32)
        score = groove_similarity(env_a, env_b)
        assert 0.0 <= score <= 1.0

    def test_symmetric(self) -> None:
        rng = np.random.default_rng(42)
        env_a = rng.random(500).astype(np.float32)
        env_b = rng.random(500).astype(np.float32)
        assert abs(groove_similarity(env_a, env_b) - groove_similarity(env_b, env_a)) < 1e-6

    def test_different_lengths_handled(self) -> None:
        env_a = np.ones(100, dtype=np.float32)
        env_b = np.ones(150, dtype=np.float32)
        score = groove_similarity(env_a, env_b)
        assert 0.0 <= score <= 1.0

    def test_silent_envelope_returns_zero(self) -> None:
        env_a = np.zeros(100, dtype=np.float32)
        env_b = np.ones(100, dtype=np.float32)
        score = groove_similarity(env_a, env_b)
        assert score == 0.0

    def test_similar_patterns_high_score(self) -> None:
        """Two slightly different 4/4 patterns should have high similarity."""
        pattern = np.tile([1.0, 0.0, 0.5, 0.0], 25).astype(np.float32)
        rng = np.random.default_rng(42)
        noisy = pattern + rng.normal(0, 0.1, len(pattern)).astype(np.float32)
        score = groove_similarity(pattern, np.clip(noisy, 0, 2).astype(np.float32))
        assert score > 0.7
