"""Session state helpers for MCP workflow continuity.

Provides typed save/get for common workflow artifacts.
Handles None return from ctx.get_state() (no default= parameter).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

_KEY_LAST_BUILD = "last_build"
_KEY_LAST_PLAYLIST = "last_playlist"
_KEY_LAST_EXPORT = "last_export"


async def save_build_result(
    ctx: Context,
    *,
    set_id: int,
    version_id: int,
    quality: float,
) -> None:
    """Save build result to session state."""
    await ctx.set_state(
        _KEY_LAST_BUILD,
        {"set_id": set_id, "version_id": version_id, "quality": quality},
    )


async def get_last_build(ctx: Context) -> dict[str, Any] | None:
    """Get last build result. Returns None if not set."""
    result = await ctx.get_state(_KEY_LAST_BUILD)
    return result if isinstance(result, dict) else None


async def save_playlist_context(
    ctx: Context,
    *,
    playlist_id: int,
    name: str,
    track_count: int,
) -> None:
    """Save playlist context for workflow continuity."""
    await ctx.set_state(
        _KEY_LAST_PLAYLIST,
        {"playlist_id": playlist_id, "name": name, "track_count": track_count},
    )


async def get_last_playlist(ctx: Context) -> dict[str, Any] | None:
    """Get last playlist context. Returns None if not set."""
    result = await ctx.get_state(_KEY_LAST_PLAYLIST)
    return result if isinstance(result, dict) else None


async def save_export_config(
    ctx: Context,
    *,
    set_id: int,
    format: str,
    track_count: int,
) -> None:
    """Save export config for repeat exports."""
    await ctx.set_state(
        _KEY_LAST_EXPORT,
        {"set_id": set_id, "format": format, "track_count": track_count},
    )


async def get_last_export(ctx: Context) -> dict[str, Any] | None:
    """Get last export config. Returns None if not set."""
    result = await ctx.get_state(_KEY_LAST_EXPORT)
    return result if isinstance(result, dict) else None
