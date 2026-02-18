---
description: Improve an existing DJ set by analyzing and fixing weak transitions
---

# Improve Set

Analyze an existing DJ set's transitions and iteratively improve
the track ordering.

## Parameters

- **set_id**: DJ set ID to improve
- **version_id**: Version to base improvements on
- **feedback**: Optional user feedback about what to fix

## Workflow

1. **Score transitions** — `dj_score_transitions` with set_id and version_id.
   Review each transition's component scores (BPM, harmonic, energy,
   spectral, groove).

2. **Identify weak points** — Look for transitions with total < 0.6.
   Common issues:
   - BPM mismatch (score < 0.5): tracks have incompatible tempos
   - Harmonic clash (score < 0.4): keys don't mix well
   - Energy jump (score < 0.5): too big a change in loudness

3. **Pin good tracks** — Mark tracks with strong transitions as pinned
   in the set items via REST API.

4. **Rebuild set** — `dj_rebuild_set` to regenerate with pinned tracks
   preserved and weak ones replaced by better candidates.

5. **Re-score** — `dj_score_transitions` on the new version.
   Compare average scores between versions.

6. **Iterate** — Repeat steps 3-5 until satisfied.
   Usually 2-3 iterations are enough.

## Score Guide

| Component | Good | Acceptable | Poor |
|-----------|------|-----------|------|
| BPM | > 0.8 | 0.5-0.8 | < 0.5 |
| Harmonic | > 0.7 | 0.4-0.7 | < 0.4 |
| Energy | > 0.6 | 0.3-0.6 | < 0.3 |
| Spectral | > 0.5 | 0.3-0.5 | < 0.3 |
| Groove | > 0.5 | 0.3-0.5 | < 0.3 |
| **Total** | **> 0.7** | **0.5-0.7** | **< 0.5** |
