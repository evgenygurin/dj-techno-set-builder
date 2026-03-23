from datetime import UTC, datetime

from app.models.runs import FeatureExtractionRun, TransitionRun
from app.infrastructure.repositories.base import BaseRepository


class FeatureRunRepository(BaseRepository[FeatureExtractionRun]):
    model = FeatureExtractionRun

    async def mark_completed(self, run_id: int) -> FeatureExtractionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"FeatureExtractionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="completed",
            completed_at=datetime.now(UTC),
        )

    async def mark_failed(self, run_id: int) -> FeatureExtractionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"FeatureExtractionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="failed",
            completed_at=datetime.now(UTC),
        )


class TransitionRunRepository(BaseRepository[TransitionRun]):
    model = TransitionRun

    async def mark_completed(self, run_id: int) -> TransitionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"TransitionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="completed",
            completed_at=datetime.now(UTC),
        )

    async def mark_failed(self, run_id: int) -> TransitionRun:
        run = await self.get_by_id(run_id)
        if not run:
            msg = f"TransitionRun {run_id} not found"
            raise ValueError(msg)
        return await self.update(
            run,
            status="failed",
            completed_at=datetime.now(UTC),
        )
