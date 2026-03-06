"""TrackMapper — maps local track IDs to platform track IDs via DB."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import ProviderTrackId
from app.models.providers import Provider


class DbTrackMapper:
    """Maps between local track IDs and platform track IDs.

    Uses the ``providers`` + ``provider_track_ids`` tables for lookups.
    Provider is identified by ``provider_code`` column.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def local_to_platform(self, track_ids: list[int], platform: str) -> dict[int, str]:
        """Map local track IDs to platform track IDs.

        Args:
            track_ids: Local DB track IDs.
            platform: Provider code (e.g. "yandex_music", "spotify").

        Returns:
            Dict of {local_track_id: platform_track_id}.
            Missing mappings are omitted.
        """
        if not track_ids:
            return {}

        stmt = (
            select(ProviderTrackId.track_id, ProviderTrackId.provider_track_id)
            .join(Provider)
            .where(
                Provider.provider_code == platform,
                ProviderTrackId.track_id.in_(track_ids),
            )
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return {row[0]: row[1] for row in rows}

    async def platform_to_local(
        self, platform_ids: list[str], platform: str
    ) -> dict[str, int | None]:
        """Map platform track IDs to local track IDs.

        Args:
            platform_ids: Platform-specific track IDs.
            platform: Provider code.

        Returns:
            Dict of {platform_track_id: local_track_id | None}.
            All input IDs present in output; None means not found.
        """
        if not platform_ids:
            return {}

        stmt = (
            select(ProviderTrackId.provider_track_id, ProviderTrackId.track_id)
            .join(Provider)
            .where(
                Provider.provider_code == platform,
                ProviderTrackId.provider_track_id.in_(platform_ids),
            )
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        found: dict[str, int] = {row[0]: row[1] for row in rows}

        # Ensure all input IDs are in output
        return {pid: found.get(pid) for pid in platform_ids}
