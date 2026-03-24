"""Download tools for DJ workflow MCP server."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.mcp.dependencies import get_session, get_ym_client
from app.clients.yandex_music.downloader import DownloadResult, DownloadService
from app.clients.yandex_music import YandexMusicClient


def register_download_tools(mcp: FastMCP) -> None:
    """Register download tools on the MCP server."""

    @mcp.tool(
        name="download_tracks",
        description="Download MP3 files for tracks from Yandex Music to iCloud library",
        tags={"download", "yandex"},
        annotations={"readonly": False},
        timeout=600,
    )
    async def download_tracks(
        track_ids: list[int],
        ctx: Context,
        prefer_bitrate: int = 320,
        session: AsyncSession = Depends(get_session),
        ym_client: YandexMusicClient = Depends(get_ym_client),
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
        library_path = Path(settings.dj_library_path).expanduser()

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
