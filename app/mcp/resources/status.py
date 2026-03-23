"""Status and statistics resources for the DJ MCP server.

Provides read-only resources exposing playlist status, catalog stats,
and set summaries via the MCP resource protocol.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from app.mcp.dependencies import get_playlist_service, get_set_service, get_track_service
from app.services.catalog.tracks import TrackService
from app.services.dj.playlists import DjPlaylistService
from app.services.dj.sets import DjSetService


def register_resources(mcp: FastMCP) -> None:
    """Register status and statistics resources on the MCP server."""

    @mcp.resource("playlist://{playlist_id}/status")
    async def playlist_status(
        playlist_id: str,
        playlist_svc: DjPlaylistService = Depends(get_playlist_service),
    ) -> str:
        """Current status of a playlist including track count."""
        pid = int(playlist_id)
        playlist = await playlist_svc.get(pid)
        items_list = await playlist_svc.list_items(pid, offset=0, limit=1)
        return json.dumps(
            {
                "playlist_id": playlist.playlist_id,
                "name": playlist.name,
                "total_tracks": items_list.total,
            }
        )

    @mcp.resource("catalog://stats")
    async def catalog_stats(
        track_svc: TrackService = Depends(get_track_service),
    ) -> str:
        """Overall catalog statistics: total track count."""
        track_list = await track_svc.list(offset=0, limit=1)
        return json.dumps(
            {
                "total_tracks": track_list.total,
            }
        )

    @mcp.resource("set://{set_id}/summary")
    async def set_summary(
        set_id: str,
        set_svc: DjSetService = Depends(get_set_service),
    ) -> str:
        """Summary of a DJ set including version count."""
        sid = int(set_id)
        dj_set = await set_svc.get(sid)
        versions_list = await set_svc.list_versions(sid, offset=0, limit=1)
        return json.dumps(
            {
                "set_id": dj_set.set_id,
                "name": dj_set.name,
                "total_versions": versions_list.total,
            }
        )
