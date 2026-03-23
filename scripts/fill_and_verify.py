#!/usr/bin/env python3
"""Fill YM playlist with fully verified techno tracks.

Filtering policy (priority order):
1. MUST BLOCK:  YM disliked (absolute blocklist, pre-scoring)
2. MUST PASS:   YM liked (bypass audio gate)
3. STRONG NEG:  missing audio features
4. SOFT SCORE:  not compilation, recency, kick_prominence, bpm_stability, LUFS
5. NOT YET:     mood classification (beat coverage <50%), hard year cuts (destroy 51% kept)

Pipeline per seed:
1. Get similar tracks from YM API
2. Pre-filter by metadata (genre=techno, duration>=4:15, no remixes/edits)
3. Import candidates to local DB
4. Download MP3 files
5. Run full audio analysis (BPM, LUFS, energy, onset, kick, spectral)
6. Apply feedback gate: block disliked, bypass audio gate for liked
7. Audio gate for remaining candidates
8. Add passing tracks to playlist; move rejected to '{source} deleted'

Feedback signals (liked/disliked) are fetched once at pipeline start.
Feature extraction runs for ALL candidates — including disliked — so the DB
always has audio data for future training/analysis.  The feedback gate is
applied AFTER extraction, keeping the 'deleted' playlist a clean negative
sample (user-rejected only) separate from audio failures.

Usage:
    uv run python scripts/fill_and_verify.py
    uv run python scripts/fill_and_verify.py --target 150 --workers 4 --batch 5
    uv run python scripts/fill_and_verify.py --no-skip-existing  # re-process tracks already in DB
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import contextlib
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.infrastructure.database import close_db, init_db, session_factory
from app.core.models.catalog import Track
from app.core.models.dj import DjLibraryItem, DjPlaylist, DjPlaylistItem
from app.core.models.features import TrackAudioFeaturesComputed
from app.core.models.ingestion import ProviderTrackId
from app.core.models.metadata_yandex import YandexMetadata
from app.core.models.runs import FeatureExtractionRun
from app.services.yandex_music_client import YandexMusicClient, parse_ym_track
from app.audio.mood_classifier import TrackMood, classify_track

# ── Config ───────────────────────────────────────────────────────────────────

_process_pool: concurrent.futures.ProcessPoolExecutor | None = None

YM_BASE = "https://api.music.yandex.net"
USER_ID = settings.yandex_music_user_id or "250905515"
LIBRARY_PATH = Path(settings.dj_library_path).expanduser()
REQUEST_DELAY = 1.5
MAX_RETRIES = 4
ANALYSIS_TIMEOUT_S = 180  # 3 min per track — essentia can hang on corrupt audio

# Metadata pre-filter
BAD_VERSION_WORDS = {"radio", "edit", "short", "remix", "live", "acoustic", "instrumental"}
MIN_DURATION_MS = 255_000  # 4:15

# Subgenre playlists
SUBGENRE_MAP_PATH = Path(__file__).with_name(".subgenre_playlists.json")
SUBGENRE_DISPLAY_NAMES: dict[str, str] = {
    "ambient_dub": "Techno: Ambient Dub",
    "dub_techno": "Techno: Dub Techno",
    "minimal": "Techno: Minimal",
    "detroit": "Techno: Detroit",
    "melodic_deep": "Techno: Melodic Deep",
    "progressive": "Techno: Progressive",
    "hypnotic": "Techno: Hypnotic",
    "driving": "Techno: Driving",
    "tribal": "Techno: Tribal",
    "breakbeat": "Techno: Breakbeat",
    "peak_time": "Techno: Peak Time",
    "acid": "Techno: Acid",
    "raw": "Techno: Raw",
    "industrial": "Techno: Industrial",
    "hard_techno": "Techno: Hard Techno",
}

# Audio criteria (full techno check — matches MCP mood_classifier + save_features)
BPM_MIN, BPM_MAX = 120.0, 155.0
LUFS_MIN, LUFS_MAX = -20.0, -4.0
ENERGY_MIN = 0.05
ONSET_MIN = 1.0
KICK_MIN = 0.05
CENTROID_MIN, CENTROID_MAX = 300.0, 10000.0
FLATNESS_MAX = 0.5
TEMPO_CONF_MIN = 0.3
BPM_STABILITY_MIN = 0.3
PULSE_CLARITY_MIN = 0.02
CREST_MAX = 30.0  # dB — too dynamic = not club-ready
LRA_MAX = 25.0  # LU — loudness range too wide
HP_RATIO_MAX = 8.0  # harmonic/percussive RMS ratio; unbounded (avg=2.2, >8 = extreme melodic)
HNR_MIN = -30.0  # extremely noisy signal

# ANSI colors
C = "\033[0m"
B = "\033[1m"
D = "\033[2m"
G = "\033[32m"
R = "\033[31m"
Y = "\033[33m"
CY = "\033[36m"
M = "\033[35m"
BG_G = "\033[42;30m"
BG_R = "\033[41;37m"
BG_Y = "\033[43;30m"


# ── Output helpers ───────────────────────────────────────────────────────────


def out(msg: str = "") -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def phase_header(num: int | str, title: str) -> None:
    out(f"\n{CY}{B}{'─' * 60}{C}")
    out(f"{CY}{B}  Phase {num}: {title}{C}")
    out(f"{CY}{'─' * 60}{C}")


def progress_bar(current: int, total: int, width: int = 30, label: str = "") -> str:
    """Render a dynamic progress bar string."""
    if total == 0:
        return ""
    frac = current / total
    filled = int(width * frac)
    bar = f"{'█' * filled}{'░' * (width - filled)}"
    pct = f"{frac * 100:5.1f}%"
    return f"  {bar} {pct}  {current}/{total}  {label}"


def progress_write(text: str) -> None:
    """Overwrite current line (carriage return, no newline)."""
    sys.stderr.write(f"\r\033[K{text}")
    sys.stderr.flush()


def progress_finish(text: str) -> None:
    """Finish progress line and move to next line."""
    sys.stderr.write(f"\r\033[K{text}\n")
    sys.stderr.flush()


def sanitize(title: str, max_len: int = 50) -> str:
    safe = re.sub(r'[/\\:*?"<>|]', "", title)
    safe = safe.replace(" ", "_")
    safe = re.sub(r"_+", "_", safe).lower()[:max_len].rstrip("_")
    return safe or "untitled"


# ── YM API client ───────────────────────────────────────────────────────────


class YmApi:
    """Thin async wrapper for Yandex Music REST API with throttling."""

    def __init__(self, token: str) -> None:
        self.token = token
        self._client: httpx.AsyncClient | None = None
        self._last_req = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - elapsed)
        self._last_req = time.monotonic()

    async def get(self, url: str) -> dict[str, Any]:
        for attempt in range(MAX_RETRIES):
            await self._throttle()
            c = await self._get_client()
            resp = await c.get(url, headers={"Authorization": f"OAuth {self.token}"})
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                out(f"  {Y}429 -> backoff {wait}s{C}")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        raise httpx.HTTPStatusError("429 after retries", request=resp.request, response=resp)

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        for attempt in range(MAX_RETRIES):
            await self._throttle()
            c = await self._get_client()
            resp = await c.post(url, headers={"Authorization": f"OAuth {self.token}"}, data=data)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                out(f"  {Y}429 -> backoff {wait}s{C}")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        raise httpx.HTTPStatusError("429 after retries", request=resp.request, response=resp)


# ── Data container ───────────────────────────────────────────────────────────


@dataclass
class Candidate:
    ym_id: str
    album_id: str
    title: str
    artists: str
    duration_ms: int
    raw: dict[str, Any]
    track_id: int = 0
    file_path: Path | None = None
    audio_ok: bool | None = None  # None = not analyzed yet
    fail_reasons: list[str] = field(default_factory=list)
    mood: TrackMood | None = None


# ── Metadata pre-filter ─────────────────────────────────────────────────────


def is_techno(track: dict[str, Any]) -> bool:
    for album in track.get("albums", []):
        genre = (album.get("genre") or "").lower()
        if "techno" in genre:
            return True
    return False


def has_bad_version(track: dict[str, Any]) -> str | None:
    version = (track.get("version") or "").lower()
    title = (track.get("title") or "").lower()
    for word in BAD_VERSION_WORDS:
        if word in version or f"({word}" in title or f"[{word}" in title:
            return word
    return None


def track_label(track: dict[str, Any]) -> str:
    artists = ", ".join(a.get("name", "?") for a in track.get("artists", []))
    return f"{artists} -- {track.get('title', '?')}"


# ── Audio criteria check ────────────────────────────────────────────────────


def check_audio(feats: Any) -> list[str]:
    """Check TrackFeatures against full techno criteria.

    Mirrors parameters used by MCP: mood_classifier (6 params), save_features (47 cols),
    filter_by_criteria (bpm/key/lufs), and curation tools.
    """
    reasons: list[str] = []

    # ── Tempo ────────────────────────────────────────────────────────────
    bpm = feats.bpm.bpm
    tempo_conf = feats.bpm.confidence
    bpm_stab = feats.bpm.stability

    if bpm < BPM_MIN or bpm > BPM_MAX:
        reasons.append(f"BPM={bpm:.1f}")
    if tempo_conf < TEMPO_CONF_MIN:
        reasons.append(f"TempoConf={tempo_conf:.2f}")
    if bpm_stab < BPM_STABILITY_MIN:
        reasons.append(f"BpmStab={bpm_stab:.2f}")

    # ── Loudness & dynamics ──────────────────────────────────────────────
    lufs = feats.loudness.lufs_i
    crest = feats.loudness.crest_factor_db
    lra = feats.loudness.lra_lu

    if lufs < LUFS_MIN or lufs > LUFS_MAX:
        reasons.append(f"LUFS={lufs:.1f}")
    if crest is not None and crest > CREST_MAX:
        reasons.append(f"Crest={crest:.1f}dB")
    if lra is not None and lra > LRA_MAX:
        reasons.append(f"LRA={lra:.1f}LU")

    # ── Energy bands ─────────────────────────────────────────────────────
    e_mid = feats.band_energy.mid  # energy_mean in DB
    e_low = feats.band_energy.low
    e_high = feats.band_energy.high

    if e_mid < ENERGY_MIN:
        reasons.append(f"Energy={e_mid:.4f}")
    if e_low is not None and e_low < 0.01:
        reasons.append(f"NoBass={e_low:.3f}")
    if e_high is not None and e_high > 0.7:
        reasons.append(f"HiDom={e_high:.2f}")

    # ── Rhythm (used by mood_classifier) ─────────────────────────────────
    beats = feats.beats
    if beats is not None:
        if beats.onset_rate_mean < ONSET_MIN:
            reasons.append(f"Onset={beats.onset_rate_mean:.2f}")
        if beats.kick_prominence < KICK_MIN:
            reasons.append(f"Kick={beats.kick_prominence:.2f}")
        if beats.pulse_clarity < PULSE_CLARITY_MIN:
            reasons.append(f"Pulse={beats.pulse_clarity:.3f}")
        if beats.hp_ratio > HP_RATIO_MAX:
            reasons.append(f"HP={beats.hp_ratio:.2f} (no percussion)")

    # ── Spectral ─────────────────────────────────────────────────────────
    spectral = feats.spectral
    centroid = spectral.centroid_mean_hz if spectral else 0
    flatness = spectral.flatness_mean if spectral else 0
    hnr = spectral.hnr_mean_db if spectral else 0

    if centroid and (centroid < CENTROID_MIN or centroid > CENTROID_MAX):
        reasons.append(f"Centroid={centroid:.0f}Hz")
    if flatness and flatness > FLATNESS_MAX:
        reasons.append(f"Flatness={flatness:.3f}")
    if hnr is not None and hnr < HNR_MIN:
        reasons.append(f"HNR={hnr:.1f}dB")

    return reasons


def check_audio_from_db(f: Any) -> list[str]:
    """Same criteria as check_audio but from TrackAudioFeaturesComputed ORM row."""
    reasons: list[str] = []

    # Tempo
    if f.bpm < BPM_MIN or f.bpm > BPM_MAX:
        reasons.append(f"BPM={f.bpm:.1f}")
    if f.tempo_confidence is not None and f.tempo_confidence < TEMPO_CONF_MIN:
        reasons.append(f"TempoConf={f.tempo_confidence:.2f}")
    if f.bpm_stability is not None and f.bpm_stability < BPM_STABILITY_MIN:
        reasons.append(f"BpmStab={f.bpm_stability:.2f}")

    # Loudness & dynamics
    if f.lufs_i < LUFS_MIN or f.lufs_i > LUFS_MAX:
        reasons.append(f"LUFS={f.lufs_i:.1f}")
    if f.crest_factor_db is not None and f.crest_factor_db > CREST_MAX:
        reasons.append(f"Crest={f.crest_factor_db:.1f}dB")
    if f.lra_lu is not None and f.lra_lu > LRA_MAX:
        reasons.append(f"LRA={f.lra_lu:.1f}LU")

    # Energy bands (energy_mean = mid band in save_features)
    if f.energy_mean is not None and f.energy_mean < ENERGY_MIN:
        reasons.append(f"Energy={f.energy_mean:.4f}")
    if f.low_energy is not None and f.low_energy < 0.01:
        reasons.append(f"NoBass={f.low_energy:.3f}")
    if f.high_energy is not None and f.high_energy > 0.7:
        reasons.append(f"HiDom={f.high_energy:.2f}")

    # Rhythm
    if f.onset_rate_mean is not None and f.onset_rate_mean < ONSET_MIN:
        reasons.append(f"Onset={f.onset_rate_mean:.2f}")
    if f.kick_prominence is not None and f.kick_prominence < KICK_MIN:
        reasons.append(f"Kick={f.kick_prominence:.2f}")
    if f.pulse_clarity is not None and f.pulse_clarity < PULSE_CLARITY_MIN:
        reasons.append(f"Pulse={f.pulse_clarity:.3f}")
    if f.hp_ratio is not None and f.hp_ratio > HP_RATIO_MAX:
        reasons.append(f"HP={f.hp_ratio:.2f}")

    # Spectral
    if f.centroid_mean_hz is not None and (
        f.centroid_mean_hz < CENTROID_MIN or f.centroid_mean_hz > CENTROID_MAX
    ):
        reasons.append(f"Centroid={f.centroid_mean_hz:.0f}Hz")
    if f.flatness_mean is not None and f.flatness_mean > FLATNESS_MAX:
        reasons.append(f"Flatness={f.flatness_mean:.3f}")
    if f.hnr_mean_db is not None and f.hnr_mean_db < HNR_MIN:
        reasons.append(f"HNR={f.hnr_mean_db:.1f}dB")

    return reasons


# ── Subgenre playlist helpers ─────────────────────────────────────────────


def _load_subgenre_map() -> dict[str, dict[str, Any]]:
    """Load {mood_value: {ym_kind, db_playlist_id, name}} from JSON."""
    if SUBGENRE_MAP_PATH.exists():
        try:
            return json.loads(SUBGENRE_MAP_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_subgenre_map(mapping: dict[str, dict[str, Any]]) -> None:
    """Persist subgenre playlist mapping."""
    SUBGENRE_MAP_PATH.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n")


def classify_from_db(feat: Any) -> TrackMood:
    """Classify track mood from DB audio features row (ORM or raw).

    Fallback values are P50 medians from real data (N=583 tracks).
    """
    mc = classify_track(
        bpm=feat.bpm,
        lufs_i=feat.lufs_i,
        kick_prominence=feat.kick_prominence or 0.5,
        spectral_centroid_mean=feat.centroid_mean_hz or 2500.0,
        onset_rate=feat.onset_rate_mean or 5.0,
        hp_ratio=feat.hp_ratio or 2.0,
        pulse_clarity=feat.pulse_clarity or 1.0,
        flux_mean=feat.flux_mean or 0.18,
        flux_std=feat.flux_std or 0.10,
        energy_std=feat.energy_std or 0.13,
        energy_mean=feat.energy_mean or 0.22,
        sub_energy=feat.sub_energy or 0.95,
        lra_lu=feat.lra_lu or 6.6,
        crest_factor_db=feat.crest_factor_db or 13.3,
        chroma_entropy=feat.chroma_entropy or 0.98,
        contrast_mean_db=feat.contrast_mean_db or -0.7,
        flatness_mean=feat.flatness_mean or 0.06,
        energy_slope_mean=feat.energy_slope_mean or 0.0,
    )
    return mc.mood


async def init_subgenre_playlists(api: YmApi) -> dict[str, dict[str, Any]]:
    """Create YM + local DB playlists for all 15 subgenres if not exist.

    Returns mapping {mood_value: {ym_kind, db_playlist_id, name}}.
    """
    mapping = _load_subgenre_map()
    created = 0

    for mood in TrackMood:
        mood_val = mood.value
        if mood_val in mapping:
            # Verify YM playlist still exists
            kind = mapping[mood_val]["ym_kind"]
            try:
                await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/{kind}")
                continue
            except Exception:
                out(f"  {Y}YM playlist kind={kind} for {mood_val} gone, recreating{C}")

        display_name = SUBGENRE_DISPLAY_NAMES[mood_val]

        # Create YM playlist
        data = await api.post_form(
            f"{YM_BASE}/users/{USER_ID}/playlists/create",
            {"title": display_name, "visibility": "public"},
        )
        result = data.get("result", data)
        ym_kind = str(result["kind"])

        # Create local DB playlist
        async with session_factory() as session:
            db_pl = DjPlaylist(
                name=display_name,
                source_of_truth="ym",
                platform_ids={"ym": ym_kind},
            )
            session.add(db_pl)
            await session.flush()
            db_pid = db_pl.playlist_id
            await session.commit()

        mapping[mood_val] = {
            "ym_kind": ym_kind,
            "db_playlist_id": db_pid,
            "name": display_name,
        }
        created += 1
        out(f"  {G}+{C} {display_name} (ym={ym_kind}, db={db_pid})")
        await asyncio.sleep(REQUEST_DELAY)

    _save_subgenre_map(mapping)
    if created:
        out(f"  {G}Created {created} subgenre playlists{C}")
    else:
        out(f"  {D}All 15 subgenre playlists exist{C}")
    return mapping


async def add_to_subgenre_playlist(
    api: YmApi,
    subgenre_map: dict[str, dict[str, Any]],
    mood_val: str,
    candidates: list[Any],
) -> None:
    """Add candidates to the YM + DB subgenre playlist."""
    if not candidates:
        return
    sg = subgenre_map[mood_val]
    ym_kind = sg["ym_kind"]
    db_pid = sg["db_playlist_id"]

    # Add to YM
    rev, _, existing_ids, _ = await fetch_playlist(api, ym_kind)
    new_tracks = [
        c for c in candidates if (c.ym_id if hasattr(c, "ym_id") else str(c)) not in existing_ids
    ]
    if new_tracks:
        add_tracks = [
            {"id": c.ym_id, "albumId": c.album_id}
            if hasattr(c, "album_id") and c.album_id
            else {"id": c.ym_id if hasattr(c, "ym_id") else str(c)}
            for c in new_tracks
        ]
        try:
            new_rev = await add_to_playlist(api, ym_kind, rev, add_tracks)
            out(f"    {G}+{C} {sg['name']}: {len(new_tracks)} tracks (rev={new_rev})")
        except httpx.HTTPStatusError as e:
            out(f"    {R}Failed to add to {sg['name']}: {e}{C}")
            return

    # Add to local DB
    async with session_factory() as session:
        # Get current max sort_index
        row = await session.execute(
            text(
                "SELECT COALESCE(MAX(sort_index), -1) FROM dj_playlist_items"
                f" WHERE playlist_id = {db_pid}"
            )
        )
        max_idx = row.scalar() or -1

        for i, cand in enumerate(new_tracks):
            track_id = cand.track_id if hasattr(cand, "track_id") else 0
            if track_id:
                # Check not already in playlist
                exists = await session.execute(
                    select(DjPlaylistItem.playlist_item_id).where(
                        DjPlaylistItem.playlist_id == db_pid,
                        DjPlaylistItem.track_id == track_id,
                    )
                )
                if exists.scalar():
                    continue
                session.add(
                    DjPlaylistItem(
                        playlist_id=db_pid,
                        track_id=track_id,
                        sort_index=max_idx + 1 + i,
                    )
                )
        await session.commit()


# ── Feedback gate helpers ──────────────────────────────────────────────────


def is_disliked(ym_id: int, disliked_ids: set[int]) -> bool:
    """Return True if the track was explicitly disliked by the user (absolute blocklist)."""
    return int(ym_id) in disliked_ids


def is_liked(ym_id: int, liked_ids: set[int]) -> bool:
    """Return True if the track was explicitly liked — bypasses audio gate."""
    return int(ym_id) in liked_ids


# ── Seed selection ──────────────────────────────────────────────────────────

_SEED_MIN_WEIGHT = 1.0  # floor weight for freshly-added tracks


def _pick_weighted_seed(
    candidates: list[str],
    timestamps: dict[str, str],
) -> str:
    """Pick a seed track weighted by age (older = higher probability).

    Weight = max(1, age_in_hours).  A track added 7 days ago is ~168x
    more likely to be picked than one added <1 hour ago.  This favours
    tracks that survived manual curation (older = user kept them).
    """
    if not candidates:
        msg = "No candidates for seed selection"
        raise ValueError(msg)

    now = datetime.now(UTC)
    weights: list[float] = []
    for tid in candidates:
        ts_str = timestamps.get(tid)
        if ts_str:
            try:
                added = datetime.fromisoformat(ts_str)
                age_hours = (now - added).total_seconds() / 3600.0
                weights.append(max(_SEED_MIN_WEIGHT, age_hours))
            except (ValueError, TypeError):
                weights.append(_SEED_MIN_WEIGHT)
        else:
            weights.append(_SEED_MIN_WEIGHT)

    return random.choices(candidates, weights=weights, k=1)[0]


# ── Playlist operations ─────────────────────────────────────────────────────


async def fetch_playlist(
    api: YmApi,
    kind: str,
) -> tuple[int, int, list[str], dict[str, str]]:
    """Returns (revision, track_count, list_of_ym_ids, {id: timestamp_iso}).

    ``timestamp`` is the ISO-8601 date when the track was added to the playlist.
    Used for weighted seed selection (older tracks = higher weight).
    """
    data = await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/{kind}")
    result = data.get("result", data)
    revision = result.get("revision", 0)
    track_count = result.get("trackCount", 0)
    tracks = result.get("tracks", [])
    ids: list[str] = []
    timestamps: dict[str, str] = {}
    for item in tracks:
        tr = item.get("track", item)
        tid = str(tr.get("id", ""))
        if tid:
            ids.append(tid)
            ts = item.get("timestamp", "")
            if ts:
                timestamps[tid] = ts
    return revision, track_count, ids, timestamps


async def add_to_playlist(
    api: YmApi, kind: str, revision: int, tracks: list[dict[str, str]]
) -> int:
    diff = json.dumps([{"op": "insert", "at": 0, "tracks": tracks}])
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/{kind}/change",
        {"diff": diff, "revision": str(revision)},
    )
    return data.get("result", {}).get("revision", revision + 1)


async def delete_from_playlist(api: YmApi, kind: str, revision: int, index: int) -> int:
    """Delete track at given index. Returns new revision."""
    diff = json.dumps([{"op": "delete", "from": index, "to": index + 1}])
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/{kind}/change",
        {"diff": diff, "revision": str(revision)},
    )
    return data.get("result", {}).get("revision", revision + 1)


async def clear_playlist(api: YmApi, kind: str) -> int:
    """Remove ALL tracks from a YM playlist. Returns new revision."""
    rev, track_count, _, _ = await fetch_playlist(api, kind)
    if track_count == 0:
        return rev
    diff = json.dumps([{"op": "delete", "from": 0, "to": track_count}])
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/{kind}/change",
        {"diff": diff, "revision": str(rev)},
    )
    return data.get("result", {}).get("revision", rev + 1)


_PLAYLIST_MAP_PATH = Path(__file__).with_name(".playlist_map.json")


def _load_playlist_map() -> dict[str, str]:
    """Load {source_kind: deleted_kind} mapping from local JSON file."""
    if _PLAYLIST_MAP_PATH.exists():
        try:
            return json.loads(_PLAYLIST_MAP_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_playlist_map(mapping: dict[str, str]) -> None:
    """Persist {source_kind: deleted_kind} mapping."""
    _PLAYLIST_MAP_PATH.write_text(json.dumps(mapping, indent=2) + "\n")


async def _playlist_exists(api: YmApi, kind: str) -> bool:
    """Check if a playlist with given kind exists (quick HEAD-like check)."""
    try:
        data = await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/{kind}")
        result = data.get("result", data)
        return bool(result.get("kind"))
    except Exception:
        return False


async def get_or_create_deleted_playlist(
    api: YmApi,
    source_kind: str,
    source_name: str,
) -> str:
    """Get deleted playlist kind by ID mapping, create if missing. Returns kind.

    Lookup order:
    1. Local mapping file (.playlist_map.json) — by source_kind
    2. CLI --deleted-kind override (handled by caller)
    3. Create new playlist and save mapping
    """
    mapping = _load_playlist_map()

    # Check saved mapping
    saved_kind = mapping.get(source_kind)
    if saved_kind:
        if await _playlist_exists(api, saved_kind):
            out(f"  {D}Deleted playlist: kind={saved_kind} (from mapping){C}")
            return saved_kind
        out(f"  {Y}Mapped deleted playlist kind={saved_kind} no longer exists{C}")

    # Create new playlist
    deleted_name = f"{source_name} deleted"
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/create",
        {"title": deleted_name, "visibility": "private"},
    )
    result = data.get("result", data)
    kind = str(result["kind"])

    # Save mapping
    mapping[source_kind] = kind
    _save_playlist_map(mapping)

    out(f"  {G}Created '{deleted_name}' playlist: kind={kind}{C}")
    return kind


async def add_to_deleted_playlist(
    api: YmApi,
    deleted_kind: str,
    candidates: list[Candidate],
) -> None:
    """Add rejected candidates to the 'deleted' playlist."""
    if not candidates:
        return

    revision, _, existing_ids, _ = await fetch_playlist(api, deleted_kind)

    # Skip tracks already in deleted playlist
    to_add = [c for c in candidates if c.ym_id not in existing_ids]
    if not to_add:
        out(f"  {D}All failed tracks already in deleted playlist{C}")
        return

    add_tracks = [
        {"id": c.ym_id, "albumId": c.album_id} if c.album_id else {"id": c.ym_id} for c in to_add
    ]
    try:
        new_rev = await add_to_playlist(api, deleted_kind, revision, add_tracks)
        out(f"  {Y}Moved {len(to_add)} failed tracks to deleted playlist (rev={new_rev}){C}")
    except httpx.HTTPStatusError as e:
        out(f"  {R}Failed to add to deleted playlist: {e}{C}")


async def get_disliked_ids(api: YmApi) -> set[int]:
    """Fetch user's disliked track IDs (as ints for gate functions)."""
    try:
        data = await api.get(f"{YM_BASE}/users/{USER_ID}/dislikes/tracks")
        result = data.get("result", data)
        lib = result.get("library", result)
        tracks = lib.get("tracks", [])
        return {int(t["id"]) for t in tracks if t.get("id")}
    except Exception as e:
        out(f"  {D}Could not fetch dislikes: {e}{C}")
        return set()


async def get_liked_ids(api: YmApi) -> set[int]:
    """Fetch user's liked track IDs (as ints for gate functions)."""
    try:
        data = await api.get(f"{YM_BASE}/users/{USER_ID}/likes/tracks")
        result = data.get("result", data)
        lib = result.get("library", result)
        tracks = lib.get("tracks", [])
        return {int(t["id"]) for t in tracks if t.get("id")}
    except Exception as e:
        out(f"  {D}Could not fetch likes: {e}{C}")
        return set()


async def remove_disliked_from_playlist(
    api: YmApi,
    kind: str,
    deleted_kind: str,
    disliked_ids: set[int] | None = None,
) -> int:
    """Remove disliked tracks from playlist, move to deleted. Returns count removed.

    Accepts pre-fetched *disliked_ids* (``set[int]``) so the caller can reuse
    the set across the session.  Falls back to a fresh API call when ``None``.
    """
    disliked = disliked_ids if disliked_ids is not None else await get_disliked_ids(api)
    if not disliked:
        return 0

    revision, _, playlist_ids, _ = await fetch_playlist(api, kind)
    to_remove = [(i, tid) for i, tid in enumerate(playlist_ids) if is_disliked(int(tid), disliked)]

    if not to_remove:
        return 0

    out(f"  {Y}Found {len(to_remove)} disliked tracks in playlist{C}")

    # Move to deleted playlist first
    candidates_for_deleted: list[Candidate] = []
    for _, tid in to_remove:
        candidates_for_deleted.append(
            Candidate(
                ym_id=tid,
                album_id="",
                title=f"disliked:{tid}",
                artists="",
                duration_ms=0,
                raw={},
            )
        )
    await add_to_deleted_playlist(api, deleted_kind, candidates_for_deleted)

    # Delete from main playlist (reverse order to keep indices valid)
    for idx, tid in reversed(to_remove):
        try:
            revision = await delete_from_playlist(api, kind, revision, idx)
            out(f"  {R}-{C} Removed disliked track {tid} (idx={idx})")
        except httpx.HTTPStatusError:
            # Re-fetch after failure (indices may have shifted)
            revision, _, playlist_ids, _ = await fetch_playlist(api, kind)
            for j, pid in enumerate(playlist_ids):
                if pid == tid:
                    revision = await delete_from_playlist(api, kind, revision, j)
                    out(f"  {R}-{C} Removed disliked track {tid} (re-indexed)")
                    break

    return len(to_remove)


async def verify_no_disliked_in_main(
    api: YmApi,
    kind: str,
    deleted_kind: str,
    disliked_ids: set[int],
) -> int:
    """Ensure no disliked track remains in the main playlist.

    Specifically catches track 76796973 (Rhythm Dancer) and any other
    disliked IDs that leaked into the main playlist (kind *kind*).
    Returns the number of tracks removed.
    """
    revision, _, playlist_ids, _ = await fetch_playlist(api, kind)
    leaked = [
        (i, tid) for i, tid in enumerate(playlist_ids) if is_disliked(int(tid), disliked_ids)
    ]
    if not leaked:
        return 0

    out(f"  {Y}verify_no_disliked_in_main: found {len(leaked)} disliked tracks still in main{C}")

    # Move to deleted playlist
    cands = [
        Candidate(ym_id=tid, album_id="", title=f"leaked:{tid}", artists="", duration_ms=0, raw={})
        for _, tid in leaked
    ]
    await add_to_deleted_playlist(api, deleted_kind, cands)

    # Delete from main (reverse order)
    removed = 0
    for idx, tid in reversed(leaked):
        try:
            revision = await delete_from_playlist(api, kind, revision, idx)
            removed += 1
            out(f"  {R}-{C} verify: removed disliked track {tid} from main")
        except httpx.HTTPStatusError:
            revision, _, current_ids, _ = await fetch_playlist(api, kind)
            for j, pid in enumerate(current_ids):
                if pid == tid:
                    revision = await delete_from_playlist(api, kind, revision, j)
                    removed += 1
                    out(f"  {R}-{C} verify: removed disliked track {tid} (re-indexed)")
                    break

    return removed


async def audit_playlist_tracks(
    api: YmApi,
    kind: str,
    deleted_kind: str,
    liked_ids: set[int] | None = None,
) -> int:
    """Check ALL playlist tracks against audio criteria. Remove failures.

    Liked tracks (in *liked_ids*) bypass the audio gate entirely.
    This is AUDIO ANALYSIS rejection based on BPM, LUFS, energy, etc.
    For tracks without features in DB — downloads + analyzes them first.

    Returns count of removed tracks.
    """
    revision, _, playlist_ids, _ = await fetch_playlist(api, kind)
    if not playlist_ids:
        return 0

    # Map ym_id → track_id via provider_track_ids
    to_check: list[tuple[int, str, int]] = []  # (index, ym_id, track_id)
    async with session_factory() as session:
        for i, ym_id in enumerate(playlist_ids):
            row = await session.execute(
                select(ProviderTrackId.track_id).where(
                    ProviderTrackId.provider_track_id == ym_id,
                )
            )
            tid = row.scalar()
            if tid:
                to_check.append((i, ym_id, tid))

    if not to_check:
        return 0

    # Check features for each track
    _liked = liked_ids or set()
    fail_indices: list[tuple[int, str]] = []  # (index, ym_id)
    audit_total = len(to_check)
    for audit_i, (idx, ym_id, track_id) in enumerate(to_check, 1):
        # Liked tracks bypass the audio gate entirely
        if is_liked(int(ym_id), _liked):
            progress_finish(
                progress_bar(
                    audit_i,
                    audit_total,
                    label=f"{G}LIKED{C} #{track_id} — bypass audio gate",
                )
            )
            continue

        progress_write(progress_bar(audit_i, audit_total, label=f"🔍 #{track_id}"))
        async with session_factory() as session:
            row = await session.execute(
                select(TrackAudioFeaturesComputed).where(
                    TrackAudioFeaturesComputed.track_id == track_id,
                )
            )
            feat = row.scalars().first()

        if not feat:
            # No features — need to analyze. Check if file exists.
            async with session_factory() as session:
                lib_row = await session.execute(
                    select(DjLibraryItem.file_path).where(
                        DjLibraryItem.track_id == track_id,
                    )
                )
                file_path = lib_row.scalar()

            if file_path and Path(file_path).exists():
                # Check iCloud stub
                st = Path(file_path).stat()
                if hasattr(st, "st_blocks") and st.st_blocks * 512 < st.st_size * 0.9:
                    out(f"  {D}skip audit {ym_id}: iCloud stub{C}")
                    continue

                out(f"  {D}Analyzing unverified track #{track_id}...{C}")
                try:
                    loop = asyncio.get_event_loop()
                    feats = await asyncio.wait_for(
                        loop.run_in_executor(
                            _process_pool,
                            _extract_sync,
                            file_path,
                        ),
                        timeout=ANALYSIS_TIMEOUT_S,
                    )
                    # Save to DB
                    async with session_factory() as session:
                        from app.infrastructure.repositories.audio_features import AudioFeaturesRepository

                        run = FeatureExtractionRun(
                            pipeline_name="audit",
                            pipeline_version="1.0",
                            status="completed",
                        )
                        session.add(run)
                        await session.flush()
                        repo = AudioFeaturesRepository(session)
                        await repo.save_features(track_id, run.run_id, feats)
                        await session.commit()

                    reasons = check_audio(feats)
                except Exception as e:
                    out(f"  {R}audit analysis error #{track_id}: {e!s:.60}{C}")
                    continue
            else:
                continue  # no file, skip
        else:
            reasons = check_audio_from_db(feat)

        if reasons:
            fail_indices.append((idx, ym_id))
            progress_finish(
                progress_bar(
                    audit_i,
                    audit_total,
                    label=f"{R}FAIL{C} #{track_id}: {', '.join(reasons)}",
                )
            )
        else:
            progress_finish(
                progress_bar(
                    audit_i,
                    audit_total,
                    label=f"{G}OK{C} #{track_id}",
                )
            )

    if not fail_indices:
        return 0

    # Move to deleted playlist
    candidates_for_deleted = [
        Candidate(
            ym_id=ym_id, album_id="", title=f"audit:{ym_id}", artists="", duration_ms=0, raw={}
        )
        for _, ym_id in fail_indices
    ]
    await add_to_deleted_playlist(api, deleted_kind, candidates_for_deleted)

    # Delete from playlist (reverse order)
    removed = 0
    for idx, ym_id in reversed(fail_indices):
        try:
            revision = await delete_from_playlist(api, kind, revision, idx)
            removed += 1
            out(f"  {R}-{C} Removed audit-failed track {ym_id}")
        except httpx.HTTPStatusError:
            revision, _, current_ids, _ = await fetch_playlist(api, kind)
            for j, pid in enumerate(current_ids):
                if pid == ym_id:
                    revision = await delete_from_playlist(api, kind, revision, j)
                    removed += 1
                    out(f"  {R}-{C} Removed audit-failed track {ym_id} (re-indexed)")
                    break

    return removed


# ── Core pipeline steps ─────────────────────────────────────────────────────


async def get_similar_candidates(
    api: YmApi, seed_id: str, seen: set[str], batch: int
) -> list[Candidate]:
    """Get similar tracks, pre-filter by metadata, return candidates."""
    data = await api.get(f"{YM_BASE}/tracks/{seed_id}/similar")
    similar = data.get("result", {}).get("similarTracks", [])
    candidates: list[Candidate] = []

    for tr in similar:
        tid = str(tr.get("id", ""))
        if tid in seen:
            continue
        seen.add(tid)

        dur = tr.get("durationMs", 0)
        if dur < MIN_DURATION_MS:
            out(f"  {D}skip {track_label(tr)} [short {dur // 1000}s]{C}")
            continue

        if not is_techno(tr):
            out(f"  {D}skip {track_label(tr)} [not techno]{C}")
            continue

        bad = has_bad_version(tr)
        if bad:
            out(f"  {D}skip {track_label(tr)} [{bad}]{C}")
            continue

        albums = tr.get("albums", [])
        album_id = str(albums[0].get("id", "")) if albums else ""
        artists = ", ".join(a.get("name", "?") for a in tr.get("artists", []))

        candidates.append(
            Candidate(
                ym_id=tid,
                album_id=album_id,
                title=tr.get("title", "?"),
                artists=artists,
                duration_ms=dur,
                raw=tr,
            )
        )

        if len(candidates) >= batch:
            break

    return candidates


async def import_candidate(candidate: Candidate) -> None:
    """Import candidate to local DB if not exists."""
    async with session_factory() as session:
        prov_row = await session.execute(
            text("SELECT provider_id FROM providers WHERE provider_code = 'ym'")
        )
        provider_id = prov_row.scalar()
        if not provider_id:
            return

        existing = await session.execute(
            select(ProviderTrackId.track_id).where(
                ProviderTrackId.provider_id == provider_id,
                ProviderTrackId.provider_track_id == candidate.ym_id,
            )
        )
        existing_tid = existing.scalar_one_or_none()
        if existing_tid:
            candidate.track_id = existing_tid
            return

        parsed = parse_ym_track(candidate.raw)
        track = Track(
            title=parsed.title,
            title_sort=parsed.title.lower(),
            duration_ms=parsed.duration_ms or 0,
            status=0,
        )
        session.add(track)
        await session.flush()

        session.add(
            ProviderTrackId(
                track_id=track.track_id,
                provider_id=provider_id,
                provider_track_id=candidate.ym_id,
                provider_country="RU",
            )
        )
        session.add(
            YandexMetadata(
                track_id=track.track_id,
                yandex_track_id=parsed.yandex_track_id,
                yandex_album_id=parsed.yandex_album_id,
                album_title=parsed.album_title,
                album_type=parsed.album_type,
                album_genre=parsed.album_genre,
                album_year=parsed.album_year,
                label_name=parsed.label_name,
                release_date=parsed.release_date,
                duration_ms=parsed.duration_ms,
                cover_uri=parsed.cover_uri,
                explicit=parsed.explicit,
            )
        )
        await session.flush()
        candidate.track_id = track.track_id
        await session.commit()


async def download_candidate(candidate: Candidate, ym_client: YandexMusicClient) -> bool:
    """Download MP3 if not cached. Returns True on success."""
    async with session_factory() as session:
        existing = await session.execute(
            select(DjLibraryItem).where(DjLibraryItem.track_id == candidate.track_id)
        )
        lib_item = existing.scalar_one_or_none()
        if lib_item and lib_item.file_path and Path(lib_item.file_path).exists():
            p = Path(lib_item.file_path)
            # Check not iCloud stub
            st = p.stat()
            if st.st_blocks * 512 >= st.st_size * 0.9:
                candidate.file_path = p
                return True

        filename = f"{candidate.track_id}_{sanitize(candidate.title)}.mp3"
        dest = LIBRARY_PATH / filename

        if not dest.exists():
            try:
                file_size = await ym_client.download_track(
                    candidate.ym_id, str(dest), prefer_bitrate=320
                )
            except Exception as e:
                out(f"  {R}download fail: {candidate.artists} -- {candidate.title}: {e!s:.60}{C}")
                return False
        else:
            file_size = dest.stat().st_size

        file_hash = hashlib.sha256(dest.read_bytes()).digest()

        if not lib_item:
            lib_item = DjLibraryItem(
                track_id=candidate.track_id,
                file_path=str(dest),
                file_size_bytes=file_size,
                file_hash=file_hash,
                bitrate_kbps=320,
                mime_type="audio/mpeg",
            )
            session.add(lib_item)
            await session.flush()
            await session.commit()

        candidate.file_path = dest
        return True


def _extract_sync(audio_path: str) -> Any:
    """CPU-heavy feature extraction (runs in subprocess to isolate C-extension crashes).

    Essentia/scipy/soundfile are C-extensions that can segfault on corrupt audio.
    Running in a subprocess means a segfault kills only the worker, not the main script.
    """
    from app.audio.pipeline import extract_all_features

    return extract_all_features(audio_path)


async def analyze_candidate(candidate: Candidate, sem: asyncio.Semaphore) -> bool:
    """Analyze audio, save to DB, check criteria. Returns True if passes."""
    if not candidate.file_path:
        return False

    # Check cached features
    async with session_factory() as session:
        existing = await session.execute(
            select(TrackAudioFeaturesComputed).where(
                TrackAudioFeaturesComputed.track_id == candidate.track_id
            )
        )
        cached = existing.scalars().first()
        if cached:
            # Re-check from DB values (same criteria as check_audio)
            reasons = check_audio_from_db(cached)
            candidate.fail_reasons = reasons
            candidate.audio_ok = len(reasons) == 0
            return candidate.audio_ok

    # Extract features (CPU-heavy, parallel-limited)
    # Use ProcessPoolExecutor to isolate C-extension segfaults (essentia/scipy/soundfile).
    # A segfault in a subprocess kills only the worker, not the main script.
    async with sem:
        loop = asyncio.get_event_loop()
        try:
            feats = await asyncio.wait_for(
                loop.run_in_executor(_process_pool, _extract_sync, str(candidate.file_path)),
                timeout=ANALYSIS_TIMEOUT_S,
            )
        except TimeoutError:
            out(f"  {R}analysis timeout ({ANALYSIS_TIMEOUT_S}s): {candidate.title}{C}")
            candidate.audio_ok = False
            candidate.fail_reasons = [f"timeout after {ANALYSIS_TIMEOUT_S}s"]
            return False
        except concurrent.futures.BrokenExecutor:
            out(f"  {R}analysis crash (C-extension segfault?): {candidate.title}{C}")
            candidate.audio_ok = False
            candidate.fail_reasons = ["worker crash (segfault?)"]
            return False
        except Exception as e:
            out(f"  {R}analysis fail: {candidate.title}: {e!s:.60}{C}")
            candidate.audio_ok = False
            candidate.fail_reasons = [f"analysis error: {e!s:.40}"]
            return False

    # Check criteria
    candidate.fail_reasons = check_audio(feats)
    candidate.audio_ok = len(candidate.fail_reasons) == 0

    # Save to DB
    async with session_factory() as session:
        from app.infrastructure.repositories.audio_features import AudioFeaturesRepository

        run = FeatureExtractionRun(
            pipeline_name="fill_and_verify",
            pipeline_version="1.0",
            status="completed",
        )
        session.add(run)
        await session.flush()
        repo = AudioFeaturesRepository(session)
        await repo.save_features(candidate.track_id, run.run_id, feats)
        await session.commit()

    return candidate.audio_ok


# ── Distribute mode ──────────────────────────────────────────────────────────


async def _distribute_tracks(
    api: YmApi,
    source_kind: str,
    *,
    clean: bool = False,
    ym_client: YandexMusicClient | None = None,
    sem: asyncio.Semaphore | None = None,
) -> None:
    """Classify all tracks from source playlist and distribute to subgenre playlists.

    If ym_client and sem are provided, tracks missing from local DB or without
    audio features will be auto-imported, downloaded, and analyzed.
    """
    out(f"\n{B}{'=' * 60}{C}")
    out(f"{B}  Distribute Mode — classify & route to subgenre playlists{C}")
    if clean:
        out(f"{Y}  (--clean: all subgenre playlists will be cleared first){C}")
    out(f"{B}{'=' * 60}{C}")

    # 1. Init subgenre playlists (create if needed)
    phase_header(1, "Init subgenre playlists")
    subgenre_map = await init_subgenre_playlists(api)

    # 1b. Clear existing playlists if --clean
    if clean:
        phase_header("1b", "Clear subgenre playlists")
        for mood in TrackMood:
            sg = subgenre_map[mood.value]
            ym_kind = sg["ym_kind"]
            db_pid = sg["db_playlist_id"]
            new_rev = await clear_playlist(api, ym_kind)
            # Also clear local DB
            async with session_factory() as session:
                await session.execute(
                    text(f"DELETE FROM dj_playlist_items WHERE playlist_id = {db_pid}")
                )
                await session.commit()
            out(f"  {D}Cleared {sg['name']} (rev={new_rev}){C}")
            await asyncio.sleep(REQUEST_DELAY)

    # 2. Fetch source playlist tracks
    phase_header(2, "Fetch source playlist")
    _, track_count, playlist_ids, _ = await fetch_playlist(api, source_kind)
    out(f"  {CY}Source playlist: {track_count} tracks{C}")

    if not playlist_ids:
        out(f"  {Y}No tracks in source playlist{C}")
        return

    # 3. Classify each track
    phase_header(3, f"Classify {len(playlist_ids)} tracks")
    from collections import defaultdict

    by_mood: dict[str, list[dict[str, str]]] = defaultdict(list)
    # {mood_value: [{ym_id, album_id, track_id, title}]}
    classified = 0
    skipped = 0

    for i, ym_id in enumerate(playlist_ids, 1):
        progress_write(progress_bar(i, len(playlist_ids), label=f"classifying {ym_id}"))

        # Find track_id via provider_track_ids
        async with session_factory() as session:
            row = await session.execute(
                select(ProviderTrackId.track_id).where(
                    ProviderTrackId.provider_track_id == ym_id,
                )
            )
            track_id = row.scalar()

        if not track_id:
            # Auto-import: fetch metadata from YM, create DB records
            if not ym_client or not sem:
                skipped += 1
                progress_finish(
                    progress_bar(
                        i,
                        len(playlist_ids),
                        label=f"{Y}SKIP{C} {ym_id} (not in DB)",
                    )
                )
                continue
            try:
                resp = await api.get(f"{YM_BASE}/tracks/{ym_id}")
                tracks_data = resp.get("result", [])
                if not tracks_data:
                    raise ValueError("empty result")
                raw = tracks_data[0]
            except Exception as e:
                skipped += 1
                progress_finish(
                    progress_bar(
                        i,
                        len(playlist_ids),
                        label=f"{Y}SKIP{C} {ym_id} (YM fetch fail: {e!s:.30})",
                    )
                )
                continue
            albums = raw.get("albums", [])
            album_id_str = str(albums[0].get("id", "")) if albums else ""
            artists = ", ".join(a.get("name", "?") for a in raw.get("artists", []))
            cand = Candidate(
                ym_id=ym_id,
                album_id=album_id_str,
                title=raw.get("title", "?"),
                artists=artists,
                duration_ms=raw.get("durationMs", 0),
                raw=raw,
            )
            await import_candidate(cand)
            if not cand.track_id:
                skipped += 1
                progress_finish(
                    progress_bar(
                        i,
                        len(playlist_ids),
                        label=f"{Y}SKIP{C} {ym_id} (import fail)",
                    )
                )
                continue
            track_id = cand.track_id
            ok = await download_candidate(cand, ym_client)
            if not ok:
                skipped += 1
                progress_finish(
                    progress_bar(
                        i,
                        len(playlist_ids),
                        label=f"{Y}SKIP{C} #{track_id} (download fail)",
                    )
                )
                continue
            await analyze_candidate(cand, sem)
            progress_write(
                progress_bar(
                    i,
                    len(playlist_ids),
                    label=f"{CY}imported{C} #{track_id}",
                )
            )

        # Get audio features
        async with session_factory() as session:
            row = await session.execute(
                select(TrackAudioFeaturesComputed).where(
                    TrackAudioFeaturesComputed.track_id == track_id,
                )
            )
            feat = row.scalars().first()

        if not feat:
            # Auto-analyze: track exists but no features
            if ym_client and sem:
                # Build candidate for download + analyze
                async with session_factory() as session:
                    lib_row = await session.execute(
                        select(DjLibraryItem.file_path).where(
                            DjLibraryItem.track_id == track_id,
                        )
                    )
                    file_path = lib_row.scalar()
                    title_row = await session.execute(
                        select(Track.title).where(Track.track_id == track_id)
                    )
                    title = title_row.scalar() or "?"
                albums_str = ""
                async with session_factory() as session:
                    ym_row = await session.execute(
                        select(YandexMetadata.yandex_album_id).where(
                            YandexMetadata.track_id == track_id,
                        )
                    )
                    albums_str = ym_row.scalar() or ""
                cand = Candidate(
                    ym_id=ym_id,
                    album_id=albums_str,
                    title=title,
                    artists="",
                    duration_ms=0,
                    raw={},
                    track_id=track_id,
                )
                if file_path:
                    cand.file_path = Path(file_path)
                else:
                    ok = await download_candidate(cand, ym_client)
                    if not ok:
                        skipped += 1
                        progress_finish(
                            progress_bar(
                                i,
                                len(playlist_ids),
                                label=f"{Y}SKIP{C} #{track_id} (download fail)",
                            )
                        )
                        continue
                await analyze_candidate(cand, sem)
                # Re-fetch features after analysis
                async with session_factory() as session:
                    row = await session.execute(
                        select(TrackAudioFeaturesComputed).where(
                            TrackAudioFeaturesComputed.track_id == track_id,
                        )
                    )
                    feat = row.scalars().first()

            if not feat:
                skipped += 1
                progress_finish(
                    progress_bar(
                        i,
                        len(playlist_ids),
                        label=f"{Y}SKIP{C} #{track_id} (no features)",
                    )
                )
                continue

        mood = classify_from_db(feat)

        # Get album_id from YM metadata
        async with session_factory() as session:
            ym_row = await session.execute(
                select(YandexMetadata.yandex_album_id).where(
                    YandexMetadata.track_id == track_id,
                )
            )
            album_id = ym_row.scalar() or ""

        by_mood[mood.value].append(
            {
                "ym_id": ym_id,
                "album_id": album_id,
                "track_id": str(track_id),
            }
        )
        classified += 1
        progress_finish(
            progress_bar(
                i,
                len(playlist_ids),
                label=f"{G}{mood.value}{C} #{track_id}",
            )
        )

    # 4. Add to subgenre playlists
    phase_header(4, "Distribute to subgenre playlists")
    for mood in TrackMood:
        mood_val = mood.value
        tracks = by_mood.get(mood_val, [])
        if not tracks:
            continue

        sg = subgenre_map[mood_val]
        ym_kind = sg["ym_kind"]
        db_pid = sg["db_playlist_id"]

        # Add to YM playlist
        rev, _, existing_ids, _ = await fetch_playlist(api, ym_kind)
        new_tracks = [t for t in tracks if t["ym_id"] not in existing_ids]

        if new_tracks:
            add_tracks = [
                {"id": t["ym_id"], "albumId": t["album_id"]}
                if t["album_id"]
                else {"id": t["ym_id"]}
                for t in new_tracks
            ]
            # Retry with fresh revision on 412 (stale revision)
            for _attempt in range(3):
                try:
                    new_rev = await add_to_playlist(api, ym_kind, rev, add_tracks)
                    out(f"  {G}+{C} {sg['name']}: {len(new_tracks)} new (rev={new_rev})")
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 412 and _attempt < 2:
                        out(f"  {Y}412 stale revision for {sg['name']}, re-fetching...{C}")
                        await asyncio.sleep(REQUEST_DELAY)
                        rev, _, existing_ids, _ = await fetch_playlist(api, ym_kind)
                        new_tracks = [t for t in tracks if t["ym_id"] not in existing_ids]
                        if not new_tracks:
                            out(f"  {D}{sg['name']}: all present after re-fetch{C}")
                            break
                        add_tracks = [
                            {"id": t["ym_id"], "albumId": t["album_id"]}
                            if t["album_id"]
                            else {"id": t["ym_id"]}
                            for t in new_tracks
                        ]
                        continue
                    out(f"  {R}Failed {sg['name']}: {e}{C}")
                    break

            # Add to local DB
            async with session_factory() as session:
                row = await session.execute(
                    text(
                        "SELECT COALESCE(MAX(sort_index), -1)"
                        f" FROM dj_playlist_items WHERE playlist_id = {db_pid}"
                    )
                )
                max_idx = row.scalar() or -1
                for j, t in enumerate(new_tracks):
                    tid = int(t["track_id"])
                    if tid:
                        exists = await session.execute(
                            select(DjPlaylistItem.playlist_item_id).where(
                                DjPlaylistItem.playlist_id == db_pid,
                                DjPlaylistItem.track_id == tid,
                            )
                        )
                        if not exists.scalar():
                            session.add(
                                DjPlaylistItem(
                                    playlist_id=db_pid,
                                    track_id=tid,
                                    sort_index=max_idx + 1 + j,
                                )
                            )
                await session.commit()

            await asyncio.sleep(REQUEST_DELAY)
        else:
            out(f"  {D}{sg['name']}: {len(tracks)} (all already present){C}")

    # 5. Summary
    out(f"\n{B}{'=' * 60}{C}")
    out(f"{G}{B}  Distribution complete{C}")
    out(f"{B}  Classified: {classified}  |  Skipped: {skipped}{C}")
    out(f"{B}{'─' * 60}{C}")
    for mood in TrackMood:
        count = len(by_mood.get(mood.value, []))
        if count:
            bar = "█" * min(count, 40)
            name = SUBGENRE_DISPLAY_NAMES[mood.value]
            out(f"  {mood.intensity:2d}. {name:<25s} {count:3d} {D}{bar}{C}")
    out(f"{B}{'=' * 60}{C}")


async def _backfill_source(api: YmApi, source_kind: str) -> None:
    """Collect all tracks from subgenre playlists and add missing ones to source."""
    out(f"\n{B}{'=' * 60}{C}")
    out(f"{B}  Backfill — add subgenre tracks missing from source playlist{C}")
    out(f"{B}{'=' * 60}{C}")

    subgenre_map = _load_subgenre_map()
    if not subgenre_map:
        out(f"  {R}No subgenre map found. Run --distribute first.{C}")
        return

    # Collect all track IDs from subgenre playlists
    all_subgenre_ids: set[str] = set()
    for _mood_val, sg in subgenre_map.items():
        ym_kind = sg["ym_kind"]
        try:
            _, count, ids, _ = await fetch_playlist(api, ym_kind)
            all_subgenre_ids.update(ids)
            out(f"  {D}{sg['name']}: {count} tracks{C}")
        except Exception as e:
            out(f"  {Y}Failed to fetch {sg['name']}: {e}{C}")
        await asyncio.sleep(REQUEST_DELAY)

    out(f"\n  {CY}Total unique tracks in subgenre playlists: {len(all_subgenre_ids)}{C}")

    # Fetch source playlist
    rev, src_count, source_ids, _ = await fetch_playlist(api, source_kind)
    source_set = set(source_ids)
    out(f"  {CY}Source playlist (kind={source_kind}): {src_count} tracks{C}")

    # Find missing
    missing_ids = all_subgenre_ids - source_set
    if not missing_ids:
        out(f"\n  {G}All subgenre tracks already in source playlist. Nothing to do.{C}")
        return

    out(f"  {Y}Missing from source: {len(missing_ids)} tracks{C}")

    # Need album IDs for each missing track — look up from YM metadata in DB
    add_tracks: list[dict[str, str]] = []
    for ym_id in missing_ids:
        async with session_factory() as session:
            row = await session.execute(
                select(
                    ProviderTrackId.track_id,
                ).where(
                    ProviderTrackId.provider_track_id == ym_id,
                )
            )
            track_id = row.scalar()

        album_id = ""
        if track_id:
            async with session_factory() as session:
                ym_row = await session.execute(
                    select(YandexMetadata.yandex_album_id).where(
                        YandexMetadata.track_id == track_id,
                    )
                )
                album_id = ym_row.scalar() or ""

        entry: dict[str, str] = {"id": ym_id}
        if album_id:
            entry["albumId"] = album_id
        add_tracks.append(entry)

    # Add in batches of 50 to avoid too-large requests
    batch_size = 50
    added = 0
    for start in range(0, len(add_tracks), batch_size):
        batch = add_tracks[start : start + batch_size]
        # Re-fetch revision before each batch
        rev, _, _, _ = await fetch_playlist(api, source_kind)
        try:
            new_rev = await add_to_playlist(api, source_kind, rev, batch)
            added += len(batch)
            out(f"  {G}+{C} batch {start // batch_size + 1}: {len(batch)} tracks (rev={new_rev})")
        except httpx.HTTPStatusError as e:
            out(f"  {R}Failed batch {start // batch_size + 1}: {e}{C}")
        await asyncio.sleep(REQUEST_DELAY)

    out(f"\n{B}{'=' * 60}{C}")
    out(f"{G}{B}  Backfill complete: added {added}/{len(missing_ids)} tracks{C}")
    out(f"{B}{'=' * 60}{C}")


# ── Main loop ────────────────────────────────────────────────────────────────


async def main() -> None:
    global _process_pool
    parser = argparse.ArgumentParser(description="Fill & verify YM techno playlist")
    parser.add_argument("--kind", default="1280", help="Playlist kind ID")
    parser.add_argument("--target", type=int, default=0, help="Target track count (0 = unlimited)")
    parser.add_argument("--batch", type=int, default=5, help="Candidates per seed")
    parser.add_argument("--workers", type=int, default=4, help="Parallel analysis workers")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=0,
        help="Max seed rounds (0 = unlimited)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        default=False,
        help="Allow tracks already in DB to enter pipeline (by default they are skipped)",
    )
    parser.add_argument(
        "--deleted-kind",
        default=None,
        help="Kind ID for the 'deleted' playlist (skip name-based lookup)",
    )
    parser.add_argument(
        "--distribute",
        action="store_true",
        default=False,
        help="Distribute existing playlist tracks into subgenre playlists, then exit",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="With --distribute: clear all subgenre playlists before distributing",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        default=False,
        help="Add missing tracks from subgenre playlists back into source playlist",
    )
    args = parser.parse_args()

    if not settings.yandex_music_token:
        raise RuntimeError("YANDEX_MUSIC_TOKEN not set")

    await init_db()
    LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    # Lower process priority
    with contextlib.suppress(OSError):
        os.nice(10)

    api = YmApi(settings.yandex_music_token)

    # ── Backfill mode: add subgenre tracks missing from source playlist ──
    if args.backfill:
        try:
            await _backfill_source(api, args.kind)
        finally:
            await api.close()
            await close_db()
        return

    # ── Distribute mode: classify existing tracks into subgenre playlists ──
    if args.distribute:
        # Init process pool + YM client for auto-import of missing tracks
        _process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=args.workers)
        ym_client = YandexMusicClient(token=settings.yandex_music_token)
        sem = asyncio.Semaphore(args.workers)
        try:
            await _distribute_tracks(
                api,
                args.kind,
                clean=args.clean,
                ym_client=ym_client,
                sem=sem,
            )
        finally:
            await ym_client.close()
            await api.close()
            await close_db()
            _process_pool.shutdown(wait=False, cancel_futures=True)
        return

    ym_client = YandexMusicClient(token=settings.yandex_music_token)
    sem = asyncio.Semaphore(args.workers)

    # ProcessPoolExecutor isolates C-extension crashes (essentia segfaults)
    # from the main process.  max_workers=workers so semaphore controls concurrency.
    _process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=args.workers)
    seen_ids: set[str] = set()
    seed_used: set[str] = set()
    total_added = 0
    total_rejected = 0

    # Pre-populate seen_ids with tracks already in DB (skip re-processing)
    skip_existing = not args.no_skip_existing
    db_ym_ids: set[str] = set()
    if skip_existing:
        async with session_factory() as session:
            rows = await session.execute(
                text(
                    "SELECT pt.provider_track_id FROM provider_track_ids pt"
                    " JOIN providers p ON p.provider_id = pt.provider_id"
                    " WHERE p.provider_code = 'ym'"
                )
            )
            db_ym_ids = {row[0] for row in rows}
            seen_ids.update(db_ym_ids)

    out(f"{B}{'=' * 60}{C}")
    out(f"{B}  Fill & Verify Pipeline{C}")
    target_str = str(args.target) if args.target else "∞"
    skip_label = (
        f"  Skip existing: {len(db_ym_ids)} DB tracks" if skip_existing else "  Skip existing: OFF"
    )
    out(f"{B}  Playlist: {USER_ID}/{args.kind}  Target: {target_str}  Workers: {args.workers}{C}")
    out(f"{B}{skip_label}{C}")
    out(f"{B}{'=' * 60}{C}")

    # Get source playlist name and find/create deleted playlist
    pl_data = await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/{args.kind}")
    pl_result = pl_data.get("result", pl_data)
    source_name = pl_result.get("title", f"Playlist {args.kind}")
    if args.deleted_kind:
        deleted_kind = args.deleted_kind
        out(f"  {D}Using deleted playlist: kind={deleted_kind}{C}")
    else:
        deleted_kind = await get_or_create_deleted_playlist(
            api,
            args.kind,
            source_name,
        )

    # Init subgenre playlists (create YM + DB playlists if needed)
    subgenre_map = await init_subgenre_playlists(api)

    # Fetch feedback signals once — reused across the whole session
    disliked_ids = await get_disliked_ids(api)
    liked_ids = await get_liked_ids(api)
    out(f"  {D}Feedback: {len(disliked_ids)} disliked, {len(liked_ids)} liked{C}")

    # NOTE: disliked IDs are NOT added to seen_ids so that similar-track
    # discovery still works and features are extracted for every candidate.
    # The feedback gate is applied AFTER feature extraction.

    shutdown = False

    def _handle_sigint(*_: object) -> None:
        nonlocal shutdown
        if shutdown:
            out(f"\n  {R}{B}Force quit{C}")
            raise SystemExit(1)
        shutdown = True
        out(f"\n  {Y}{B}Shutting down after current round... (Ctrl+C again to force){C}")

    import signal

    signal.signal(signal.SIGINT, _handle_sigint)

    completed_normally = False
    round_num = 0
    try:
        while not shutdown:
            round_num += 1
            if args.max_rounds and round_num > args.max_rounds:
                out(f"\n  {Y}Max rounds ({args.max_rounds}) reached{C}")
                break
            # ── Fetch current state ──────────────────────────────────────
            revision, track_count, playlist_ids, track_ts = await fetch_playlist(api, args.kind)
            seen_ids.update(playlist_ids)

            # ── Remove disliked tracks from main playlist ──────────────
            removed = await remove_disliked_from_playlist(
                api,
                args.kind,
                deleted_kind,
                disliked_ids=disliked_ids,
            )
            if removed:
                revision, track_count, playlist_ids, track_ts = await fetch_playlist(
                    api, args.kind
                )
                total_rejected += removed

            # ── Verify no disliked leaked into main ───────────────────
            if round_num == 1:
                leaked = await verify_no_disliked_in_main(
                    api,
                    args.kind,
                    deleted_kind,
                    disliked_ids,
                )
                if leaked:
                    revision, track_count, playlist_ids, track_ts = await fetch_playlist(
                        api, args.kind
                    )
                    total_rejected += leaked
                    out(f"  {Y}verify_no_disliked_in_main cleaned {leaked} tracks{C}")

            # ── Audit: verify all playlist tracks pass criteria ────────
            if round_num == 1:  # full audit on first round only
                audit_removed = await audit_playlist_tracks(
                    api,
                    args.kind,
                    deleted_kind,
                    liked_ids=liked_ids,
                )
                if audit_removed:
                    revision, track_count, playlist_ids, track_ts = await fetch_playlist(
                        api, args.kind
                    )
                    total_rejected += audit_removed
                    out(f"  {Y}Audit removed {audit_removed} tracks{C}")

            out(f"\n{CY}{B}{'=' * 60}{C}")
            out(
                f"{CY}{B}  Round {round_num}  |  {track_count}/{target_str} tracks  |  "
                f"rev={revision}  |  +{total_added} -{total_rejected}{C}"
            )
            out(f"{CY}{'=' * 60}{C}")

            if args.target and track_count >= args.target:
                out(f"\n  {G}{B}Target reached! {track_count} tracks{C}")
                break

            # ── Pick seed (weighted by age — older = more likely curated) ─
            available_seeds = [tid for tid in playlist_ids if tid not in seed_used]
            if not available_seeds:
                seed_used.clear()
                available_seeds = playlist_ids
            seed_id = _pick_weighted_seed(available_seeds, track_ts)
            seed_used.add(seed_id)

            out(f"\n  {D}Seed: {seed_id}{C}")

            # ── Phase 1: Get similar + metadata pre-filter ───────────────
            phase_header(1, "Similar tracks + metadata filter")
            candidates = await get_similar_candidates(api, seed_id, seen_ids, args.batch)
            out(f"  {CY}Candidates after metadata filter: {len(candidates)}{C}")

            if not candidates:
                out(f"  {Y}No candidates, next seed...{C}")
                continue

            # ── Phase 2: Import to DB ────────────────────────────────────
            phase_header(2, "Import to local DB")
            for cand in candidates:
                await import_candidate(cand)
                if cand.track_id:
                    out(f"  {G}+{C} #{cand.track_id} {cand.artists} -- {cand.title}")
                else:
                    out(f"  {R}!{C} Failed to import: {cand.artists} -- {cand.title}")

            candidates = [c for c in candidates if c.track_id > 0]

            # ── Phase 3: Download MP3 ────────────────────────────────────
            phase_header(3, "Download MP3 files")
            download_ok: list[Candidate] = []
            dl_total = len(candidates)
            for dl_i, cand in enumerate(candidates, 1):
                label = f"{D}{cand.artists} -- {cand.title}{C}"
                progress_write(progress_bar(dl_i - 1, dl_total, label=f"⬇ {label}"))
                ok = await download_candidate(cand, ym_client)
                if ok:
                    download_ok.append(cand)
                    sz = cand.file_path.stat().st_size // 1024 if cand.file_path else 0
                    progress_finish(
                        progress_bar(
                            dl_i,
                            dl_total,
                            label=f"{G}+{C} {sz}KB {cand.title}",
                        )
                    )
                else:
                    progress_finish(progress_bar(dl_i, dl_total, label=f"{R}!{C} {cand.title}"))
                await asyncio.sleep(REQUEST_DELAY)

            # ── Phase 4: Audio analysis (parallel, streaming output) ────
            # Feature extraction runs for ALL candidates — including disliked
            # ones — so the DB always has audio data for training/analysis.
            phase_header(4, f"Audio analysis ({args.workers} workers)")
            analyzed: list[Candidate] = []
            an_total = len(download_ok)
            an_done = 0

            async def _analyze_and_report(
                cand: Candidate,
                _total: int = an_total,
                _out: list[Candidate] = analyzed,
            ) -> None:
                nonlocal an_done
                progress_write(progress_bar(an_done, _total, label=f"♫ {D}{cand.title}{C}"))
                try:
                    await analyze_candidate(cand, sem)
                except Exception as e:
                    cand.audio_ok = False
                    cand.fail_reasons = [f"crash: {e!s:.60}"]
                    out(f"\n  {R}CRASH{C} {cand.title}: {e!s:.80}")
                an_done += 1
                if cand.audio_ok:
                    progress_finish(
                        progress_bar(
                            an_done,
                            _total,
                            label=f"{G}PASS{C} {cand.title}",
                        )
                    )
                elif cand.audio_ok is False:
                    progress_finish(
                        progress_bar(
                            an_done,
                            _total,
                            label=f"{R}FAIL{C} {cand.title} {D}{', '.join(cand.fail_reasons)}{C}",
                        )
                    )
                else:
                    progress_finish(
                        progress_bar(
                            an_done,
                            _total,
                            label=f"{Y}NO-FEAT{C} {cand.title}",
                        )
                    )
                _out.append(cand)

            tasks = [_analyze_and_report(cand) for cand in download_ok]
            # return_exceptions=True prevents one BaseException (CancelledError,
            # BrokenExecutor) from cancelling ALL other tasks.
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, BaseException):
                    cand = download_ok[i]
                    out(f"  {R}UNHANDLED{C} {cand.title}: {res!r}")
                    if cand not in analyzed:
                        cand.audio_ok = False
                        cand.fail_reasons = [f"unhandled: {res!s:.60}"]
                        analyzed.append(cand)

            # ── Phase 4b: Feedback gate (AFTER feature extraction) ─────
            # Priority: disliked → hard block; liked → bypass audio gate
            phase_header(4, "Feedback gate")
            passed: list[Candidate] = []
            failed: list[Candidate] = []
            blocked: list[Candidate] = []

            for cand in analyzed:
                ym_int = int(cand.ym_id)
                if is_disliked(ym_int, disliked_ids):
                    blocked.append(cand)
                    out(f"  {R}BLOCK{C} {cand.artists} -- {cand.title} {D}(disliked){C}")
                    total_rejected += 1
                elif is_liked(ym_int, liked_ids):
                    # Liked bypasses audio gate but still needs mood for routing
                    async with session_factory() as session:
                        row = await session.execute(
                            select(TrackAudioFeaturesComputed).where(
                                TrackAudioFeaturesComputed.track_id == cand.track_id
                            )
                        )
                        feat = row.scalars().first()
                        if feat:
                            cand.mood = classify_from_db(feat)
                    passed.append(cand)
                    mood_tag = f" [{cand.mood.value}]" if cand.mood else ""
                    out(
                        f"  {G}LIKED{C} {cand.artists} -- {cand.title}"
                        f" {D}(bypass audio gate){mood_tag}{C}"
                    )
                elif cand.audio_ok:
                    # Classify mood for routing
                    bpm_s = "?"
                    lufs_s = "?"
                    async with session_factory() as session:
                        row = await session.execute(
                            select(TrackAudioFeaturesComputed).where(
                                TrackAudioFeaturesComputed.track_id == cand.track_id
                            )
                        )
                        feat = row.scalars().first()
                        if feat:
                            bpm_s = f"{feat.bpm:.0f}"
                            lufs_s = f"{feat.lufs_i:.1f}"
                            cand.mood = classify_from_db(feat)
                    mood_tag = f" [{cand.mood.value}]" if cand.mood else ""
                    passed.append(cand)
                    out(
                        f"  {G}PASS{C} {cand.artists} -- {cand.title}"
                        f" {D}BPM={bpm_s} LUFS={lufs_s}{mood_tag}{C}"
                    )
                else:
                    failed.append(cand)
                    out(
                        f"  {R}FAIL{C} {cand.artists} -- {cand.title}"
                        f" {D}{', '.join(cand.fail_reasons)}{C}"
                    )
                    total_rejected += 1

            # Move audio-failed and blocked to deleted playlist (separate reasons)
            if failed:
                await add_to_deleted_playlist(api, deleted_kind, failed)
            if blocked:
                await add_to_deleted_playlist(api, deleted_kind, blocked)

            # ── Phase 5: Add passed to subgenre playlists ────────────────
            if passed:
                from collections import defaultdict

                by_mood: dict[str, list[Candidate]] = defaultdict(list)
                no_mood: list[Candidate] = []
                for cand in passed:
                    if cand.mood:
                        by_mood[cand.mood.value].append(cand)
                    else:
                        no_mood.append(cand)

                phase_header(5, f"Route {len(passed)} tracks to subgenre playlists")

                for mood_val, mood_cands in sorted(by_mood.items()):
                    await add_to_subgenre_playlist(
                        api,
                        subgenre_map,
                        mood_val,
                        mood_cands,
                    )
                    await asyncio.sleep(REQUEST_DELAY)

                # Also add ALL passed tracks to the source (general) playlist
                revision, track_count, playlist_ids, _ = await fetch_playlist(api, args.kind)
                all_add = [{"id": c.ym_id, "albumId": c.album_id} for c in passed]
                try:
                    await add_to_playlist(api, args.kind, revision, all_add)
                    total_added += len(passed)
                    out(f"  {G}+{C} {len(passed)} tracks → source playlist (rev={revision})")
                except httpx.HTTPStatusError as e:
                    out(f"  {R}Failed to add to source playlist: {e}{C}")
            else:
                out(f"\n  {Y}No tracks passed verification this round{C}")

        # ── Final summary ────────────────────────────────────────────────
        completed_normally = True
        try:
            revision, track_count, _, _ = await fetch_playlist(api, args.kind)
        except Exception:
            track_count = "?"
            revision = "?"
        out(f"\n{B}{'=' * 60}{C}")
        out(f"{G}{B}  DONE: {track_count}/{target_str} tracks  |  rev={revision}{C}")
        out(
            f"{G}{B}  Added: {total_added}  |  Rejected: {total_rejected}"
            f"  |  Rounds: {round_num}{C}"
        )
        # Show subgenre playlist sizes
        out(f"{B}{'─' * 60}{C}")
        for mood in TrackMood:
            sg = subgenre_map.get(mood.value)
            if sg:
                try:
                    _, sg_count, _, _ = await fetch_playlist(api, sg["ym_kind"])
                    bar = "█" * min(sg_count, 40)
                    out(f"  {mood.intensity:2d}. {sg['name']:<25s} {sg_count:3d} {D}{bar}{C}")
                except Exception:
                    pass
        out(f"{B}{'=' * 60}{C}")

    except Exception as fatal_err:
        out(f"\n  {R}{B}FATAL: {fatal_err}{C}")
        import traceback

        traceback.print_exc()

    except BaseException as base_err:
        # Catches SystemExit (double Ctrl+C), CancelledError, KeyboardInterrupt
        out(f"\n  {R}{B}EXIT ({type(base_err).__name__}): {base_err}{C}")

    finally:
        # Print crash summary ONLY if exit was abnormal
        if not completed_normally:
            try:
                _, tc_final, _, _ = await fetch_playlist(api, args.kind)
                out(f"\n{B}{'=' * 60}{C}")
                out(
                    f"{Y}{B}  CRASHED after {round_num} rounds  |  {tc_final} tracks  |  "
                    f"+{total_added} -{total_rejected}{C}"
                )
                out(f"{B}{'=' * 60}{C}")
            except Exception as summary_err:
                # API also failed — print what we know without API data
                out(f"\n{B}{'=' * 60}{C}")
                out(
                    f"{Y}{B}  CRASHED after {round_num} rounds  |  "
                    f"+{total_added} -{total_rejected}  |  "
                    f"(API unavailable: {summary_err!s:.40}){C}"
                )
                out(f"{B}{'=' * 60}{C}")

        # Shutdown process pool (kill any hung C-extension workers)
        if _process_pool is not None:
            _process_pool.shutdown(wait=False, cancel_futures=True)
        await api.close()
        await ym_client.close()
        await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\033[33m\033[1mInterrupted by user\033[0m", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise  # re-raise to preserve exit code
    except BaseException as exc:
        print(f"\n\033[91m\033[1mFATAL ({type(exc).__name__}): {exc}\033[0m", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
