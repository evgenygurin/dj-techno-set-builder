"""DRY response envelope wrappers for MCP tools.

Every CRUD tool returns JSON with the same structure.
These helpers add LibraryStats + PaginationInfo automatically.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.mcp.library_stats import get_library_stats
from app.mcp.pagination import encode_cursor
from app.mcp.types import (
    ActionResponse,
    EntityDetailResponse,
    EntityListResponse,
    PaginationInfo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def wrap_list(
    entities: list[BaseModel],
    total: int,
    offset: int,
    limit: int,
    session: AsyncSession,
) -> str:
    """Wrap a list of entities with library stats + pagination."""
    library = await get_library_stats(session)
    has_more = offset + limit < total
    next_cursor = encode_cursor(offset=offset + limit) if has_more else None

    resp = EntityListResponse(
        results=[e.model_dump(exclude_none=True) for e in entities],
        total=total,
        library=library,
        pagination=PaginationInfo(limit=limit, has_more=has_more, cursor=next_cursor),
    )
    return json.dumps(resp.model_dump(exclude_none=True), ensure_ascii=False)


async def wrap_detail(
    entity: BaseModel,
    session: AsyncSession,
) -> str:
    """Wrap a single entity with library context."""
    library = await get_library_stats(session)

    resp = EntityDetailResponse(
        result=entity.model_dump(exclude_none=True),
        library=library,
    )
    return json.dumps(resp.model_dump(exclude_none=True), ensure_ascii=False)


async def wrap_action(
    *,
    success: bool,
    message: str,
    session: AsyncSession,
    result: BaseModel | None = None,
) -> str:
    """Wrap a create/update/delete confirmation with library context."""
    library = await get_library_stats(session)

    resp = ActionResponse(
        success=success,
        message=message,
        result=result.model_dump(exclude_none=True) if result else None,
        library=library,
    )
    return json.dumps(resp.model_dump(exclude_none=True), ensure_ascii=False)
