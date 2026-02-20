"""Set CRUD tools for DJ workflow MCP server.

list_sets — paginated list with optional text search
get_set — single set by ref with detail stats
create_set — create new set, optionally populated with tracks
update_set — update set fields
delete_set — delete set
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.converters import set_to_summary
from app.mcp.dependencies import get_session
from app.mcp.entity_finder import SetFinder
from app.mcp.pagination import paginate_params
from app.mcp.refs import RefType, parse_ref
from app.mcp.response import wrap_action, wrap_detail, wrap_list
from app.mcp.types import SetDetail
from app.repositories.sets import DjSetItemRepository, DjSetRepository, DjSetVersionRepository
from app.schemas.sets import DjSetCreate, DjSetItemCreate, DjSetUpdate, DjSetVersionCreate
from app.services.sets import DjSetService


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
            set_to_summary(s, version_count=stats.get(s.set_id, (0, 0))[0], track_count=stats.get(s.set_id, (0, 0))[1])
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
