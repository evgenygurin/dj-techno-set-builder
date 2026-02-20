"""Session state helpers for DJ workflow continuity.

Uses FastMCP's ctx.set_state()/ctx.get_state() to persist data
across MCP requests within a single session. Enables "continue
where I left off" patterns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

# State keys
_LAST_BUILD = "dj:last_build"
_LAST_PLAYLIST = "dj:last_playlist"
_LAST_EXPORT = "dj:last_export"


async def save_build_result(
    ctx: Context,
    *,
    set_id: int,
    version_id: int,
    track_count: int,
) -> None:
    """Save build result for follow-up operations (score, export)."""
    await ctx.set_state(
        _LAST_BUILD,
        {"set_id": set_id, "version_id": version_id, "track_count": track_count},
    )


async def get_last_build(ctx: Context) -> dict[str, Any] | None:
    """Retrieve the last build result from session state."""
    result: dict[str, Any] | None = await ctx.get_state(_LAST_BUILD)
    return result


async def save_playlist_context(
    ctx: Context,
    *,
    playlist_id: int,
    playlist_name: str,
) -> None:
    """Save current playlist context for implicit references."""
    await ctx.set_state(
        _LAST_PLAYLIST,
        {"playlist_id": playlist_id, "playlist_name": playlist_name},
    )


async def get_last_playlist(ctx: Context) -> dict[str, Any] | None:
    """Retrieve the last playlist context from session state."""
    result: dict[str, Any] | None = await ctx.get_state(_LAST_PLAYLIST)
    return result


async def save_export_config(
    ctx: Context,
    *,
    format: str,
    set_id: int,
    version_id: int,
) -> None:
    """Save last export configuration for repeat exports."""
    await ctx.set_state(
        _LAST_EXPORT,
        {"format": format, "set_id": set_id, "version_id": version_id},
    )


async def get_last_export(ctx: Context) -> dict[str, Any] | None:
    """Retrieve the last export configuration."""
    result: dict[str, Any] | None = await ctx.get_state(_LAST_EXPORT)
    return result
