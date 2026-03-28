# Plugin Audio Parity: dj-music-plugin analyzer alignment

> Created: 2026-03-28 | Priority: P0-P2 | Status: In Progress

## Context

Comparative audit of audio analysis between `dj-techno-set-builder` (essentia-based) and `dj-music-plugin` (librosa/numpy-based) revealed significant discrepancies across all feature dimensions. The main project's essentia-based approach is closer to industry standards.

## Discrepancies Found

### P0 — Critical (values incorrect by standard)

| Feature | Main (correct) | Plugin (incorrect) | Impact |
|---------|---------------|-------------------|--------|
| **LUFS** | EBU R128 via essentia `LoudnessEBUR128` (K-weighting + gating) | `20*log10(RMS) - 0.691` (no K-weight, no gate) | 2-4 dB error on techno |
| **True Peak** | 4x polyphase oversampling (`resample_poly`) | Raw `max(abs(samples))` | 0.5-3 dB underestimate |

### P1 — High (wrong scale/normalization)

| Feature | Main | Plugin | Impact |
|---------|------|--------|--------|
| **Spectral Flux** | L2-norm (~0.05-0.3) | Raw `sum(diff²)` (~5000-50000) | Incomparable scales |
| **Key Detection** | essentia `bgate` EDM profile | Krumhansl-Kessler classical | 20-30% more errors on techno |

### P2 — Medium (approximations, fixable)

| Feature | Main | Plugin | Fix |
|---------|------|--------|-----|
| **Chroma Entropy** | Normalized 0-1 (`H / log2(12)`) | Raw 0-3.585 | Add `/ np.log2(12)` |
| **HNR** | Autocorrelation (Boersma) | Spectral flatness proxy | Implement autocorrelation or rename |
| **Energy Bands** | Butterworth bandpass, 6 bands | FFT bin selection, 5 bands | Align boundaries |

### P3 — Low (different but acceptable)

| Feature | Main | Plugin | Note |
|---------|------|--------|------|
| **BPM** | essentia multi-feature ensemble | librosa beat_track | Both acceptable for techno |
| **Kick/HP ratio** | Beat-synced, bandpass RMS | HPSS, spectral percussive | Different metrics entirely |

## Fix Plan (for dj-music-plugin)

1. **LUFS**: Replace numpy approximation with `pyloudnorm` (pure Python EBU R128)
2. **True Peak**: Add `scipy.signal.resample_poly` 4x oversampling
3. **Spectral Flux**: Normalize: `np.linalg.norm(diff) / len(diff)`
4. **Chroma Entropy**: Divide by `np.log2(12)`
5. **HNR**: Implement autocorrelation-based method (20 lines numpy)
6. **Energy Bands**: Align boundary frequencies with main project

## Files to Modify (plugin)

- `app/audio/analyzers/loudness.py` — P0: LUFS + true peak
- `app/audio/analyzers/spectral.py` — P1: flux normalization
- `app/audio/analyzers/key.py` — P1: EDM profiles, P2: chroma entropy, HNR
- `app/audio/analyzers/energy.py` — P2: band boundaries
- `app/audio/analyzers/beat.py` — P3: no changes needed now

## Verification

After fixes, re-analyze 6 identical tracks from both systems and compare values.
Expected: LUFS within ±1 dB, flux on same scale, chroma entropy 0-1.
