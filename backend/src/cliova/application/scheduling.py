"""Application boundary for safe wall-clock scheduling of authoritative world ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from cliova.application.persistence import PersistenceRepository, TickResolver
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import SimulationInput, TickResult, WorldState


class WorldScheduleStatus(StrEnum):
    """Administrative scheduling state; player responses never pause a world."""

    ACTIVE = "active"
    PAUSED = "paused"


class TickRunTrigger(StrEnum):
    """Why the application requested an authoritative tick."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"


class TickRunStatus(StrEnum):
    """Durable lifecycle of one target-tick execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TickRunClaim:
    """Durable ownership token for one world/target-tick execution attempt."""

    run_id: UUID
    world_id: UUID
    target_tick: int
    trigger: TickRunTrigger
    claim_token: UUID
    started_at: datetime
    attempt_count: int


@dataclass(frozen=True, slots=True)
class WorldScheduleState:
    """Persistent scheduler metadata kept outside authoritative simulation state."""

    world_id: UUID
    status: WorldScheduleStatus
    next_eligible_at: datetime | None
    current_run_id: UUID | None
    last_completed_run_id: UUID | None
    last_completed_at: datetime | None
    last_failure_at: datetime | None
    last_failure_reason: str | None
    duplicate_attempt_count: int


@dataclass(frozen=True, slots=True)
class TickRunRecord:
    """Diagnostics for a scheduled/manual authoritative tick run."""

    run_id: UUID
    world_id: UUID
    target_tick: int
    trigger: TickRunTrigger
    status: TickRunStatus
    scheduled_for: datetime | None
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None
    accepted_input_max_queue_id: int | None
    accepted_input_count: int
    attempt_count: int


class SchedulingRepository(PersistenceRepository, Protocol):
    """Persistence operations needed by the wall-clock scheduler application service."""

    def list_due_world_ids(self, *, now: datetime) -> tuple[UUID, ...]: ...

    def claim_scheduled_tick(self, world_id: UUID, *, now: datetime) -> TickRunClaim | None: ...

    def claim_manual_tick(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        now: datetime,
    ) -> TickRunClaim: ...

    def execute_claimed_tick(
        self,
        claim: TickRunClaim,
        *,
        resolver: TickResolver,
        next_eligible_at: datetime,
    ) -> TickResult: ...

    def set_schedule_status(
        self,
        world_id: UUID,
        *,
        status: WorldScheduleStatus,
        now: datetime,
    ) -> WorldScheduleState: ...

    def load_schedule_state(self, world_id: UUID) -> WorldScheduleState: ...

    def load_tick_run(self, world_id: UUID, *, target_tick: int) -> TickRunRecord | None: ...


class ScheduledTickService:
    """Invoke authoritative ticks without coupling simulation rules to wall-clock cadence."""

    def __init__(
        self,
        engine: SimulationEngine,
        repository: SchedulingRepository,
        *,
        cadence: timedelta = timedelta(days=1),
    ) -> None:
        if cadence <= timedelta(0):
            raise ValueError("cadence must be positive")
        self._engine = engine
        self._repository = repository
        self._cadence = cadence

    def run_due(self, *, now: datetime) -> tuple[TickResult, ...]:
        """Advance each currently eligible active world at most once for this scheduler pass."""

        now = _aware_utc(now)
        results: list[TickResult] = []
        for world_id in self._repository.list_due_world_ids(now=now):
            result = self.run_scheduled_world(world_id, now=now)
            if result is not None:
                results.append(result)
        return tuple(results)

    def run_scheduled_world(self, world_id: UUID, *, now: datetime) -> TickResult | None:
        """Try to claim and execute one due scheduled tick.

        Duplicate or not-yet-due attempts are safe no-ops.
        """

        now = _aware_utc(now)
        claim = self._repository.claim_scheduled_tick(world_id, now=now)
        if claim is None:
            return None
        return self._repository.execute_claimed_tick(
            claim,
            resolver=self._resolve,
            next_eligible_at=now + self._cadence,
        )

    def advance_manual(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        now: datetime | None = None,
    ) -> TickResult:
        """Run the development/manual path through the same claim/freeze/commit boundary."""

        if expected_tick < 0:
            raise ValueError("expected_tick must be non-negative")
        started_at = _aware_utc(now or datetime.now(UTC))
        claim = self._repository.claim_manual_tick(
            world_id,
            expected_tick=expected_tick,
            now=started_at,
        )
        return self._repository.execute_claimed_tick(
            claim,
            resolver=self._resolve,
            next_eligible_at=started_at + self._cadence,
        )

    def set_administrative_pause(
        self,
        world_id: UUID,
        *,
        paused: bool,
        now: datetime | None = None,
    ) -> WorldScheduleState:
        """Pause/resume scheduler eligibility without introducing player-response pauses."""

        changed_at = _aware_utc(now or datetime.now(UTC))
        return self._repository.set_schedule_status(
            world_id,
            status=WorldScheduleStatus.PAUSED if paused else WorldScheduleStatus.ACTIVE,
            now=changed_at,
        )

    def _resolve(self, world: WorldState, inputs: tuple[SimulationInput, ...]) -> TickResult:
        return self._engine.step(world, inputs=inputs)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler timestamps must be timezone-aware")
    return value.astimezone(UTC)
