import os
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest

from cliova.application.persistence import TickResolver
from cliova.application.scheduling import (
    ScheduledTickService,
    TickRunClaim,
    TickRunStatus,
    TickRunTrigger,
    WorldScheduleStatus,
)
from cliova.infrastructure.persistence.migrations import apply_migrations
from cliova.infrastructure.persistence.postgres import TickConflictError
from cliova.infrastructure.persistence.scheduling import PostgresScheduledWorldRepository
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import SimulationInput, SimulationTime, TickResult, WorldState

pytestmark = pytest.mark.integration

_TABLES = (
    "cliova_world_schedules",
    "cliova_tick_runs",
    "cliova_history_event_causes",
    "cliova_history_events",
    "cliova_completed_ticks",
    "cliova_queued_inputs",
    "cliova_world_snapshots",
    "cliova_worlds",
)


def _database_url() -> str:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    return url


@pytest.fixture
def database_url() -> str:
    url = _database_url()
    apply_migrations(url)
    with psycopg.connect(url) as connection:
        connection.execute("TRUNCATE TABLE " + ", ".join(_TABLES) + " RESTART IDENTITY CASCADE")
    return url


def _world(*, key: str) -> WorldState:
    return WorldState.create(seed=1701, world_key=key)


def _input(*, reason: str) -> SimulationInput:
    return SimulationInput(source="test", kind="test-input", reason=reason)


def _count(database_url: str, table: str) -> int:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        return int(row[0])


class BlockingEngine(SimulationEngine):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()
        self.seen_inputs: tuple[SimulationInput, ...] = ()

    def step(self, world: WorldState, *, inputs: Iterable[SimulationInput] = ()) -> TickResult:
        self.seen_inputs = tuple(inputs)
        self.started.set()
        if not self.release.wait(timeout=10):
            raise RuntimeError("test did not release blocked simulation")
        return super().step(world, inputs=self.seen_inputs)


class FailingEngine(SimulationEngine):
    def step(self, world: WorldState, *, inputs: Iterable[SimulationInput] = ()) -> TickResult:
        del world, inputs
        raise RuntimeError("forced scheduled execution failure")


def test_active_world_advances_once_per_cadence_without_player_input(database_url: str) -> None:
    repository = PostgresScheduledWorldRepository(database_url)
    world = _world(key="active-once")
    repository.create_world(world)
    service = ScheduledTickService(SimulationEngine(), repository)
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)

    first = service.run_due(now=now)
    duplicate = service.run_due(now=now)
    too_early = service.run_due(now=now + timedelta(hours=23))
    next_day = service.run_due(now=now + timedelta(days=1))

    assert len(first) == 1
    assert first[0].world.time.tick == 1
    assert duplicate == ()
    assert too_early == ()
    assert len(next_day) == 1
    assert next_day[0].world.time.tick == 2
    assert repository.load_world(world.id.value).time.tick == 2
    assert _count(database_url, "cliova_completed_ticks") == 2


def test_administratively_paused_world_does_not_advance(database_url: str) -> None:
    repository = PostgresScheduledWorldRepository(database_url)
    world = _world(key="paused")
    repository.create_world(world)
    service = ScheduledTickService(SimulationEngine(), repository)
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)

    state = service.set_administrative_pause(world.id.value, paused=True, now=now)

    assert state.status is WorldScheduleStatus.PAUSED
    assert service.run_due(now=now) == ()
    assert repository.load_world(world.id.value) == world
    assert _count(database_url, "cliova_completed_ticks") == 0


def test_concurrent_scheduled_attempts_cannot_both_commit(database_url: str) -> None:
    world = _world(key="concurrent")
    first_repository = PostgresScheduledWorldRepository(database_url)
    first_repository.create_world(world)
    first_engine = BlockingEngine()
    first_service = ScheduledTickService(first_engine, first_repository)
    second_service = ScheduledTickService(
        SimulationEngine(),
        PostgresScheduledWorldRepository(database_url),
    )
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first_service.run_scheduled_world, world.id.value, now=now)
        assert first_engine.started.wait(timeout=5)
        second_future = pool.submit(second_service.run_scheduled_world, world.id.value, now=now)
        first_engine.release.set()
        outcomes = (first_future.result(timeout=10), second_future.result(timeout=10))

    assert sum(result is not None for result in outcomes) == 1
    assert first_repository.load_world(world.id.value).time.tick == 1
    assert _count(database_url, "cliova_completed_ticks") == 1
    assert _count(database_url, "cliova_tick_runs") == 1


def test_late_input_cannot_change_started_tick_and_remains_for_future_tick(
    database_url: str,
) -> None:
    world = _world(key="late-input")
    repository = PostgresScheduledWorldRepository(database_url)
    repository.create_world(world)
    engine = BlockingEngine()
    service = ScheduledTickService(engine, repository)
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)

    with ThreadPoolExecutor(max_workers=2) as pool:
        tick_future = pool.submit(service.run_scheduled_world, world.id.value, now=now)
        assert engine.started.wait(timeout=5)
        input_future = pool.submit(
            PostgresScheduledWorldRepository(database_url).queue_input,
            world.id.value,
            _input(reason="arrived after input closure"),
        )
        engine.release.set()
        result = tick_future.result(timeout=10)
        queued = input_future.result(timeout=10)

    assert result is not None
    assert result.world.time.tick == 1
    assert engine.seen_inputs == ()
    assert queued.submitted_tick == 2
    assert repository.load_pending_inputs(world.id.value) == (queued,)
    run = repository.load_tick_run(world.id.value, target_tick=1)
    assert run is not None
    assert run.accepted_input_count == 0
    assert run.accepted_input_max_queue_id is None


def test_failed_execution_preserves_state_records_diagnostics_and_retries_safely(
    database_url: str,
) -> None:
    repository = PostgresScheduledWorldRepository(database_url)
    world = _world(key="retry")
    repository.create_world(world)
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="forced scheduled execution failure"):
        ScheduledTickService(FailingEngine(), repository).run_scheduled_world(
            world.id.value,
            now=now,
        )

    assert repository.load_world(world.id.value) == world
    assert _count(database_url, "cliova_completed_ticks") == 0
    failed = repository.load_tick_run(world.id.value, target_tick=1)
    assert failed is not None
    assert failed.status is TickRunStatus.FAILED
    assert failed.failed_at is not None
    assert "forced scheduled execution failure" in (failed.failure_reason or "")
    assert failed.attempt_count == 1

    retried = ScheduledTickService(SimulationEngine(), repository).run_scheduled_world(
        world.id.value,
        now=now,
    )

    assert retried is not None
    assert retried.world.time.tick == 1
    completed = repository.load_tick_run(world.id.value, target_tick=1)
    assert completed is not None
    assert completed.status is TickRunStatus.COMPLETED
    assert completed.attempt_count == 2
    assert completed.failure_reason is None
    assert _count(database_url, "cliova_completed_ticks") == 1


def test_manual_tick_uses_same_claim_input_boundary_and_duplicate_protection(
    database_url: str,
) -> None:
    repository = PostgresScheduledWorldRepository(database_url)
    world = _world(key="manual")
    repository.create_world(world)
    queued = repository.queue_input(world.id.value, _input(reason="manual accepted input"))
    service = ScheduledTickService(SimulationEngine(), repository)
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)

    result = service.advance_manual(world.id.value, expected_tick=0, now=now)

    assert result.world.time.tick == 1
    assert repository.load_pending_inputs(world.id.value) == ()
    run = repository.load_tick_run(world.id.value, target_tick=1)
    assert run is not None
    assert run.trigger is TickRunTrigger.MANUAL
    assert run.status is TickRunStatus.COMPLETED
    assert run.accepted_input_count == 1
    assert run.accepted_input_max_queue_id == queued.queue_id
    with pytest.raises(TickConflictError):
        service.advance_manual(world.id.value, expected_tick=0, now=now)
    assert _count(database_url, "cliova_completed_ticks") == 1


def test_scheduling_service_does_not_interpret_tick_as_in_world_year() -> None:
    now = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)
    world = _world(key="time-independent")
    arbitrary_time_world = world.model_copy(update={"time": SimulationTime(tick=1, year=37)})
    arbitrary_result = SimulationEngine().step(world).model_copy(
        update={"world": arbitrary_time_world}
    )

    class RecordingRepository:
        def __init__(self) -> None:
            self.next_eligible_at: datetime | None = None

        def claim_scheduled_tick(self, world_id: UUID, *, now: datetime) -> TickRunClaim | None:
            return TickRunClaim(
                run_id=uuid4(),
                world_id=world_id,
                target_tick=1,
                trigger=TickRunTrigger.SCHEDULED,
                claim_token=uuid4(),
                started_at=now,
                attempt_count=1,
            )

        def execute_claimed_tick(
            self,
            claim: TickRunClaim,
            *,
            resolver: TickResolver,
            next_eligible_at: datetime,
        ) -> TickResult:
            del claim, resolver
            self.next_eligible_at = next_eligible_at
            return arbitrary_result

    repository = RecordingRepository()
    service = ScheduledTickService(
        SimulationEngine(),
        repository,  # type: ignore[arg-type]
        cadence=timedelta(hours=6),
    )

    result = service.run_scheduled_world(world.id.value, now=now)

    assert result is arbitrary_result
    assert result.world.time.tick == 1
    assert result.world.time.year == 37
    assert repository.next_eligible_at == now + timedelta(hours=6)
