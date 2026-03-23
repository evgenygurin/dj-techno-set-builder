#!/usr/bin/env python3
"""Diagnose which analysis step hangs.

Loads audio ONCE, then runs each step with a printed timestamp.
Whichever step doesn't print "done" is the one that hangs.
Writes to scripts/diagnose.log in real-time.
"""

import time
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG = LOGS_DIR / "diagnose.log"
P = (
    "/Users/laptop/Library/Mobile Documents/com~apple~CloudDocs/"
    "dj-techno-set-builder/techno-develop-recs/323_mantra.mp3"
)

_log_file = LOG.open("w")


def log(msg: str) -> None:
    line = f"[{time.monotonic():.1f}] {msg}"
    print(line, flush=True)
    _log_file.write(line + "\n")
    _log_file.flush()


log("load_audio ...")
from app.domain.audio.dsp.loader import load_audio, validate_audio

sig = load_audio(P)
validate_audio(sig)
log(f"load_audio DONE (dur={sig.duration_s:.0f}s)")

log("estimate_bpm ...")
from app.domain.audio.dsp.bpm import estimate_bpm

r = estimate_bpm(sig)
log(f"estimate_bpm DONE bpm={r.bpm:.1f}")

log("detect_key ...")
from app.domain.audio.dsp.key_detect import detect_key

r = detect_key(sig)
log(f"detect_key DONE key={r.key_code}")

log("measure_loudness ...")
from app.domain.audio.dsp.loudness import measure_loudness

r = measure_loudness(sig)
log(f"measure_loudness DONE lufs={r.lufs_i:.1f}")

log("compute_band_energies ...")
from app.domain.audio.dsp.energy import compute_band_energies

r = compute_band_energies(sig)
log("compute_band_energies DONE")

log("extract_spectral_features ...")
from app.domain.audio.dsp.spectral import extract_spectral_features

r = extract_spectral_features(sig)
log("extract_spectral_features DONE")

log("extract_mfcc ...")
from app.domain.audio.dsp.mfcc import extract_mfcc

r = extract_mfcc(sig)
log("extract_mfcc DONE")

log("detect_beats ...")
from app.domain.audio.dsp.beats import detect_beats

r = detect_beats(sig)
log(f"detect_beats DONE beats={len(r.beat_times)}")

log("segment_structure ...")
from app.domain.audio.dsp.structure import segment_structure

s = segment_structure(sig, beat_times=r.beat_times, track_pulse_clarity=r.pulse_clarity)
log(f"segment_structure DONE sections={len(s)}")

log("ALL STEPS COMPLETED")
_log_file.close()
