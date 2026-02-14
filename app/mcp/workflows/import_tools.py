"""Import tools for DJ workflow MCP server."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.mcp.types import ImportResult


def register_import_tools(mcp: FastMCP) -> None:
    """Register import tools on the MCP server."""

    @mcp.tool(tags={"import"})
    async def import_playlist(
        source: str,
        playlist_id: str,
        ctx: Context,
    ) -> ImportResult:
        """Import a playlist from an external source into the local database.

        Currently supported sources: "yandex".
        This is a stub — the full import pipeline (fetch metadata,
        create tracks, enrich audio features) requires multiple steps
        that are not yet consolidated into a single service method.

        Args:
            source: Source platform name (e.g. "yandex").
            playlist_id: Playlist identifier on the source platform.
        """
        supported = {"yandex"}
        if source.lower() not in supported:
            raise ValueError(
                f"Unsupported source '{source}'. Supported: {', '.join(sorted(supported))}"
            )

        await ctx.info(
            f"Import from '{source}' playlist {playlist_id} is not yet "
            "automated end-to-end.  Manual steps required:\n"
            "1. Use ym_search_tracks / ym_fetch_tracks to get metadata\n"
            "2. Create tracks via the REST API (POST /api/v1/tracks)\n"
            "3. Add tracks to a local playlist\n"
            "4. Run audio analysis on each track"
        )

        return ImportResult(
            playlist_id=0,
            imported_count=0,
            skipped_count=0,
            enriched_count=0,
        )

    @mcp.tool(tags={"import"})
    async def import_tracks(
        track_ids: list[int],
        ctx: Context,
    ) -> ImportResult:
        """Import specific tracks by their Yandex Music IDs.

        This is a stub — fetching tracks from Yandex Music and persisting
        them requires coordinating the YM client, TrackService, and
        audio analysis pipeline.

        Args:
            track_ids: List of Yandex Music track IDs to import.
        """
        if not track_ids:
            raise ValueError("track_ids must not be empty")

        await ctx.info(
            f"Import of {len(track_ids)} tracks is not yet automated.  "
            "Manual steps required:\n"
            "1. Use ym_fetch_tracks with the given IDs\n"
            "2. Create tracks via the REST API\n"
            "3. Run audio analysis on imported tracks"
        )

        return ImportResult(
            playlist_id=0,
            imported_count=0,
            skipped_count=len(track_ids),
            enriched_count=0,
        )
