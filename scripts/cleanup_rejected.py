#!/usr/bin/env python3
"""Remove rejected tracks from YM playlist, local DB, and disk.

Reads a rejection report JSON and performs 3-phase cleanup:
  Phase 1: Remove from YM playlist via API
  Phase 2: Remove from local DB (dj_playlist_items)
  Phase 3: Delete mp3 files from disk

Dry-run by default — pass --confirm to actually delete.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from app.config import settings

# ── Logging ──────────────────────────────────────────────
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"cleanup_{datetime.now():%Y%m%d_%H%M%S}.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_console, _fh])
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────
YM_USER_ID = "250905515"
YM_PLAYLIST_KIND = 1271
LOCAL_PLAYLIST_ID = 2
AUDIO_DIR = Path(settings.dj_library_path).expanduser().parent / "techno-develop-recs"
YM_BASE = "https://api.music.yandex.net"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cleanup rejected tracks")
    p.add_argument("--confirm", action="store_true", help="Actually delete (dry-run without)")
    p.add_argument("--report", type=Path, help="Path to rejection report JSON")
    p.add_argument("--skip-ym", action="store_true", help="Skip YM phase (local only)")
    return p.parse_args()


def find_latest_report() -> Path:
    """Find the most recent rejection report in AUDIO_DIR."""
    reports = sorted(AUDIO_DIR.glob("rejection_report_*.json"), reverse=True)
    if not reports:
        raise FileNotFoundError(f"No rejection reports in {AUDIO_DIR}")
    return reports[0]


def load_report(path: Path) -> dict:
    """Load and validate the rejection report."""
    data = json.loads(path.read_text())
    ids = data.get("ym_ids_to_delete", [])
    if not ids:
        raise ValueError("Report has no ym_ids_to_delete")
    logger.info("Report: %s (%d IDs to delete)", path.name, len(ids))
    return data


async def main() -> None:
    args = parse_args()
    report_path = args.report or find_latest_report()
    report = load_report(report_path)
    ym_ids = set(report["ym_ids_to_delete"])
    dry = not args.confirm
    mode = "DRY RUN" if dry else "LIVE"
    logger.info("Mode: %s | Log: %s", mode, _log_file)

    # Phase 1: YM playlist
    if not args.skip_ym:
        await phase1_ym_playlist(ym_ids, dry=dry)
    else:
        logger.info("Phase 1 skipped (--skip-ym)")

    # Phase 2: Local DB
    await phase2_local_db(report, dry=dry)

    # Phase 3: MP3 files
    phase3_delete_files(report, dry=dry)

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
