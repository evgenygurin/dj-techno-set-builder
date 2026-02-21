"""Set CRUD tools for DJ workflow MCP server.

list_sets — paginated list with optional text search
get_set — single set by ref with detail stats
create_set — create new set, optionally populated with tracks
update_set — update set fields
delete_set — delete set
get_set_tracks — all tracks of a version with BPM/key/LUFS
list_set_versions — version history with track count and score
"""

from __future__ import annotations

import contextlib
import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import set_to_summary
from app.mcp.dependencies import get_features_service, get_session, get_track_service
from app.mcp.entity_finder import SetFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types import (
    SetCheatSheet,
    SetDetail,
    SetTrackItem,
    SetVersionSummary,
    TransitionSummary,
)
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.schemas.sets import DjSetCreate, DjSetItemCreate, DjSetUpdate, DjSetVersionCreate
from app.services.features import AudioFeaturesService
from app.services.sets import DjSetService
from app.services.tracks import TrackService
from app.utils.audio.camelot import key_code_to_camelot


def _make_svc(session: AsyncSession) -> DjSetService:
    return DjSetService(
        DjSetRepository(session),
        DjSetVersionRepository(session),
        DjSetItemRepository(session),
    )


async def _build_set_detail(set_id: int, session: AsyncSession) -> SetDetail | None:
    """Build SetDetail with version and track stats."""
    svc = _make_svc(session)
    try:
        set_read = await svc.get(set_id)
    except Exception:
        return None

    versions = await svc.list_versions(set_id)
    track_count = 0
    latest_version_id = None
    latest_score = None

    if versions.items:
        latest = versions.items[-1]
        latest_version_id = latest.set_version_id
        latest_score = latest.score
        items = await svc.list_items(latest.set_version_id)
        track_count = items.total

    return SetDetail(
        ref=f"local:{set_read.set_id}",
        name=set_read.name,
        version_count=versions.total,
        track_count=track_count,
        description=set_read.description,
        template_name=set_read.template_name,
        target_bpm_min=set_read.target_bpm_min,
        target_bpm_max=set_read.target_bpm_max,
        latest_version_id=latest_version_id,
        latest_score=latest_score,
    )


async def _get_set_tracks_impl(
    set_id: int,
    version_id: int | None,
    session: AsyncSession,
    features_svc: AudioFeaturesService,
    track_svc: TrackService,
) -> list[SetTrackItem]:
    """Shared implementation for get_set_tracks and get_set_cheat_sheet."""
    svc = _make_svc(session)

    # Resolve version
    if version_id is None:
        versions = await svc.list_versions(set_id)
        if not versions.items:
            return []
        version_id = max(v.set_version_id for v in versions.items)

    items_list = await svc.list_items(version_id, offset=0, limit=500)
    items = sorted(items_list.items, key=lambda i: i.sort_index)

    # Batch fetch artists
    track_ids = [item.track_id for item in items]
    artists_map = await track_svc.get_track_artists(track_ids)

    result: list[SetTrackItem] = []
    for pos, item in enumerate(items, 1):
        entry = SetTrackItem(
            position=pos,
            track_id=item.track_id,
            title=f"Track {item.track_id}",
            pinned=item.pinned,
        )
        with contextlib.suppress(Exception):
            track = await track_svc.get(item.track_id)
            entry.title = track.title
            entry.duration_s = track.duration_ms // 1000
        entry.artists = ", ".join(artists_map.get(item.track_id, []))
        with contextlib.suppress(Exception):
            feat = await features_svc.get_latest(item.track_id)
            entry.bpm = feat.bpm
            entry.energy_lufs = feat.lufs_i
            with contextlib.suppress(ValueError):
                entry.key = key_code_to_camelot(feat.key_code)
        result.append(entry)

    return result


def register_set_tools(mcp: FastMCP) -> None:
    """Register Set CRUD tools on the MCP server."""

    @mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True})
    async def list_sets(
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """List DJ sets with optional text search.

        Args:
            limit: Max results per page (default 20, max 100).
            cursor: Pagination cursor from previous response.
            search: Optional text to filter by set name.
        """
        offset, clamped = paginate_params(cursor=cursor, limit=limit)
        repo = DjSetRepository(session)

        if search:
            sets, total = await repo.search_by_name(search, offset=offset, limit=clamped)
        else:
            sets, total = await repo.list(offset=offset, limit=clamped)

        stats = await repo.get_stats_batch([s.set_id for s in sets])
        summaries = [
            set_to_summary(
                s,
                version_count=stats.get(s.set_id, (0, 0))[0],
                track_count=stats.get(s.set_id, (0, 0))[1],
            )
            for s in sets
        ]
        return await wrap_list(summaries, total, offset, clamped, session)

    @mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True})
    async def get_set(
        set_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Get set details by ref. Text refs return match list.

        Args:
            set_ref: Set reference — local:3, 3, or text query.
        """
        ref = parse_ref(set_ref)

        if ref.ref_type == RefType.LOCAL and ref.local_id is not None:
            detail = await _build_set_detail(ref.local_id, session)
            if detail is None:
                return json.dumps({"error": "Set not found", "ref": set_ref})
            return await wrap_detail(detail, session)

        if ref.ref_type == RefType.TEXT:
            repo = DjSetRepository(session)
            finder = SetFinder(repo)
            found = await finder.find(ref, limit=20)
            return await wrap_list(found.entities, len(found.entities), 0, 20, session)

        return json.dumps({"error": "Platform refs not yet supported", "ref": set_ref})

    @mcp.tool(tags={"crud", "set"})
    async def create_set(
        name: str,
        description: str | None = None,
        track_ids: list[int] | None = None,
        template_name: str | None = None,
        source_playlist_id: int | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Create a new DJ set, optionally populated with tracks.

        If track_ids provided, creates set + version + items in one call.
        Use after build_set() to persist the computed result.

        Args:
            name: Set name.
            description: Optional description.
            track_ids: Optional list of track IDs to populate (in order).
            template_name: Optional template name used for generation.
            source_playlist_id: Optional source playlist ID.
        """
        svc = _make_svc(session)

        set_data = DjSetCreate(
            name=name,
            description=description,
            template_name=template_name,
            source_playlist_id=source_playlist_id,
        )
        new_set = await svc.create(set_data)

        if track_ids:
            version = await svc.create_version(
                new_set.set_id,
                DjSetVersionCreate(version_label="v1"),
            )
            for idx, track_id in enumerate(track_ids):
                await svc.add_item(
                    version.set_version_id,
                    DjSetItemCreate(sort_index=idx, track_id=track_id),
                )

        detail = await _build_set_detail(new_set.set_id, session)
        return await wrap_action(
            success=True,
            message=f"Created set local:{new_set.set_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "set"})
    async def update_set(
        set_ref: str,
        name: str | None = None,
        description: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Update set fields by ref.

        Args:
            set_ref: Set reference (must resolve to exact ID).
            name: New name (optional).
            description: New description (optional).
        """
        ref = parse_ref(set_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "update requires exact ref", "ref": set_ref})

        svc = _make_svc(session)
        await svc.update(ref.local_id, DjSetUpdate(name=name, description=description))

        detail = await _build_set_detail(ref.local_id, session)
        return await wrap_action(
            success=True,
            message=f"Updated set local:{ref.local_id}",
            session=session,
            result=detail,
        )

    @mcp.tool(tags={"crud", "set"})
    async def delete_set(
        set_ref: str,
        session: AsyncSession = Depends(get_session),
    ) -> str:
        """Delete a DJ set by ref.

        Args:
            set_ref: Set reference (must resolve to exact ID).
        """
        ref = parse_ref(set_ref)
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return json.dumps({"error": "delete requires exact ref", "ref": set_ref})

        svc = _make_svc(session)
        await svc.delete(ref.local_id)

        return await wrap_action(
            success=True,
            message=f"Deleted set local:{ref.local_id}",
            session=session,
        )

    @mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True}, timeout=60)
    async def get_set_tracks(
        set_ref: str | int,
        version_id: int | None = None,
        session: AsyncSession = Depends(get_session),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        track_svc: TrackService = Depends(get_track_service),
    ) -> list[SetTrackItem]:
        """Get all tracks of a set version with BPM/key/LUFS in one call.

        If version_id is None, uses the latest version automatically.
        Returns tracks in play order with position (1-based), pinned flag,
        and audio features (BPM, Camelot key, LUFS). No separate get_features
        calls needed.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            version_id: Specific version ID, or None for latest.
        """
        ref = parse_ref(str(set_ref))
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return []
        return await _get_set_tracks_impl(
            ref.local_id, version_id, session, features_svc, track_svc
        )

    @mcp.tool(tags={"crud", "set"}, annotations={"readOnlyHint": True})
    async def list_set_versions(
        set_ref: str | int,
        session: AsyncSession = Depends(get_session),
    ) -> list[SetVersionSummary]:
        """List all versions of a DJ set with date, score, and track count.

        Most recent version is last. Use version_id from here to pass to
        score_transitions, get_set_tracks, deliver_set, etc.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
        """
        ref = parse_ref(str(set_ref))
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return []

        svc = _make_svc(session)
        versions = await svc.list_versions(ref.local_id)
        if not versions.items:
            return []

        result: list[SetVersionSummary] = []
        for v in sorted(versions.items, key=lambda x: x.set_version_id):
            items_list = await svc.list_items(v.set_version_id, offset=0, limit=500)
            created = v.created_at.isoformat() if v.created_at else None
            result.append(
                SetVersionSummary(
                    version_id=v.set_version_id,
                    version_label=v.version_label,
                    created_at=created,
                    track_count=items_list.total,
                    score=v.score,
                )
            )
        return result

    @mcp.tool(
        tags={"set", "setbuilder"}, annotations={"readOnlyHint": True}, timeout=120
    )
    async def get_set_cheat_sheet(
        set_ref: str | int,
        version_id: int | None = None,
        session: AsyncSession = Depends(get_session),
        features_svc: AudioFeaturesService = Depends(get_features_service),
        track_svc: TrackService = Depends(get_track_service),
    ) -> SetCheatSheet:
        """Get a complete cheat sheet for a set version: tracks + transitions + summary.

        Returns the same content as cheat_sheet.txt but as a structured MCP
        response without writing any files. Use this to inspect a set before
        running deliver_set. version_id defaults to the latest version if
        not specified.

        Args:
            set_ref: DJ set ref (int, "42", or "local:42").
            version_id: Specific version ID, or None for latest.
        """
        from app.mcp.tools.delivery import (
            _build_transition_summary,
            _generate_cheat_sheet,
            _score_version,
        )

        ref = parse_ref(str(set_ref))
        if ref.ref_type != RefType.LOCAL or ref.local_id is None:
            return SetCheatSheet(
                set_id=0,
                version_id=0,
                set_name="",
                tracks=[],
                transitions=[],
                summary=TransitionSummary(
                    total=0, hard_conflicts=0, weak=0, avg_score=0.0, min_score=0.0
                ),
                text="Error: invalid set ref",
            )

        set_id = ref.local_id
        svc = _make_svc(session)
        dj_set = await svc.get(set_id)

        # Resolve version
        if version_id is None:
            versions = await svc.list_versions(set_id)
            if not versions.items:
                return SetCheatSheet(
                    set_id=set_id,
                    version_id=0,
                    set_name=dj_set.name,
                    tracks=[],
                    transitions=[],
                    summary=TransitionSummary(
                        total=0,
                        hard_conflicts=0,
                        weak=0,
                        avg_score=0.0,
                        min_score=0.0,
                    ),
                    text="No versions found",
                )
            version_id = max(v.set_version_id for v in versions.items)

        # 1. Get tracks
        tracks = await _get_set_tracks_impl(
            set_id, version_id, session, features_svc, track_svc
        )

        # 2. Score transitions
        scores = await _score_version(
            set_id, version_id, svc, features_svc, track_svc
        )
        summary = _build_transition_summary(scores)

        # 3. Build text cheat sheet
        track_dicts = [
            {
                "position": t.position,
                "track_id": t.track_id,
                "title": t.title,
                "bpm": t.bpm,
                "key": t.key,
                "lufs": t.energy_lufs,
                "duration_s": t.duration_s,
            }
            for t in tracks
        ]
        text = _generate_cheat_sheet(dj_set.name, track_dicts, scores)

        # 4. Derived stats
        bpms = [t.bpm for t in tracks if t.bpm is not None]
        keys = [t.key for t in tracks if t.key is not None]
        total_s = sum(t.duration_s or 0 for t in tracks)

        return SetCheatSheet(
            set_id=set_id,
            version_id=version_id,
            set_name=dj_set.name,
            tracks=tracks,
            transitions=scores,
            summary=summary,
            bpm_range=(min(bpms), max(bpms)) if bpms else None,
            harmonic_chain=keys,
            duration_min=total_s // 60,
            text=text,
        )
