#!/usr/bin/env python3
"""Subprocess isolation worker for audio analysis.

Runs audio analysis + DB persist for a single track, then writes a
JSON summary line to stdout.  Stdout is reserved for that JSON only —
all logging goes to stderr.

Why subprocess?  Essentia is a C++ library that can crash with SIGBUS /
SIGSEGV on corrupt audio files.  Inside asyncio.to_thread a crash kills
the entire Python process.  Running each track in its own subprocess
means one corrupt file = one failed task, not a dead orchestrator.

Usage:
    python _analyze_worker.py <audio_path> <track_id>

Stdout (exactly one JSON line on success):
    {"status": "ok",       "run_id": …, "bpm": …, "key_code": …, "lufs_i": …, "is_atonal": …}
    {"status": "rejected", "reject_reason": …, "reject_tier": …, "details": {…}}

Exit codes:
    0  — task completed (ok or rejected — check "status" in JSON)
    1  — unexpected error (details on stderr)
    2  — bad arguments
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# ── 1. Logging → stderr BEFORE any other imports ────────────────────────
#    force=True overrides any basicConfig calls from imported modules.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)

# ── 2. Project root on sys.path + cwd (required for .env / app imports) ─
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)


# ── 3. Worker coroutine ─────────────────────────────────────────────────


async def _run(audio_path: str, track_id: int) -> dict:
    """Analyze one track and persist to DB.  Returns JSON-serialisable dict."""

    # Late imports: after path/cwd are set up, and after logging is configured
    # so that any logging from app.* goes to stderr, not stdout.
    from app.database import session_factory
    from app.repositories.audio_features import AudioFeaturesRepository
    from app.repositories.runs import FeatureRunRepository
    from app.repositories.sections import SectionsRepository
    from scripts.analyze_techno_develop_recs import analyze_single_pass

    # ── CPU-heavy analysis (may SIGBUS on corrupt audio) ─────────────────
    result = analyze_single_pass(audio_path, track_id)

    # ── Rejected: no DB write needed ─────────────────────────────────────
    if "reject_reason" in result:
        return {
            "status": "rejected",
            "reject_reason": result["reject_reason"],
            "reject_tier": result["reject_tier"],
            "details": result.get("details", {}),
        }

    # ── Persist to DB ─────────────────────────────────────────────────────
    async with session_factory() as session:
        run_repo = FeatureRunRepository(session)
        features_repo = AudioFeaturesRepository(session)
        sections_repo = SectionsRepository(session)

        run = await run_repo.create(
            pipeline_name="essentia-v1",
            pipeline_version="2.1b6",
            parameters={"full_analysis": True},
            code_ref="essentia-v1@2.1b6",
            status="running",
        )
        await features_repo.save_features(track_id, run.run_id, result["features"])
        for section in result["sections"]:
            await sections_repo.create(
                track_id=track_id,
                run_id=run.run_id,
                start_ms=int(section.start_s * 1000),
                end_ms=int(section.end_s * 1000),
                section_type=section.section_type,
                section_duration_ms=int(section.duration_s * 1000),
                section_energy_mean=section.energy_mean,
                section_energy_max=section.energy_max,
                section_energy_slope=section.energy_slope,
                boundary_confidence=section.boundary_confidence,
                section_centroid_hz=section.centroid_hz,
                section_flux=section.flux,
                section_onset_rate=section.onset_rate,
                section_pulse_clarity=section.pulse_clarity,
            )
        await run_repo.mark_completed(run.run_id)
        await session.commit()

    return {
        "status": "ok",
        "run_id": run.run_id,
        "bpm": round(result["bpm"], 1),
        "key_code": result["key_code"],
        "lufs_i": round(result["lufs_i"], 1),
        "is_atonal": result["is_atonal"],
    }


# ── 4. Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: _analyze_worker.py <audio_path> <track_id>\n")
        sys.exit(2)

    _audio_path = sys.argv[1]
    try:
        _track_id = int(sys.argv[2])
    except ValueError:
        sys.stderr.write(f"track_id must be int, got: {sys.argv[2]!r}\n")
        sys.exit(2)

    try:
        _summary = asyncio.run(_run(_audio_path, _track_id))
        print(json.dumps(_summary))  # stdout — one JSON line
    except Exception as _exc:
        sys.stderr.write(f"[{_track_id}] {type(_exc).__name__}: {_exc}\n")
        sys.exit(1)
