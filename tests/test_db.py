"""Tests for the database layer — engine, ORM models, and repositories."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lpf.db.base import close_db, create_engine, init_db
from lpf.db.models import (
    ArtifactModel,
    CostEventModel,
    RunEventModel,
    RunModel,
    SourceModel,
)
from lpf.db.repositories import (
    ArtifactRepository,
    CostRepository,
    EventRepository,
    RunRepository,
    SourceRepository,
)
from lpf.domain.artifact import ArtifactBase
from lpf.domain.identity import new_id

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    eng, _ = create_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await close_db(eng)


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest.fixture
def run() -> RunModel:
    return RunModel(id=new_id(), status="created", product_spec_id=new_id())


@pytest.fixture
def event(run: RunModel) -> RunEventModel:
    return RunEventModel(id=new_id(), run_id=run.id, stage="discovery", status="started")


@pytest.fixture
def cost(run: RunModel) -> CostEventModel:
    return CostEventModel(
        id=new_id(),
        run_id=run.id,
        agent_id="01_product_strategist",
        model="mock",
        input_tokens=100,
        output_tokens=50,
        estimated_cost=0.01,
    )


@pytest.fixture
def source(run: RunModel) -> SourceModel:
    return SourceModel(
        id=new_id(),
        run_id=run.id,
        url="https://arxiv.org/abs/1234",
        title="A Paper",
        domain="arxiv.org",
        authority="academic",
        provider="arxiv",
        verified=True,
    )


class _SampleArtifact(ArtifactBase):
    artifact_type: str = "sample_artifact"
    payload: str = "hello"


# ---------------------------------------------------------------------------
# Tests: engine helpers
# ---------------------------------------------------------------------------


class TestEngine:
    @pytest.mark.asyncio
    async def test_init_creates_tables(self, engine) -> None:
        from sqlalchemy import inspect

        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        assert "runs" in tables
        assert "run_events" in tables
        assert "artifacts" in tables
        assert "cost_events" in tables
        assert "sources" in tables

    @pytest.mark.asyncio
    async def test_create_engine_returns_pair(self) -> None:
        eng, factory = create_engine("sqlite+aiosqlite:///:memory:")
        assert eng is not None
        assert factory is not None
        await close_db(eng)


# ---------------------------------------------------------------------------
# Tests: RunRepository
# ---------------------------------------------------------------------------


class TestRunRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session: AsyncSession, run: RunModel) -> None:
        repo = RunRepository(session)
        await repo.create(run)
        got = await repo.get(run.id)
        assert got is not None
        assert got.id == run.id
        assert got.status == "created"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, session: AsyncSession) -> None:
        repo = RunRepository(session)
        assert await repo.get("does_not_exist") is None

    @pytest.mark.asyncio
    async def test_update_status(self, session: AsyncSession, run: RunModel) -> None:
        repo = RunRepository(session)
        await repo.create(run)
        await repo.update_status(run.id, "running", stage="research")
        got = await repo.get(run.id)
        assert got is not None
        assert got.status == "running"
        assert got.current_stage == "research"

    @pytest.mark.asyncio
    async def test_update_status_missing_is_noop(self, session: AsyncSession) -> None:
        repo = RunRepository(session)
        await repo.update_status("nope", "running")

    @pytest.mark.asyncio
    async def test_update_status_without_stage_keeps_stage(
        self, session: AsyncSession, run: RunModel
    ) -> None:
        repo = RunRepository(session)
        await repo.create(run)
        await repo.update_status(run.id, "running", stage="research")
        await repo.update_status(run.id, "completed")
        got = await repo.get(run.id)
        assert got is not None
        assert got.current_stage == "research"

    @pytest.mark.asyncio
    async def test_list_runs(self, session: AsyncSession) -> None:
        repo = RunRepository(session)
        for _ in range(3):
            await repo.create(RunModel(id=new_id(), status="created"))
        runs = await repo.list_runs()
        assert len(runs) == 3

    @pytest.mark.asyncio
    async def test_list_runs_respects_limit(self, session: AsyncSession) -> None:
        repo = RunRepository(session)
        for _ in range(5):
            await repo.create(RunModel(id=new_id(), status="created"))
        runs = await repo.list_runs(limit=2)
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_iteration_defaults(self, session: AsyncSession, run: RunModel) -> None:
        repo = RunRepository(session)
        await repo.create(run)
        got = await repo.get(run.id)
        assert got is not None
        assert got.iteration == 1
        assert got.max_iterations == 3


# ---------------------------------------------------------------------------
# Tests: EventRepository
# ---------------------------------------------------------------------------


class TestEventRepository:
    @pytest.mark.asyncio
    async def test_create_and_list(
        self, session: AsyncSession, run: RunModel, event: RunEventModel
    ) -> None:
        runs = RunRepository(session)
        await runs.create(run)
        events = EventRepository(session)
        await events.create(event)
        listed = await events.list_for_run(run.id)
        assert len(listed) == 1
        assert listed[0].stage == "discovery"

    @pytest.mark.asyncio
    async def test_complete(
        self, session: AsyncSession, run: RunModel, event: RunEventModel
    ) -> None:
        await RunRepository(session).create(run)
        events = EventRepository(session)
        await events.create(event)
        await events.complete(event.id, output_summary="done")
        listed = await events.list_for_run(run.id)
        assert listed[0].status == "completed"
        assert listed[0].output_summary == "done"
        assert listed[0].completed_at is not None

    @pytest.mark.asyncio
    async def test_fail(self, session: AsyncSession, run: RunModel, event: RunEventModel) -> None:
        await RunRepository(session).create(run)
        events = EventRepository(session)
        await events.create(event)
        await events.fail(event.id, error="boom")
        listed = await events.list_for_run(run.id)
        assert listed[0].status == "failed"
        assert listed[0].error == "boom"

    @pytest.mark.asyncio
    async def test_complete_missing_is_noop(self, session: AsyncSession) -> None:
        await EventRepository(session).complete("nope")

    @pytest.mark.asyncio
    async def test_fail_missing_is_noop(self, session: AsyncSession) -> None:
        await EventRepository(session).fail("nope", "err")

    @pytest.mark.asyncio
    async def test_list_filters_by_run(
        self, session: AsyncSession, run: RunModel, event: RunEventModel
    ) -> None:
        events = EventRepository(session)
        await events.create(event)
        other = RunEventModel(id=new_id(), run_id="other_run", stage="qa")
        await events.create(other)
        assert len(await events.list_for_run(run.id)) == 1
        assert len(await events.list_for_run("other_run")) == 1


# ---------------------------------------------------------------------------
# Tests: ArtifactRepository
# ---------------------------------------------------------------------------


class TestArtifactRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, session: AsyncSession) -> None:
        repo = ArtifactRepository(session)
        artifact = ArtifactModel(id=new_id(), run_id="run1", artifact_type="lesson")
        await repo.create(artifact)
        got = await repo.get(artifact.id)
        assert got is not None
        assert got.artifact_type == "lesson"
        assert got.status == "draft"
        assert got.schema_version == "1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, session: AsyncSession) -> None:
        repo = ArtifactRepository(session)
        assert await repo.get("nope") is None

    @pytest.mark.asyncio
    async def test_list_for_run(self, session: AsyncSession) -> None:
        repo = ArtifactRepository(session)
        await repo.create(ArtifactModel(id=new_id(), run_id="run1", artifact_type="lesson"))
        await repo.create(ArtifactModel(id=new_id(), run_id="run1", artifact_type="quiz"))
        await repo.create(ArtifactModel(id=new_id(), run_id="run2", artifact_type="lesson"))
        assert len(await repo.list_for_run("run1")) == 2
        assert len(await repo.list_for_run("run2")) == 1

    @pytest.mark.asyncio
    async def test_store_pydantic(self, session: AsyncSession) -> None:
        repo = ArtifactRepository(session)
        artifact = _SampleArtifact(payload="world")
        stored = await repo.store_pydantic("run1", artifact)
        assert stored.id == artifact.id
        assert stored.artifact_type == "sample_artifact"
        assert stored.content_hash
        assert stored.data_json is not None
        assert "world" in stored.data_json

    @pytest.mark.asyncio
    async def test_store_pydantic_roundtrip(self, session: AsyncSession) -> None:
        repo = ArtifactRepository(session)
        artifact = _SampleArtifact(payload="roundtrip")
        stored = await repo.store_pydantic("run1", artifact)
        restored = _SampleArtifact.model_validate_json(stored.data_json)
        assert restored.payload == "roundtrip"
        assert restored.id == artifact.id


# ---------------------------------------------------------------------------
# Tests: CostRepository
# ---------------------------------------------------------------------------


class TestCostRepository:
    @pytest.mark.asyncio
    async def test_create(self, session: AsyncSession, cost: CostEventModel) -> None:
        repo = CostRepository(session)
        await repo.create(cost)
        assert cost.input_tokens == 100

    @pytest.mark.asyncio
    async def test_total_for_run(self, session: AsyncSession, cost: CostEventModel) -> None:
        repo = CostRepository(session)
        await repo.create(cost)
        second = CostEventModel(id=new_id(), run_id=cost.run_id, estimated_cost=0.02)
        await repo.create(second)
        total = await repo.total_for_run(cost.run_id)
        assert total == pytest.approx(0.03)

    @pytest.mark.asyncio
    async def test_total_empty_run_is_zero(self, session: AsyncSession) -> None:
        repo = CostRepository(session)
        assert await repo.total_for_run("nothing") == 0.0


# ---------------------------------------------------------------------------
# Tests: SourceRepository
# ---------------------------------------------------------------------------


class TestSourceRepository:
    @pytest.mark.asyncio
    async def test_create_and_list(self, session: AsyncSession, source: SourceModel) -> None:
        repo = SourceRepository(session)
        await repo.create(source)
        listed = await repo.list_for_run(source.run_id)
        assert len(listed) == 1
        assert listed[0].verified is True
        assert listed[0].domain == "arxiv.org"

    @pytest.mark.asyncio
    async def test_list_filters_by_run(self, session: AsyncSession, source: SourceModel) -> None:
        repo = SourceRepository(session)
        await repo.create(source)
        await repo.create(SourceModel(id=new_id(), run_id="other", url="https://x.com"))
        assert len(await repo.list_for_run(source.run_id)) == 1
        assert len(await repo.list_for_run("other")) == 1

    @pytest.mark.asyncio
    async def test_verified_defaults_false(self, session: AsyncSession) -> None:
        repo = SourceRepository(session)
        s = SourceModel(id=new_id(), run_id="run1", url="https://x.com")
        await repo.create(s)
        listed = await repo.list_for_run("run1")
        assert listed[0].verified is False


# ---------------------------------------------------------------------------
# Tests: cross-repository behaviour
# ---------------------------------------------------------------------------


class TestCrossRepository:
    @pytest.mark.asyncio
    async def test_full_run_lifecycle(self, session: AsyncSession) -> None:
        run_repo = RunRepository(session)
        event_repo = EventRepository(session)
        artifact_repo = ArtifactRepository(session)
        cost_repo = CostRepository(session)
        source_repo = SourceRepository(session)

        run = RunModel(id=new_id(), status="created", product_spec_id=new_id())
        await run_repo.create(run)

        event = RunEventModel(id=new_id(), run_id=run.id, stage="discovery")
        await event_repo.create(event)

        artifact = _SampleArtifact()
        await artifact_repo.store_pydantic(run.id, artifact)

        await cost_repo.create(CostEventModel(id=new_id(), run_id=run.id, estimated_cost=0.05))
        await source_repo.create(SourceModel(id=new_id(), run_id=run.id, url="https://a.com"))

        await run_repo.update_status(run.id, "running", stage="discovery")
        await event_repo.complete(event.id, output_summary="ok")
        await run_repo.update_status(run.id, "completed", stage="packaging")

        assert len(await artifact_repo.list_for_run(run.id)) == 1
        assert await cost_repo.total_for_run(run.id) == pytest.approx(0.05)
        assert len(await source_repo.list_for_run(run.id)) == 1
        completed = (await event_repo.list_for_run(run.id))[0]
        assert completed.status == "completed"
        final = await run_repo.get(run.id)
        assert final is not None
        assert final.status == "completed"

    @pytest.mark.asyncio
    async def test_timestamps_are_timezone_aware(
        self, session: AsyncSession, run: RunModel
    ) -> None:
        repo = RunRepository(session)
        await repo.create(run)
        got = await repo.get(run.id)
        assert got is not None
        assert got.created_at.tzinfo is not None
        assert isinstance(got.created_at, datetime)

    @pytest.mark.asyncio
    async def test_updated_at_changes_on_update(self, session: AsyncSession, run: RunModel) -> None:
        repo = RunRepository(session)
        await repo.create(run)
        before = (await repo.get(run.id)).updated_at
        await repo.update_status(run.id, "running")
        after = (await repo.get(run.id)).updated_at
        assert after >= before
        assert datetime.now(UTC) is not None
