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
from app.utils.audio.loader import load_audio, validate_audio  # noqa: E402

sig = load_audio(P)
validate_audio(sig)
log(f"load_audio DONE (dur={sig.duration_s:.0f}s)")

log("estimate_bpm ...")
from app.utils.audio.bpm import estimate_bpm  # noqa: E402

r = estimate_bpm(sig)
log(f"estimate_bpm DONE bpm={r.bpm:.1f}")

log("detect_key ...")
from app.utils.audio.key_detect import detect_key  # noqa: E402

r = detect_key(sig)
log(f"detect_key DONE key={r.key_code}")

log("measure_loudness ...")
from app.utils.audio.loudness import measure_loudness  # noqa: E402

r = measure_loudness(sig)
log(f"measure_loudness DONE lufs={r.lufs_i:.1f}")

log("compute_band_energies ...")
from app.utils.audio.energy import compute_band_energies  # noqa: E402

r = compute_band_energies(sig)
log("compute_band_energies DONE")

log("extract_spectral_features ...")
from app.utils.audio.spectral import extract_spectral_features  # noqa: E402

r = extract_spectral_features(sig)
log("extract_spectral_features DONE")

log("extract_mfcc ...")
from app.utils.audio.mfcc import extract_mfcc  # noqa: E402

r = extract_mfcc(sig)
log("extract_mfcc DONE")

log("detect_beats ...")
from app.utils.audio.beats import detect_beats  # noqa: E402

r = detect_beats(sig)
log(f"detect_beats DONE beats={len(r.beat_times)}")

log("segment_structure ...")
from app.utils.audio.structure import segment_structure  # noqa: E402

s = segment_structure(sig, beat_times=r.beat_times, track_pulse_clarity=r.pulse_clarity)
log(f"segment_structure DONE sections={len(s)}")

log("ALL STEPS COMPLETED")
_log_file.close()
