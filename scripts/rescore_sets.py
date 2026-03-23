#!/usr/bin/env python3
"""Re-score all DJ set versions using current TransitionScoringService.

Loads set items for each version, fetches audio features, scores consecutive
pairs, and updates dj_set_versions.score with the average transition quality.

Usage:
    uv run python scripts/rescore_sets.py
    uv run python scripts/rescore_sets.py --set-id 19
    uv run python scripts/rescore_sets.py --version-id 26
    uv run python scripts/rescore_sets.py --dry-run --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# fmt: off
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# fmt: on

from sqlalchemy import text

from app.infrastructure.database import close_db, init_db, session_factory
from app.services.audio.scoring import TrackFeatures, TransitionScoringService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _row_to_track_features(row: dict) -> TrackFeatures:
    """Convert a raw SQL row dict to TrackFeatures for scoring."""
    # Parse MFCC JSON string
    mfcc_vector: list[float] | None = None
    if row.get("mfcc_vector"):
        mfcc_vector = json.loads(row["mfcc_vector"])

    # Band ratios with normalization
    low = row.get("low_energy") or 0.33
    mid = row.get("mid_energy") or 0.33
    high = row.get("high_energy") or 0.34
    total = low + mid + high
    band_ratios = [low / total, mid / total, high / total] if total > 0 else [0.33, 0.33, 0.34]

    return TrackFeatures(
        bpm=row["bpm"],
        energy_lufs=row["lufs_i"],
        key_code=row["key_code"] if row["key_code"] is not None else 0,
        harmonic_density=row.get("chroma_entropy") or row.get("key_confidence") or 0.5,
        centroid_hz=row.get("centroid_mean_hz") or 2000.0,
        band_ratios=band_ratios,
        onset_rate=row.get("onset_rate_mean") or 5.0,
        mfcc_vector=mfcc_vector,
        kick_prominence=row["kick_prominence"] if row.get("kick_prominence") is not None else 0.5,
        hnr_db=row["hnr_mean_db"] if row.get("hnr_mean_db") is not None else 0.0,
        spectral_slope=row["slope_db_per_oct"] if row.get("slope_db_per_oct") is not None else 0.0,
        hp_ratio=row["hp_ratio"] if row.get("hp_ratio") is not None else 0.5,
    )


async def get_versions(set_id: int | None = None, version_id: int | None = None) -> list[dict]:
    """Get set versions to score."""
    async with session_factory() as session:
        where = ""
        params: dict = {}
        if version_id is not None:
            where = "WHERE sv.set_version_id = :vid"
            params["vid"] = version_id
        elif set_id is not None:
            where = "WHERE sv.set_id = :sid"
            params["sid"] = set_id

        result = await session.execute(
            text(f"""
                SELECT sv.set_version_id, sv.set_id, sv.score,
                       s.name as set_name,
                       COUNT(si.set_item_id) as track_count
                FROM dj_set_versions sv
                JOIN dj_sets s ON s.set_id = sv.set_id
                LEFT JOIN dj_set_items si ON si.set_version_id = sv.set_version_id
                {where}
                GROUP BY sv.set_version_id
                ORDER BY sv.set_version_id
            """),
            params,
        )
        return [dict(row._mapping) for row in result.fetchall()]


async def score_version(
    version_id: int, scorer: TransitionScoringService, *, verbose: bool = False
) -> tuple[float | None, list[dict]]:
    """Score a single set version. Returns (avg_score, transition_details)."""
    async with session_factory() as session:
        # Get ordered track IDs
        result = await session.execute(
            text("""
                SELECT si.track_id, si.sort_index
                FROM dj_set_items si
                WHERE si.set_version_id = :vid
                ORDER BY si.sort_index
            """),
            {"vid": version_id},
        )
        items = result.fetchall()

        if len(items) < 2:
            return None, []

        track_ids = [row.track_id for row in items]

        # Build IN clause for SQLite (no tuple binding)
        placeholders = ", ".join(f":t{i}" for i in range(len(track_ids)))
        params = {f"t{i}": tid for i, tid in enumerate(track_ids)}

        # Get latest features per track
        features_result = await session.execute(
            text(f"""
                SELECT f.*
                FROM track_audio_features_computed f
                INNER JOIN (
                    SELECT track_id, MAX(run_id) as max_run_id
                    FROM track_audio_features_computed
                    WHERE track_id IN ({placeholders})
                    GROUP BY track_id
                ) latest ON f.track_id = latest.track_id AND f.run_id = latest.max_run_id
            """),
            params,
        )

        features_map: dict[int, dict] = {}
        for row in features_result.fetchall():
            features_map[row.track_id] = dict(row._mapping)

    # Score consecutive pairs
    transitions = []
    scores = []
    for i in range(len(track_ids) - 1):
        tid_a, tid_b = track_ids[i], track_ids[i + 1]
        if tid_a not in features_map or tid_b not in features_map:
            if verbose:
                logger.warning(
                    "  #%d→#%d: missing features (track %d or %d)", i + 1, i + 2, tid_a, tid_b
                )
            continue

        fa = _row_to_track_features(features_map[tid_a])
        fb = _row_to_track_features(features_map[tid_b])
        score = scorer.score_transition(fa, fb)
        scores.append(score)
        transitions.append(
            {
                "from_idx": i + 1,
                "to_idx": i + 2,
                "from_track_id": tid_a,
                "to_track_id": tid_b,
                "score": score,
            }
        )

    avg = sum(scores) / len(scores) if scores else None
    return avg, transitions


async def update_score(version_id: int, score: float) -> None:
    """Update dj_set_versions.score."""
    async with session_factory() as session:
        await session.execute(
            text("UPDATE dj_set_versions SET score = :score WHERE set_version_id = :vid"),
            {"score": round(score, 4), "vid": version_id},
        )
        await session.commit()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score DJ set versions")
    parser.add_argument("--set-id", type=int, help="Score only this set (all versions)")
    parser.add_argument("--version-id", type=int, help="Score only this version")
    parser.add_argument("--dry-run", action="store_true", help="Show scores without updating DB")
    parser.add_argument("--verbose", action="store_true", help="Print per-transition details")
    args = parser.parse_args()

    await init_db()
    scorer = TransitionScoringService()

    try:
        versions = await get_versions(set_id=args.set_id, version_id=args.version_id)
        if not versions:
            logger.info("No versions found")
            return

        logger.info("Scoring %d version(s)...", len(versions))
        print()

        total_scored = 0
        all_scores: list[float] = []

        for v in versions:
            vid = v["set_version_id"]
            name = v["set_name"]
            track_count = v["track_count"]
            old_score = v["score"]

            avg, transitions = await score_version(vid, scorer, verbose=args.verbose)

            if avg is None:
                logger.warning('  "%s" (v%d): not enough tracks (%d)', name, vid, track_count)
                continue

            scores = [t["score"] for t in transitions]
            min_score = min(scores)
            max_score = max(scores)
            weak = [t for t in transitions if t["score"] < 0.7]

            # Print report
            old_str = f" (was {old_score:.3f})" if old_score is not None else ""
            print(f'Set "{name}" (v{vid}): {track_count} tracks, {len(transitions)} transitions')
            print(f"  Avg: {avg:.3f}  Min: {min_score:.3f}  Max: {max_score:.3f}{old_str}")

            if weak:
                weak_strs = [f"#{t['from_idx']}→#{t['to_idx']} ({t['score']:.3f})" for t in weak]
                print(f"  Weak (< 0.7): {', '.join(weak_strs)}")

            if args.verbose:
                for t in transitions:
                    marker = " !!!" if t["score"] < 0.7 else ""
                    print(f"    #{t['from_idx']}→#{t['to_idx']}: {t['score']:.3f}{marker}")

            if not args.dry_run:
                await update_score(vid, avg)
                print(f"  Updated score = {avg:.4f}")
            else:
                print("  [dry-run] would update score")

            print()
            total_scored += 1
            all_scores.append(avg)

        # Summary
        print("=" * 60)
        if all_scores:
            print(f"Scored: {total_scored} versions, avg {sum(all_scores) / len(all_scores):.3f}")
            print(f"Range:  {min(all_scores):.3f} — {max(all_scores):.3f}")
        else:
            print("No versions could be scored (missing features?)")
        if args.dry_run:
            print("[dry-run mode — no DB updates]")
        print("=" * 60)

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
