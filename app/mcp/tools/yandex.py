"""Register YandexMusicClient methods as MCP tools.

Uses @tool() decorators on client methods for metadata (tags, annotations).
Adds 'ym_' prefix to tool names to avoid collisions with DJ tools.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.tools import Tool

from app.mcp.dependencies import get_ym_client

_YM_METHODS = [
    "search",
    "search_tracks",
    "fetch_tracks",
    "fetch_tracks_metadata",
    "get_similar_tracks",
    "get_track_supplement",
    "get_album",
    "get_album_with_tracks",
    "fetch_albums",
    "get_artist_tracks",
    "get_artist_albums",
    "get_popular_tracks",
    "get_genres",
    "fetch_playlist",
    "fetch_playlist_tracks",
    "fetch_user_playlists",
    "fetch_playlists_by_ids",
    "get_playlist_recommendations",
    "create_playlist",
    "rename_playlist",
    "set_playlist_visibility",
    "add_tracks_to_playlist",
    "remove_tracks_from_playlist",
    "delete_playlist",
    "get_liked_track_ids",
    "like_tracks",
    "unlike_tracks",
    "get_disliked_track_ids",
    "resolve_download_url",
    "download_track",
]


def register_yandex_tools(mcp: FastMCP) -> None:
    """Register all YandexMusicClient methods as MCP tools with ym_ prefix."""
    client = get_ym_client()
    for name in _YM_METHODS:
        bound_method = getattr(client, name)
        t = Tool.from_function(bound_method, name=f"ym_{name}")
        mcp.add_tool(t)
