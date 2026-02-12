"""Groove similarity via normalized cross-correlation of onset envelopes.

Used for Transition.groove_similarity (0-1).
Higher values indicate more compatible rhythmic patterns.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def groove_similarity(
    env_a: NDArray[np.float32],
    env_b: NDArray[np.float32],
) -> float:
    """Compute groove similarity between two onset envelopes.

    Uses normalized cross-correlation at zero lag, which measures
    how well the rhythmic patterns align beat-for-beat.

    Args:
        env_a: Onset envelope of track A (frame-level, from detect_beats).
        env_b: Onset envelope of track B (frame-level, from detect_beats).

    Returns:
        Similarity score in [0, 1]. 1 = identical groove.
    """
    # Truncate to same length
    min_len = min(len(env_a), len(env_b))
    if min_len == 0:
        return 0.0

    a = env_a[:min_len].astype(np.float64)
    b = env_b[:min_len].astype(np.float64)

    # Zero-mean
    a = a - a.mean()
    b = b - b.mean()

    # Normalized cross-correlation at zero lag
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0

    ncc = float(np.dot(a, b) / (norm_a * norm_b))

    # Clamp to [0, 1] — negative correlation treated as 0
    return float(np.clip(ncc, 0.0, 1.0))
