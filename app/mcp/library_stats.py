"""Library-wide statistics for MCP response envelope.

Delegates to app.services.library_stats for actual DB queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.mcp.types import LibraryStats
from app.services.library_stats import get_library_stats as _get_stats

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_library_stats(session: AsyncSession) -> LibraryStats:
    """Get library-wide counts, wrapped in MCP response type."""
    stats = await _get_stats(session)
    return LibraryStats(**stats)
