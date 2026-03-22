"""DRY response envelope wrappers for MCP tools.

Every CRUD tool returns a Pydantic model with the same structure.
These helpers add LibraryStats + PaginationInfo automatically.

FastMCP automatically converts Pydantic return values to
structuredContent in the MCP protocol response.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    entities: Sequence[BaseModel],
    total: int,
    offset: int,
    limit: int,
    session: AsyncSession,
) -> EntityListResponse:
    """Wrap a list of entities with library stats + pagination."""
    library = await get_library_stats(session)
    has_more = offset + limit < total
    next_cursor = encode_cursor(offset=offset + limit) if has_more else None

    return EntityListResponse(
        results=[e.model_dump(mode="json", exclude_none=True) for e in entities],
        total=total,
        library=library,
        pagination=PaginationInfo(limit=limit, has_more=has_more, cursor=next_cursor),
    )


async def wrap_detail(
    entity: BaseModel,
    session: AsyncSession,
) -> EntityDetailResponse:
    """Wrap a single entity with library context."""
    library = await get_library_stats(session)

    return EntityDetailResponse(
        result=entity.model_dump(mode="json", exclude_none=True),
        library=library,
    )


async def wrap_action(
    *,
    success: bool,
    message: str,
    session: AsyncSession,
    result: BaseModel | None = None,
) -> ActionResponse:
    """Wrap a create/update/delete confirmation with library context."""
    library = await get_library_stats(session)

    return ActionResponse(
        success=success,
        message=message,
        result=result.model_dump(mode="json", exclude_none=True) if result else None,
        library=library,
    )
