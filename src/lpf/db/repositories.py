"""Database repositories — CRUD operations for ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lpf.db.models import (
    ArtifactModel,
    CostEventModel,
    RunEventModel,
    RunModel,
    SourceModel,
)


class RunRepository:
    """CRUD for factory runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: RunModel) -> RunModel:
        self._session.add(run)
        await self._session.commit()
        return run

    async def get(self, run_id: str) -> RunModel | None:
        result = await self._session.execute(select(RunModel).where(RunModel.id == run_id))
        return result.scalar_one_or_none()

    async def update_status(self, run_id: str, status: str, stage: str | None = None) -> None:
        run = await self.get(run_id)
        if run is not None:
            run.status = status
            if stage is not None:
                run.current_stage = stage
            run.updated_at = datetime.now(UTC)
            await self._session.commit()

    async def list_runs(self, limit: int = 50) -> list[RunModel]:
        result = await self._session.execute(
            select(RunModel).order_by(RunModel.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


class EventRepository:
    """CRUD for run events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, event: RunEventModel) -> RunEventModel:
        self._session.add(event)
        await self._session.commit()
        return event

    async def complete(self, event_id: str, output_summary: str | None = None) -> None:
        result = await self._session.execute(
            select(RunEventModel).where(RunEventModel.id == event_id)
        )
        event = result.scalar_one_or_none()
        if event is not None:
            event.status = "completed"
            event.completed_at = datetime.now(UTC)
            if output_summary is not None:
                event.output_summary = output_summary
            await self._session.commit()

    async def fail(self, event_id: str, error: str) -> None:
        result = await self._session.execute(
            select(RunEventModel).where(RunEventModel.id == event_id)
        )
        event = result.scalar_one_or_none()
        if event is not None:
            event.status = "failed"
            event.error = error
            event.completed_at = datetime.now(UTC)
            await self._session.commit()

    async def list_for_run(self, run_id: str) -> list[RunEventModel]:
        result = await self._session.execute(
            select(RunEventModel).where(RunEventModel.run_id == run_id)
        )
        return list(result.scalars().all())


class ArtifactRepository:
    """CRUD for artifacts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, artifact: ArtifactModel) -> ArtifactModel:
        self._session.add(artifact)
        await self._session.commit()
        return artifact

    async def get(self, artifact_id: str) -> ArtifactModel | None:
        result = await self._session.execute(
            select(ArtifactModel).where(ArtifactModel.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def list_for_run(self, run_id: str) -> list[ArtifactModel]:
        result = await self._session.execute(
            select(ArtifactModel).where(ArtifactModel.run_id == run_id)
        )
        return list(result.scalars().all())

    async def store_pydantic(self, run_id: str, artifact) -> ArtifactModel:
        """Store a Pydantic model as an artifact."""
        from lpf.domain.identity import compute_content_hash

        model = ArtifactModel(
            id=artifact.id,
            run_id=run_id,
            artifact_type=artifact.artifact_type,
            schema_version=artifact.schema_version,
            status=artifact.status,
            content_hash=compute_content_hash(artifact),
            data_json=artifact.model_dump_json(),
        )
        return await self.create(model)


class CostRepository:
    """CRUD for cost events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, cost: CostEventModel) -> CostEventModel:
        self._session.add(cost)
        await self._session.commit()
        return cost

    async def total_for_run(self, run_id: str) -> float:
        result = await self._session.execute(
            select(CostEventModel).where(CostEventModel.run_id == run_id)
        )
        events = result.scalars().all()
        return sum(e.estimated_cost for e in events)


class SourceRepository:
    """CRUD for verified sources."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, source: SourceModel) -> SourceModel:
        self._session.add(source)
        await self._session.commit()
        return source

    async def list_for_run(self, run_id: str) -> list[SourceModel]:
        result = await self._session.execute(
            select(SourceModel).where(SourceModel.run_id == run_id)
        )
        return list(result.scalars().all())
