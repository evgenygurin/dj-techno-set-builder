"""Camelot wheel harmonic compatibility scoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.repositories.harmony import KeyEdgeRepository
from app.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CamelotLookupService(BaseService):
    """Builds and caches Camelot wheel compatibility lookup table."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__()
        self.session = session
        self._lookup: dict[tuple[int, int], float] = {}
        self._built = False

    async def build_lookup_table(self) -> dict[tuple[int, int], float]:
        """Build lookup table from key_edges DB data.

        Returns:
            Dict mapping (from_key_code, to_key_code) → compatibility score [0, 1]
        """
        if self._built:
            return self._lookup

        if self.session is None:
            # Use pitch-class overlap scoring (no DB needed)
            from app.utils.audio.camelot import build_pitch_class_lookup

            self._lookup = build_pitch_class_lookup()
            self._built = True
            return self._lookup

        repo = KeyEdgeRepository(self.session)
        edges = await repo.list_all()

        # Build lookup from DB weights
        for edge in edges:
            self._lookup[(edge.from_key_code, edge.to_key_code)] = edge.weight

        # Ensure all 24x24 pairs exist — use pitch-class overlap as fallback
        from app.utils.audio.camelot import camelot_score

        for i in range(24):
            for j in range(24):
                if (i, j) not in self._lookup:
                    self._lookup[(i, j)] = camelot_score(i, j)

        self._built = True
        return self._lookup

    def get_score(self, from_key: int, to_key: int) -> float:
        """Get harmonic compatibility score for key transition.

        Args:
            from_key: Source key code (0-23)
            to_key: Target key code (0-23)

        Returns:
            Compatibility score [0, 1], or 0.5 if not in lookup
        """
        if not self._built:
            # If not built, return default
            if from_key == to_key:
                return 1.0
            return 0.5

        return self._lookup.get((from_key, to_key), 0.5)
