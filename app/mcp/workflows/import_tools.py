"""Import tools for DJ workflow MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.mcp.dependencies import get_session, get_ym_client
from app.mcp.types import ImportResult
from app.services.download import DownloadResult, DownloadService
from app.services.yandex_music_client import YandexMusicClient


def register_import_tools(mcp: FastMCP) -> None:
    """Register import tools on the MCP server."""

    @mcp.tool(tags={"import"})
    async def import_playlist(
        source: str,
        playlist_id: str,
        ctx: Context,
        download_files: bool = False,
    ) -> ImportResult:
        """Import a playlist from an external source into the local database.

        Currently supported sources: "yandex".
        This is a stub — the full import pipeline (fetch metadata,
        create tracks, enrich audio features) requires multiple steps
        that are not yet consolidated into a single service method.

        Args:
            source: Source platform name (e.g. "yandex").
            playlist_id: Playlist identifier on the source platform.
            download_files: If True, download MP3 files after importing tracks.
        """
        supported = {"yandex"}
        if source.lower() not in supported:
            raise ValueError(
                f"Unsupported source '{source}'. Supported: {', '.join(sorted(supported))}"
            )

        await ctx.report_progress(progress=0, total=100)

        download_note = "\n5. Download MP3 files (download_files=True)" if download_files else ""
        await ctx.info(
            f"Import from '{source}' playlist {playlist_id} is not yet "
            "automated end-to-end.  Manual steps required:\n"
            "1. Use ym_search_tracks / ym_fetch_tracks to get metadata\n"
            "2. Create tracks via the REST API (POST /api/v1/tracks)\n"
            "3. Add tracks to a local playlist\n"
            f"4. Run audio analysis on each track{download_note}"
        )

        await ctx.report_progress(progress=100, total=100)
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

        await ctx.report_progress(progress=0, total=len(track_ids))

        await ctx.info(
            f"Import of {len(track_ids)} tracks is not yet automated.  "
            "Manual steps required:\n"
            "1. Use ym_fetch_tracks with the given IDs\n"
            "2. Create tracks via the REST API\n"
            "3. Run audio analysis on imported tracks"
        )

        await ctx.report_progress(progress=len(track_ids), total=len(track_ids))
        return ImportResult(
            playlist_id=0,
            imported_count=0,
            skipped_count=len(track_ids),
            enriched_count=0,
        )

    @mcp.tool(
        name="download_tracks",
        description="Download MP3 files for tracks from Yandex Music to iCloud library",
        tags={"download", "yandex"},
        annotations={"readonly": False},
    )
    async def download_tracks(
        track_ids: list[int],
        prefer_bitrate: int = 320,
        ctx: Context | None = None,
        session: AsyncSession = Depends(get_session),  # noqa: B008
        ym_client: YandexMusicClient = Depends(get_ym_client),  # noqa: B008
    ) -> DownloadResult:
        """Download tracks from Yandex Music to local library.

        Downloads MP3 files and stores them in iCloud library directory.
        Skips tracks that already have files. Returns download statistics.

        Args:
            track_ids: List of track IDs to download
            prefer_bitrate: Preferred bitrate in kbps (default: 320)

        Returns:
            Download statistics (downloaded, skipped, failed counts)

        Example:
            >>> await download_tracks([1, 2, 3], prefer_bitrate=320)
            DownloadResult(downloaded=2, skipped=1, failed=0, ...)
        """
        library_path = Path(settings.dj_library_path)

        download_svc = DownloadService(
            session=session,
            ym_client=ym_client,
            library_path=library_path,
        )

        result = await download_svc.download_tracks_batch(
            track_ids=track_ids,
            prefer_bitrate=prefer_bitrate,
        )

        return result
