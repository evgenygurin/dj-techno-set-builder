#!/usr/bin/env python3
"""Analyze quality of subgenre playlist classifications.

Reads all tracks from subgenre playlists (dj_playlists 9-23), re-classifies
each track using the current mood_classifier, and produces a quality report:

  - Per-playlist accuracy, feature stats, confidence distribution
  - Confusion matrix (assigned vs predicted)
  - Borderline tracks (low margin between top-2 scores)
  - "Fugitives" — tracks that clearly belong to another subgenre
  - Driving dominance analysis
  - Overall health score

Usage:
    uv run python scripts/analyze_subgenre_quality.py
    uv run python scripts/analyze_subgenre_quality.py --top-fugitives 10
    uv run python scripts/analyze_subgenre_quality.py --playlist driving
    uv run python scripts/analyze_subgenre_quality.py --json  # machine-readable output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, stdev

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import close_db, init_db, session_factory
from app.models.catalog import Track
from app.models.dj import DjPlaylistItem
from app.models.features import TrackAudioFeaturesComputed
from app.utils.audio.mood_classifier import (
    MoodClassification,
    TrackMood,
    classify_track,
)

# ── ANSI colors ─────────────────────────────────────────────────────────────

C = "\033[0m"
B = "\033[1m"
D = "\033[2m"
G = "\033[32m"
R = "\033[31m"
Y = "\033[33m"
CY = "\033[36m"
M = "\033[35m"
W = "\033[37m"
BG_G = "\033[42;30m"
BG_R = "\033[41;37m"
BG_Y = "\033[43;30m"

# Subgenre playlist IDs (9-23)
SUBGENRE_MAP_PATH = Path(__file__).with_name(".subgenre_playlists.json")


# ── Data structures ─────────────────────────────────────────────────────────


@dataclass
class TrackAnalysis:
    """Result of re-classifying a single track."""

    track_id: int
    title: str
    assigned_mood: str  # playlist it's in
    predicted_mood: str  # what classifier says
    confidence: float
    margin: float  # score[top1] - score[top2]
    top_scores: dict[str, float]  # all 15 scores
    features: dict[str, float]  # raw audio features
    is_correct: bool


@dataclass
class PlaylistStats:
    """Aggregated stats for one subgenre playlist."""

    name: str
    mood: str
    track_count: int = 0
    correct_count: int = 0
    accuracy: float = 0.0
    mean_confidence: float = 0.0
    median_confidence: float = 0.0
    low_confidence_count: int = 0  # confidence < 0.15
    # Feature distributions
    bpm_range: tuple[float, float] = (0.0, 0.0)
    bpm_mean: float = 0.0
    lufs_range: tuple[float, float] = (0.0, 0.0)
    lufs_mean: float = 0.0
    # Where misclassified tracks go
    leak_to: dict[str, int] = field(default_factory=dict)
    # Where incoming misclassified tracks come from
    leak_from: dict[str, int] = field(default_factory=dict)
    # Fugitives: tracks with biggest score gap (assigned << predicted)
    fugitives: list[TrackAnalysis] = field(default_factory=list)


# ── Classification helper ───────────────────────────────────────────────────


def classify_from_features(
    feat: TrackAudioFeaturesComputed,
) -> tuple[MoodClassification, dict[str, float], dict[str, float]]:
    """Classify track from DB features, return classification + all scores."""
    kwargs = dict(
        bpm=feat.bpm,
        lufs_i=feat.lufs_i,
        kick_prominence=feat.kick_prominence or 0.5,
        spectral_centroid_mean=feat.centroid_mean_hz or 2500.0,
        onset_rate=feat.onset_rate_mean or 5.0,
        hp_ratio=feat.hp_ratio or 2.0,
        flux_mean=feat.flux_mean or 0.18,
        flux_std=feat.flux_std or 0.12,
        energy_std=feat.energy_std or 0.15,
        energy_mean=feat.energy_mean or 0.22,
        lra_lu=feat.lra_lu or 6.6,
        crest_factor_db=feat.crest_factor_db or 10.0,
        flatness_mean=feat.flatness_mean or 0.06,
    )
    mc = classify_track(**kwargs)

    # Re-compute all 15 scores for the confusion matrix
    # We need to call individual scorers — import them
    from app.utils.audio.mood_classifier import (
        _score_acid,
        _score_ambient_dub,
        _score_breakbeat,
        _score_detroit,
        _score_driving,
        _score_dub_techno,
        _score_hard_techno,
        _score_hypnotic,
        _score_industrial,
        _score_melodic_deep,
        _score_minimal,
        _score_peak_time,
        _score_progressive,
        _score_raw,
        _score_tribal,
    )

    all_scores = {
        "ambient_dub": _score_ambient_dub(
            kwargs["bpm"], kwargs["lufs_i"], kwargs["spectral_centroid_mean"],
            kwargs["onset_rate"], kwargs["lra_lu"], kwargs["energy_mean"],
            kwargs["hp_ratio"],
        ),
        "dub_techno": _score_dub_techno(
            kwargs["bpm"], kwargs["lufs_i"], kwargs["lra_lu"],
            kwargs["spectral_centroid_mean"], kwargs["onset_rate"], kwargs["hp_ratio"],
        ),
        "minimal": _score_minimal(
            kwargs["bpm"], kwargs["onset_rate"], kwargs["energy_std"],
            kwargs["flux_mean"], kwargs["kick_prominence"], kwargs["lufs_i"],
        ),
        "detroit": _score_detroit(
            kwargs["bpm"], kwargs["hp_ratio"], kwargs["spectral_centroid_mean"],
            kwargs["lufs_i"], kwargs["kick_prominence"], kwargs["energy_mean"],
        ),
        "melodic_deep": _score_melodic_deep(
            kwargs["hp_ratio"], kwargs["spectral_centroid_mean"],
            kwargs["bpm"], kwargs["lufs_i"], kwargs["kick_prominence"],
            kwargs["energy_mean"],
        ),
        "progressive": _score_progressive(
            kwargs["bpm"], kwargs["energy_std"], kwargs["flux_mean"],
            kwargs["lra_lu"], kwargs["hp_ratio"],
        ),
        "hypnotic": _score_hypnotic(
            kwargs["bpm"], kwargs["flux_std"], kwargs["energy_std"],
            kwargs["kick_prominence"], kwargs["flux_mean"],
        ),
        "driving": _score_driving(
            kwargs["bpm"], kwargs["lufs_i"], kwargs["kick_prominence"],
            kwargs["energy_mean"], kwargs["onset_rate"],
            hp_ratio=kwargs["hp_ratio"], flux_std=kwargs["flux_std"],
            centroid_mean_hz=kwargs["spectral_centroid_mean"],
            flatness_mean=kwargs["flatness_mean"],
            lra_lu=kwargs["lra_lu"],
        ),
        "tribal": _score_tribal(
            kwargs["bpm"], kwargs["onset_rate"], kwargs["kick_prominence"],
            kwargs["lufs_i"], kwargs["hp_ratio"],
        ),
        "breakbeat": _score_breakbeat(
            kwargs["kick_prominence"], kwargs["onset_rate"],
            kwargs["bpm"], kwargs["energy_mean"], kwargs["hp_ratio"],
        ),
        "peak_time": _score_peak_time(
            kwargs["kick_prominence"], kwargs["lufs_i"],
            kwargs["energy_mean"], kwargs["bpm"], kwargs["onset_rate"],
        ),
        "acid": _score_acid(
            kwargs["bpm"], kwargs["flux_mean"], kwargs["flux_std"],
            kwargs["spectral_centroid_mean"], kwargs["hp_ratio"],
        ),
        "raw": _score_raw(
            kwargs["kick_prominence"], kwargs["lufs_i"],
            kwargs["crest_factor_db"], kwargs["bpm"], kwargs["energy_mean"],
        ),
        "industrial": _score_industrial(
            kwargs["spectral_centroid_mean"], kwargs["onset_rate"],
            kwargs["flatness_mean"], kwargs["bpm"], kwargs["lufs_i"],
            kwargs["flux_mean"],
        ),
        "hard_techno": _score_hard_techno(
            kwargs["bpm"], kwargs["kick_prominence"],
            kwargs["lufs_i"], kwargs["energy_mean"], kwargs["onset_rate"],
        ),
    }

    raw_features = {
        "bpm": kwargs["bpm"],
        "lufs_i": kwargs["lufs_i"],
        "kick": kwargs["kick_prominence"],
        "centroid": kwargs["spectral_centroid_mean"],
        "onset": kwargs["onset_rate"],
        "hp_ratio": kwargs["hp_ratio"],
        "flux_m": kwargs["flux_mean"],
        "flux_s": kwargs["flux_std"],
        "e_std": kwargs["energy_std"],
        "e_mean": kwargs["energy_mean"],
        "lra": kwargs["lra_lu"],
        "crest": kwargs["crest_factor_db"],
        "flat": kwargs["flatness_mean"],
    }

    return mc, all_scores, raw_features


# ── Data loading ────────────────────────────────────────────────────────────


async def load_subgenre_map() -> dict[str, dict]:
    """Load subgenre playlist mapping from JSON."""
    if not SUBGENRE_MAP_PATH.exists():
        print(f"{R}ERROR: {SUBGENRE_MAP_PATH} not found{C}", file=sys.stderr)
        sys.exit(1)
    with open(SUBGENRE_MAP_PATH) as f:
        return json.load(f)


async def load_playlist_tracks(
    playlist_id: int, mood_name: str
) -> list[TrackAnalysis]:
    """Load tracks from a playlist, classify each, return analyses."""
    results = []

    async with session_factory() as session:
        # Get tracks in this playlist with their features
        stmt = (
            select(
                DjPlaylistItem.track_id,
                Track.title,
                TrackAudioFeaturesComputed,
            )
            .join(Track, Track.track_id == DjPlaylistItem.track_id)
            .join(
                TrackAudioFeaturesComputed,
                TrackAudioFeaturesComputed.track_id == DjPlaylistItem.track_id,
            )
            .where(DjPlaylistItem.playlist_id == playlist_id)
        )
        rows = (await session.execute(stmt)).all()

        for track_id, title, feat in rows:
            mc, all_scores, raw_features = classify_from_features(feat)

            sorted_scores = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
            top1_score = sorted_scores[0][1]
            top2_score = sorted_scores[1][1]
            margin = top1_score - top2_score if top1_score > 0 else 0.0

            results.append(
                TrackAnalysis(
                    track_id=track_id,
                    title=title or f"track_{track_id}",
                    assigned_mood=mood_name,
                    predicted_mood=mc.mood.value,
                    confidence=mc.confidence,
                    margin=margin,
                    top_scores=all_scores,
                    features=raw_features,
                    is_correct=(mc.mood.value == mood_name),
                )
            )

    return results


# ── Analysis ────────────────────────────────────────────────────────────────


def compute_playlist_stats(
    mood: str, name: str, tracks: list[TrackAnalysis], top_n: int = 5
) -> PlaylistStats:
    """Compute stats for one playlist."""
    stats = PlaylistStats(name=name, mood=mood, track_count=len(tracks))

    if not tracks:
        return stats

    correct = [t for t in tracks if t.is_correct]
    stats.correct_count = len(correct)
    stats.accuracy = len(correct) / len(tracks) if tracks else 0.0

    confidences = [t.confidence for t in tracks]
    stats.mean_confidence = mean(confidences)
    stats.median_confidence = median(confidences)
    stats.low_confidence_count = sum(1 for c in confidences if c < 0.15)

    bpms = [t.features["bpm"] for t in tracks]
    stats.bpm_range = (min(bpms), max(bpms))
    stats.bpm_mean = mean(bpms)

    lufs = [t.features["lufs_i"] for t in tracks]
    stats.lufs_range = (min(lufs), max(lufs))
    stats.lufs_mean = mean(lufs)

    # Leaks: where misclassified tracks go
    for t in tracks:
        if not t.is_correct:
            stats.leak_to[t.predicted_mood] = stats.leak_to.get(t.predicted_mood, 0) + 1

    # Top fugitives: tracks with biggest assigned-vs-predicted score gap
    fugitives = sorted(
        [t for t in tracks if not t.is_correct],
        key=lambda t: t.top_scores.get(t.predicted_mood, 0) - t.top_scores.get(t.assigned_mood, 0),
        reverse=True,
    )
    stats.fugitives = fugitives[:top_n]

    return stats


def build_confusion_matrix(
    all_tracks: list[TrackAnalysis],
) -> dict[str, dict[str, int]]:
    """Build confusion matrix: assigned (rows) vs predicted (cols)."""
    moods = [m.value for m in TrackMood.energy_order()]
    matrix: dict[str, dict[str, int]] = {m: {n: 0 for n in moods} for m in moods}
    for t in all_tracks:
        if t.assigned_mood in matrix and t.predicted_mood in matrix[t.assigned_mood]:
            matrix[t.assigned_mood][t.predicted_mood] += 1
    return matrix


# ── Output formatting ───────────────────────────────────────────────────────


def _bar(value: float, width: int = 20, char: str = "█") -> str:
    """Render a horizontal bar."""
    filled = int(value * width)
    return char * filled + "░" * (width - filled)


def _color_pct(pct: float) -> str:
    """Color a percentage green/yellow/red."""
    if pct >= 0.8:
        return f"{G}{pct:.0%}{C}"
    if pct >= 0.5:
        return f"{Y}{pct:.0%}{C}"
    return f"{R}{pct:.0%}{C}"


def print_header(title: str) -> None:
    print(f"\n{B}{'═' * 70}{C}")
    print(f"{B}  {title}{C}")
    print(f"{B}{'═' * 70}{C}")


def print_playlist_report(stats: PlaylistStats) -> None:
    """Print detailed report for one playlist."""
    acc_bar = _bar(stats.accuracy)
    acc_color = _color_pct(stats.accuracy)

    print(f"\n{B}{CY}▸ {stats.name}{C}  ({stats.mood})")
    print(f"  Tracks: {B}{stats.track_count}{C}  "
          f"Correct: {G}{stats.correct_count}{C}  "
          f"Accuracy: {acc_color}  {acc_bar}")
    print(f"  Confidence: mean={stats.mean_confidence:.3f}  "
          f"median={stats.median_confidence:.3f}  "
          f"low(<0.15): {stats.low_confidence_count}")

    if stats.track_count > 0:
        print(f"  BPM: {stats.bpm_range[0]:.1f}-{stats.bpm_range[1]:.1f} "
              f"(mean {stats.bpm_mean:.1f})  "
              f"LUFS: {stats.lufs_range[0]:.1f} to {stats.lufs_range[1]:.1f} "
              f"(mean {stats.lufs_mean:.1f})")

    if stats.leak_to:
        leaks = sorted(stats.leak_to.items(), key=lambda x: x[1], reverse=True)[:5]
        leak_str = ", ".join(f"{m}: {n}" for m, n in leaks)
        print(f"  {Y}Leaks to:{C} {leak_str}")

    if stats.fugitives:
        print(f"  {R}Top fugitives:{C}")
        for t in stats.fugitives[:3]:
            assigned_score = t.top_scores.get(t.assigned_mood, 0)
            predicted_score = t.top_scores.get(t.predicted_mood, 0)
            gap = predicted_score - assigned_score
            print(f"    {D}#{t.track_id}{C} {t.title[:40]:<40s}  "
                  f"{t.assigned_mood}={assigned_score:.3f} → "
                  f"{B}{t.predicted_mood}={predicted_score:.3f}{C}  "
                  f"(gap +{gap:.3f})")


def print_confusion_matrix(matrix: dict[str, dict[str, int]]) -> None:
    """Print compact confusion matrix."""
    print_header("CONFUSION MATRIX (assigned → predicted)")

    moods = list(matrix.keys())
    # Abbreviations for column headers
    abbrevs = {
        "ambient_dub": "AmD", "dub_techno": "DuT", "minimal": "Min",
        "detroit": "Det", "melodic_deep": "MeD", "progressive": "Pro",
        "hypnotic": "Hyp", "driving": "Drv", "tribal": "Tri",
        "breakbeat": "Brk", "peak_time": "PkT", "acid": "Acd",
        "raw": "Raw", "industrial": "Ind", "hard_techno": "HdT",
    }

    # Header row
    header = f"{'':>12s}"
    for m in moods:
        header += f" {abbrevs.get(m, m[:3]):>4s}"
    header += f" {'Total':>5s} {'Acc':>5s}"
    print(f"\n{D}{header}{C}")

    for row_mood in moods:
        row_data = matrix[row_mood]
        total = sum(row_data.values())
        correct = row_data.get(row_mood, 0)
        acc = correct / total if total > 0 else 0.0

        row_str = f"  {abbrevs.get(row_mood, row_mood[:3]):>10s}"
        for col_mood in moods:
            val = row_data[col_mood]
            if val == 0:
                row_str += f" {D}   ·{C}"
            elif col_mood == row_mood:
                row_str += f" {G}{val:>4d}{C}"
            else:
                row_str += f" {Y}{val:>4d}{C}"
        row_str += f" {total:>5d} {_color_pct(acc):>5s}"
        print(row_str)


def print_overall_summary(
    all_stats: list[PlaylistStats], all_tracks: list[TrackAnalysis]
) -> None:
    """Print overall quality summary."""
    print_header("OVERALL QUALITY SUMMARY")

    total_tracks = len(all_tracks)
    total_correct = sum(1 for t in all_tracks if t.is_correct)
    overall_acc = total_correct / total_tracks if total_tracks else 0.0

    print(f"\n  Total tracks analyzed: {B}{total_tracks}{C}")
    print(f"  Overall accuracy:     {_color_pct(overall_acc)} "
          f"({total_correct}/{total_tracks})")

    # Driving dominance
    driving_stats = next((s for s in all_stats if s.mood == "driving"), None)
    if driving_stats and total_tracks > 0:
        driving_pct = driving_stats.track_count / total_tracks
        print(f"  Driving share:        {driving_pct:.1%} "
              f"({driving_stats.track_count}/{total_tracks})")

    # Empty playlists
    empty = [s for s in all_stats if s.track_count == 0]
    if empty:
        print(f"  {R}Empty playlists:{C}      {', '.join(s.mood for s in empty)}")

    # Sparse playlists (<5 tracks)
    sparse = [s for s in all_stats if 0 < s.track_count < 5]
    if sparse:
        print(f"  {Y}Sparse playlists:{C}     "
              + ", ".join(f"{s.mood}({s.track_count})" for s in sparse))

    # Confidence distribution
    confs = [t.confidence for t in all_tracks]
    if confs:
        print("\n  Confidence distribution:")
        print(f"    mean={mean(confs):.3f}  median={median(confs):.3f}  "
              f"stdev={stdev(confs):.3f}" if len(confs) > 1 else
              f"    mean={mean(confs):.3f}")
        buckets = [0, 0.05, 0.10, 0.15, 0.25, 0.50, 1.01]
        for i in range(len(buckets) - 1):
            lo, hi = buckets[i], buckets[i + 1]
            cnt = sum(1 for c in confs if lo <= c < hi)
            pct = cnt / len(confs)
            label = f"[{lo:.2f}, {hi:.2f})" if hi <= 1.0 else f"[{lo:.2f}, 1.00]"
            bar = _bar(pct, width=30)
            print(f"    {label:>14s}  {cnt:>4d} ({pct:>5.1%})  {bar}")

    # Per-playlist accuracy ranking
    print(f"\n  {B}Playlist accuracy ranking:{C}")
    ranked = sorted(all_stats, key=lambda s: s.accuracy, reverse=True)
    for s in ranked:
        if s.track_count > 0:
            bar = _bar(s.accuracy, width=15)
            print(f"    {s.mood:>15s}  {_color_pct(s.accuracy):>5s}  "
                  f"{bar}  ({s.correct_count}/{s.track_count})")
        else:
            print(f"    {s.mood:>15s}  {D}empty{C}")

    # Health score: weighted combination
    # 50% accuracy + 20% coverage (non-empty) + 15% confidence + 15% balance
    coverage = sum(1 for s in all_stats if s.track_count > 0) / len(all_stats)
    avg_conf = mean(confs) if confs else 0.0
    # Balance: entropy-like measure (1 = perfectly even, 0 = all in one)
    counts = [s.track_count for s in all_stats]
    if total_tracks > 0 and len(counts) > 1:
        import math
        probs = [c / total_tracks for c in counts if c > 0]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(len(all_stats))
        balance = entropy / max_entropy if max_entropy > 0 else 0.0
    else:
        balance = 0.0

    health = 0.50 * overall_acc + 0.20 * coverage + 0.15 * avg_conf + 0.15 * balance
    print(f"\n  {B}Health score: {_color_pct(health)}{C}")
    print(f"    accuracy={overall_acc:.2f} x 0.50 + coverage={coverage:.2f} x 0.20 "
          f"+ confidence={avg_conf:.2f} x 0.15 + balance={balance:.2f} x 0.15")


def print_feature_heatmap(all_tracks: list[TrackAnalysis]) -> None:
    """Print feature means per subgenre as a compact heatmap."""
    print_header("FEATURE MEANS BY SUBGENRE")

    # Group tracks by assigned mood
    by_mood: dict[str, list[TrackAnalysis]] = defaultdict(list)
    for t in all_tracks:
        by_mood[t.assigned_mood].append(t)

    features = ["bpm", "lufs_i", "kick", "centroid", "onset", "hp_ratio",
                 "flux_m", "flux_s", "e_std", "e_mean", "lra", "crest", "flat"]

    # Compute means
    mood_order = [m.value for m in TrackMood.energy_order()]
    abbrevs = {
        "ambient_dub": "AmD", "dub_techno": "DuT", "minimal": "Min",
        "detroit": "Det", "melodic_deep": "MeD", "progressive": "Pro",
        "hypnotic": "Hyp", "driving": "Drv", "tribal": "Tri",
        "breakbeat": "Brk", "peak_time": "PkT", "acid": "Acd",
        "raw": "Raw", "industrial": "Ind", "hard_techno": "HdT",
    }

    # Header
    header = f"{'feat':>8s}"
    for m in mood_order:
        if by_mood.get(m):
            header += f" {abbrevs.get(m, m[:3]):>6s}"
    print(f"\n{D}{header}{C}")

    # Formatting per feature
    fmt_map = {
        "bpm": "{:.1f}", "lufs_i": "{:.1f}", "kick": "{:.2f}",
        "centroid": "{:.0f}", "onset": "{:.1f}", "hp_ratio": "{:.2f}",
        "flux_m": "{:.3f}", "flux_s": "{:.3f}", "e_std": "{:.3f}",
        "e_mean": "{:.3f}", "lra": "{:.1f}", "crest": "{:.1f}",
        "flat": "{:.3f}",
    }

    for feat in features:
        row = f"  {feat:>8s}"
        for m in mood_order:
            tracks = by_mood.get(m, [])
            if tracks:
                vals = [t.features[feat] for t in tracks]
                avg = mean(vals)
                row += f" {fmt_map[feat].format(avg):>6s}"
        print(row)


# ── JSON output ─────────────────────────────────────────────────────────────


def output_json(
    all_stats: list[PlaylistStats],
    all_tracks: list[TrackAnalysis],
    matrix: dict[str, dict[str, int]],
) -> None:
    """Output machine-readable JSON report."""
    total = len(all_tracks)
    correct = sum(1 for t in all_tracks if t.is_correct)

    report = {
        "total_tracks": total,
        "total_correct": correct,
        "overall_accuracy": correct / total if total else 0.0,
        "playlists": {},
        "confusion_matrix": matrix,
    }

    for s in all_stats:
        report["playlists"][s.mood] = {
            "name": s.name,
            "track_count": s.track_count,
            "correct_count": s.correct_count,
            "accuracy": round(s.accuracy, 4),
            "mean_confidence": round(s.mean_confidence, 4),
            "bpm_mean": round(s.bpm_mean, 1),
            "lufs_mean": round(s.lufs_mean, 1),
            "leak_to": s.leak_to,
            "fugitives": [
                {
                    "track_id": f.track_id,
                    "title": f.title,
                    "predicted": f.predicted_mood,
                    "assigned_score": round(f.top_scores.get(f.assigned_mood, 0), 4),
                    "predicted_score": round(f.top_scores.get(f.predicted_mood, 0), 4),
                }
                for f in s.fugitives[:5]
            ],
        }

    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze subgenre playlist quality")
    parser.add_argument("--playlist", type=str, help="Analyze only this subgenre (e.g. 'driving')")
    parser.add_argument(
        "--top-fugitives", type=int, default=5,
        help="Show N top fugitives per playlist",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON instead of human-readable",
    )
    args = parser.parse_args()

    await init_db()

    try:
        subgenre_map = await load_subgenre_map()
        all_tracks: list[TrackAnalysis] = []
        all_stats: list[PlaylistStats] = []

        if not args.json:
            print_header("SUBGENRE PLAYLIST QUALITY ANALYSIS")
            print(f"  Analyzing {len(subgenre_map)} subgenre playlists...")

        for mood_val, info in subgenre_map.items():
            if args.playlist and mood_val != args.playlist:
                continue

            db_pid = info["db_playlist_id"]
            name = info["name"]

            tracks = await load_playlist_tracks(db_pid, mood_val)
            all_tracks.extend(tracks)

            stats = compute_playlist_stats(mood_val, name, tracks, top_n=args.top_fugitives)

            # Compute leak_from (incoming misclassifications) later
            all_stats.append(stats)

            if not args.json:
                print_playlist_report(stats)

        # Compute leak_from across all playlists
        for t in all_tracks:
            if not t.is_correct:
                # This track is assigned to t.assigned_mood but predicted as t.predicted_mood
                # So t.predicted_mood "receives" a track from t.assigned_mood
                for s in all_stats:
                    if s.mood == t.predicted_mood:
                        s.leak_from[t.assigned_mood] = s.leak_from.get(t.assigned_mood, 0) + 1

        # Confusion matrix
        matrix = build_confusion_matrix(all_tracks)

        if args.json:
            output_json(all_stats, all_tracks, matrix)
        else:
            print_confusion_matrix(matrix)
            print_feature_heatmap(all_tracks)
            print_overall_summary(all_stats, all_tracks)

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
