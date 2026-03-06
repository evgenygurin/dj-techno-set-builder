#!/usr/bin/env python3
"""Fill YM playlist with fully verified techno tracks.

For each seed track in the playlist:
1. Get similar tracks from YM API
2. Pre-filter by metadata (genre=techno, duration>=4:15, no remixes/edits)
3. Import candidates to local DB
4. Download MP3 files
5. Run full audio analysis (BPM, LUFS, energy, onset, kick, spectral)
6. Filter by audio criteria — add ONLY tracks that pass
7. Delete any tracks that fail from the playlist

Usage:
    uv run python scripts/fill_and_verify.py
    uv run python scripts/fill_and_verify.py --target 150 --workers 4 --batch 5
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import close_db, init_db, session_factory
from app.models.catalog import Track
from app.models.dj import DjLibraryItem
from app.models.features import TrackAudioFeaturesComputed
from app.models.ingestion import ProviderTrackId
from app.models.metadata_yandex import YandexMetadata
from app.models.runs import FeatureExtractionRun
from app.services.yandex_music_client import YandexMusicClient, parse_ym_track

# ── Config ───────────────────────────────────────────────────────────────────

YM_BASE = "https://api.music.yandex.net"
USER_ID = settings.yandex_music_user_id or "250905515"
LIBRARY_PATH = Path(settings.dj_library_path).expanduser()
REQUEST_DELAY = 1.5
MAX_RETRIES = 4

# Metadata pre-filter
BAD_VERSION_WORDS = {"radio", "edit", "short", "remix", "live", "acoustic", "instrumental"}
MIN_DURATION_MS = 255_000  # 4:15

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
CREST_MAX = 30.0    # dB — too dynamic = not club-ready
LRA_MAX = 25.0      # LU — loudness range too wide
HP_RATIO_MAX = 8.0   # harmonic/percussive RMS ratio; unbounded (avg=2.2, >8 = extreme melodic)
HNR_MIN = -30.0     # extremely noisy signal

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


def phase_header(num: int, title: str) -> None:
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


# ── Playlist operations ─────────────────────────────────────────────────────


async def fetch_playlist(api: YmApi, kind: str) -> tuple[int, int, list[str]]:
    """Returns (revision, track_count, list_of_ym_ids)."""
    data = await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/{kind}")
    result = data.get("result", data)
    revision = result.get("revision", 0)
    track_count = result.get("trackCount", 0)
    tracks = result.get("tracks", [])
    ids: list[str] = []
    for item in tracks:
        tr = item.get("track", item)
        tid = str(tr.get("id", ""))
        if tid:
            ids.append(tid)
    return revision, track_count, ids


async def add_to_playlist(api: YmApi, kind: str, revision: int,
                          tracks: list[dict[str, str]]) -> int:
    diff = json.dumps([{"op": "insert", "at": 0, "tracks": tracks}])
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/{kind}/change",
        {"diff": diff, "revision": str(revision)},
    )
    return data.get("result", {}).get("revision", revision + 1)


async def delete_from_playlist(api: YmApi, kind: str, revision: int,
                               index: int) -> int:
    """Delete track at given index. Returns new revision."""
    diff = json.dumps([{"op": "delete", "from": index, "to": index + 1}])
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/{kind}/change",
        {"diff": diff, "revision": str(revision)},
    )
    return data.get("result", {}).get("revision", revision + 1)


async def get_or_create_deleted_playlist(
    api: YmApi, source_name: str,
) -> str:
    """Find or create a '{source_name} deleted' playlist. Returns kind."""
    deleted_name = f"{source_name} deleted"

    # List user playlists and look for existing
    data = await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/list")
    playlists = data.get("result", data) if isinstance(data.get("result"), list) else data.get("result", [])
    if isinstance(playlists, dict):
        playlists = playlists.get("playlists", playlists.get("result", []))

    for pl in playlists:
        if pl.get("title", "") == deleted_name:
            kind = str(pl["kind"])
            out(f"  {D}Found '{deleted_name}' playlist: kind={kind}{C}")
            return kind

    # Create new playlist
    data = await api.post_form(
        f"{YM_BASE}/users/{USER_ID}/playlists/create",
        {"title": deleted_name, "visibility": "private"},
    )
    result = data.get("result", data)
    kind = str(result["kind"])
    out(f"  {G}Created '{deleted_name}' playlist: kind={kind}{C}")
    return kind


async def add_to_deleted_playlist(
    api: YmApi, deleted_kind: str, candidates: list[Candidate],
) -> None:
    """Add failed candidates to the 'deleted' playlist."""
    if not candidates:
        return

    revision, _, existing_ids = await fetch_playlist(api, deleted_kind)

    # Skip tracks already in deleted playlist
    to_add = [c for c in candidates if c.ym_id not in existing_ids]
    if not to_add:
        out(f"  {D}All failed tracks already in deleted playlist{C}")
        return

    add_tracks = [{"id": c.ym_id, "albumId": c.album_id} for c in to_add]
    try:
        new_rev = await add_to_playlist(api, deleted_kind, revision, add_tracks)
        out(f"  {Y}Moved {len(to_add)} failed tracks to deleted playlist (rev={new_rev}){C}")
    except httpx.HTTPStatusError as e:
        out(f"  {R}Failed to add to deleted playlist: {e}{C}")


async def get_disliked_ids(api: YmApi) -> set[str]:
    """Fetch user's disliked track IDs."""
    try:
        data = await api.get(f"{YM_BASE}/users/{USER_ID}/dislikes/tracks")
        result = data.get("result", data)
        lib = result.get("library", result)
        tracks = lib.get("tracks", [])
        return {str(t.get("id", "")) for t in tracks if t.get("id")}
    except Exception as e:
        out(f"  {D}Could not fetch dislikes: {e}{C}")
        return set()


async def remove_disliked_from_playlist(
    api: YmApi, kind: str, deleted_kind: str,
) -> int:
    """Remove disliked tracks from playlist, move to deleted. Returns count removed."""
    disliked = await get_disliked_ids(api)
    if not disliked:
        return 0

    revision, _, playlist_ids = await fetch_playlist(api, kind)
    to_remove = [(i, tid) for i, tid in enumerate(playlist_ids) if tid in disliked]

    if not to_remove:
        return 0

    out(f"  {Y}Found {len(to_remove)} disliked tracks in playlist{C}")

    # Move to deleted playlist first
    candidates_for_deleted: list[Candidate] = []
    for _, tid in to_remove:
        candidates_for_deleted.append(Candidate(
            ym_id=tid, album_id="", title=f"disliked:{tid}",
            artists="", duration_ms=0, raw={},
        ))
    await add_to_deleted_playlist(api, deleted_kind, candidates_for_deleted)

    # Delete from main playlist (reverse order to keep indices valid)
    for idx, tid in reversed(to_remove):
        try:
            revision = await delete_from_playlist(api, kind, revision, idx)
            out(f"  {R}-{C} Removed disliked track {tid} (idx={idx})")
        except httpx.HTTPStatusError:
            # Re-fetch after failure (indices may have shifted)
            revision, _, playlist_ids = await fetch_playlist(api, kind)
            for j, pid in enumerate(playlist_ids):
                if pid == tid:
                    revision = await delete_from_playlist(api, kind, revision, j)
                    out(f"  {R}-{C} Removed disliked track {tid} (re-indexed)")
                    break

    return len(to_remove)


async def audit_playlist_tracks(
    api: YmApi, kind: str, deleted_kind: str,
) -> int:
    """Check ALL playlist tracks against audio criteria. Remove failures.

    For tracks without features in DB — downloads + analyzes them first.
    Returns count of removed tracks.
    """
    revision, _, playlist_ids = await fetch_playlist(api, kind)
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
    fail_indices: list[tuple[int, str]] = []  # (index, ym_id)
    audit_total = len(to_check)
    for audit_i, (idx, ym_id, track_id) in enumerate(to_check, 1):
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
                    from app.utils.audio.pipeline import extract_all_features
                    loop = asyncio.get_event_loop()
                    feats = await loop.run_in_executor(
                        None, extract_all_features, file_path,
                    )
                    # Save to DB
                    async with session_factory() as session:
                        from app.repositories.audio_features import AudioFeaturesRepository
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
            progress_finish(progress_bar(
                audit_i, audit_total,
                label=f"{R}FAIL{C} #{track_id}: {', '.join(reasons)}",
            ))
        else:
            progress_finish(progress_bar(
                audit_i, audit_total,
                label=f"{G}OK{C} #{track_id}",
            ))

    if not fail_indices:
        return 0

    # Move to deleted playlist
    candidates_for_deleted = [
        Candidate(ym_id=ym_id, album_id="", title=f"audit:{ym_id}",
                  artists="", duration_ms=0, raw={})
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
            revision, _, current_ids = await fetch_playlist(api, kind)
            for j, pid in enumerate(current_ids):
                if pid == ym_id:
                    revision = await delete_from_playlist(api, kind, revision, j)
                    removed += 1
                    out(f"  {R}-{C} Removed audit-failed track {ym_id} (re-indexed)")
                    break

    return removed


# ── Core pipeline steps ─────────────────────────────────────────────────────


async def get_similar_candidates(api: YmApi, seed_id: str,
                                 seen: set[str], batch: int) -> list[Candidate]:
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

        candidates.append(Candidate(
            ym_id=tid,
            album_id=album_id,
            title=tr.get("title", "?"),
            artists=artists,
            duration_ms=dur,
            raw=tr,
        ))

        if len(candidates) >= batch:
            break

    return candidates


async def import_candidate(candidate: Candidate) -> None:
    """Import candidate to local DB if not exists."""
    async with session_factory() as session:
        prov_row = await session.execute(
            text("SELECT provider_id FROM providers WHERE provider_code = 'yandex'")
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

        session.add(ProviderTrackId(
            track_id=track.track_id,
            provider_id=provider_id,
            provider_track_id=candidate.ym_id,
            provider_country="RU",
        ))
        session.add(YandexMetadata(
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
        ))
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
    """CPU-heavy feature extraction (runs in thread pool)."""
    from app.utils.audio.pipeline import extract_all_features
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
    async with sem:
        loop = asyncio.get_event_loop()
        try:
            feats = await loop.run_in_executor(None, _extract_sync, str(candidate.file_path))
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
        from app.repositories.audio_features import AudioFeaturesRepository
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


# ── Main loop ────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Fill & verify YM techno playlist")
    parser.add_argument("--kind", default="1280", help="Playlist kind ID")
    parser.add_argument("--target", type=int, default=0, help="Target track count (0 = unlimited)")
    parser.add_argument("--batch", type=int, default=5, help="Candidates per seed")
    parser.add_argument("--workers", type=int, default=4, help="Parallel analysis workers")
    parser.add_argument("--max-rounds", type=int, default=0, help="Max seed rounds (0 = unlimited)")
    args = parser.parse_args()

    if not settings.yandex_music_token:
        raise RuntimeError("YANDEX_MUSIC_TOKEN not set")

    await init_db()
    LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    # Lower process priority
    try:
        os.nice(10)
    except OSError:
        pass

    api = YmApi(settings.yandex_music_token)
    ym_client = YandexMusicClient(token=settings.yandex_music_token)
    sem = asyncio.Semaphore(args.workers)
    seen_ids: set[str] = set()
    seed_used: set[str] = set()
    total_added = 0
    total_rejected = 0

    out(f"{B}{'=' * 60}{C}")
    out(f"{B}  Fill & Verify Pipeline{C}")
    target_str = str(args.target) if args.target else "∞"
    out(f"{B}  Playlist: {USER_ID}/{args.kind}  Target: {target_str}  Workers: {args.workers}{C}")
    out(f"{B}{'=' * 60}{C}")

    # Get source playlist name and find/create deleted playlist
    pl_data = await api.get(f"{YM_BASE}/users/{USER_ID}/playlists/{args.kind}")
    pl_result = pl_data.get("result", pl_data)
    source_name = pl_result.get("title", f"Playlist {args.kind}")
    deleted_kind = await get_or_create_deleted_playlist(api, source_name)

    # Pre-load disliked tracks into seen_ids to never re-add them
    disliked_ids = await get_disliked_ids(api)
    if disliked_ids:
        seen_ids.update(disliked_ids)
        out(f"  {D}Loaded {len(disliked_ids)} disliked tracks into blocklist{C}")

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

    try:
        round_num = 0
        while not shutdown:
            round_num += 1
            if args.max_rounds and round_num > args.max_rounds:
                out(f"\n  {Y}Max rounds ({args.max_rounds}) reached{C}")
                break
            # ── Fetch current state ──────────────────────────────────────
            revision, track_count, playlist_ids = await fetch_playlist(api, args.kind)
            seen_ids.update(playlist_ids)

            # ── Remove disliked tracks ─────────────────────────────────
            removed = await remove_disliked_from_playlist(api, args.kind, deleted_kind)
            if removed:
                revision, track_count, playlist_ids = await fetch_playlist(api, args.kind)
                total_rejected += removed

            # ── Audit: verify all playlist tracks pass criteria ────────
            if round_num == 1:  # full audit on first round only
                audit_removed = await audit_playlist_tracks(
                    api, args.kind, deleted_kind,
                )
                if audit_removed:
                    revision, track_count, playlist_ids = await fetch_playlist(api, args.kind)
                    total_rejected += audit_removed
                    out(f"  {Y}Audit removed {audit_removed} tracks{C}")

            out(f"\n{CY}{B}{'=' * 60}{C}")
            out(f"{CY}{B}  Round {round_num}  |  {track_count}/{target_str} tracks  |  "
                f"rev={revision}  |  +{total_added} -{total_rejected}{C}")
            out(f"{CY}{'=' * 60}{C}")

            if args.target and track_count >= args.target:
                out(f"\n  {G}{B}Target reached! {track_count} tracks{C}")
                break

            # ── Pick seed ────────────────────────────────────────────────
            available_seeds = [tid for tid in playlist_ids if tid not in seed_used]
            if not available_seeds:
                seed_used.clear()
                available_seeds = playlist_ids
            seed_id = random.choice(available_seeds)
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
                    progress_finish(progress_bar(dl_i, dl_total, label=f"{G}+{C} {sz}KB {cand.title}"))
                else:
                    progress_finish(progress_bar(dl_i, dl_total, label=f"{R}!{C} {cand.title}"))
                await asyncio.sleep(REQUEST_DELAY)

            # ── Phase 4: Audio analysis (parallel, streaming output) ────
            phase_header(4, f"Audio analysis ({args.workers} workers)")
            passed: list[Candidate] = []
            failed: list[Candidate] = []
            an_total = len(download_ok)
            an_done = 0

            async def _analyze_and_report(cand: Candidate) -> None:
                nonlocal total_rejected, an_done
                progress_write(progress_bar(an_done, an_total, label=f"♫ {D}{cand.title}{C}"))
                await analyze_candidate(cand, sem)
                an_done += 1
                if cand.audio_ok:
                    bpm_s = "?"
                    lufs_s = "?"
                    mood_str = ""
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
                            try:
                                from app.utils.audio.mood_classifier import classify_track
                                mc = classify_track(
                                    bpm=feat.bpm,
                                    lufs_i=feat.lufs_i,
                                    kick_prominence=feat.kick_prominence or 0.5,
                                    spectral_centroid_mean=feat.centroid_mean_hz or 2000,
                                    onset_rate=feat.onset_rate_mean or 4.0,
                                    hp_ratio=feat.hp_ratio or 0.5,
                                )
                                mood_str = f" [{mc.mood.value}]"
                            except Exception:
                                pass
                    passed.append(cand)
                    progress_finish(progress_bar(
                        an_done, an_total,
                        label=f"{G}PASS{C} {cand.title} {D}BPM={bpm_s} LUFS={lufs_s}{mood_str}{C}",
                    ))
                else:
                    failed.append(cand)
                    progress_finish(progress_bar(
                        an_done, an_total,
                        label=f"{R}FAIL{C} {cand.title} {D}{', '.join(cand.fail_reasons)}{C}",
                    ))
                    total_rejected += 1

            tasks = [_analyze_and_report(cand) for cand in download_ok]
            await asyncio.gather(*tasks)

            # ── Phase 4b: Move failed to deleted playlist ──────────────
            if failed:
                await add_to_deleted_playlist(api, deleted_kind, failed)

            # ── Phase 5: Add passed to playlist ──────────────────────────
            if passed:
                phase_header(5, f"Add {len(passed)} verified tracks to playlist")
                batch_to_add = passed
                if args.target:
                    remaining = args.target - track_count
                    batch_to_add = passed[:remaining]
                add_tracks = [{"id": c.ym_id, "albumId": c.album_id} for c in batch_to_add]

                try:
                    revision = await add_to_playlist(api, args.kind, revision, add_tracks)
                    total_added += len(batch_to_add)
                    out(f"  {G}{B}Added {len(batch_to_add)} tracks! rev={revision}{C}")
                    for c in batch_to_add:
                        out(f"  {G}+{C} {c.artists} -- {c.title}")
                except httpx.HTTPStatusError as e:
                    out(f"  {R}Failed to add: {e}{C}")
            else:
                out(f"\n  {Y}No tracks passed verification this round{C}")

        # ── Final summary ────────────────────────────────────────────────
        try:
            revision, track_count, _ = await fetch_playlist(api, args.kind)
        except Exception:
            track_count = "?"
            revision = "?"
        out(f"\n{B}{'=' * 60}{C}")
        out(f"{G}{B}  DONE: {track_count}/{target_str} tracks  |  rev={revision}{C}")
        out(f"{G}{B}  Added: {total_added}  |  Rejected: {total_rejected}  |  Rounds: {round_num}{C}")
        out(f"{B}{'=' * 60}{C}")

    finally:
        await api.close()
        await ym_client.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
