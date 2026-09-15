"""Application-level persistence boundary for durable deterministic ticks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cliova.simulation.engine import SimulationEngine
from cliova.simulation.history import EventHistory
from cliova.simulation.types import SimulationInput, TickResult, WorldState


@dataclass(frozen=True, slots=True)
class QueuedSimulationInput:
    """Infrastructure queue envelope around the authoritative SimulationInput payload."""

    queue_id: int
    submitted_tick: int
    value: SimulationInput


TickResolver = Callable[[WorldState, tuple[SimulationInput, ...]], TickResult]


class PersistenceRepository(Protocol):
    """Persistence operations required by application services, independent of SQL details."""

    def create_world(self, world: WorldState) -> None: ...

    def load_world(self, world_id: UUID) -> WorldState: ...

    def load_snapshot(self, world_id: UUID, tick: int) -> WorldState: ...

    def queue_input(self, world_id: UUID, value: SimulationInput) -> QueuedSimulationInput: ...

    def load_pending_inputs(self, world_id: UUID) -> tuple[QueuedSimulationInput, ...]: ...

    def execute_tick(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        resolver: TickResolver,
    ) -> TickResult: ...

    def load_history(self, world_id: UUID) -> EventHistory: ...


class PersistedTickService:
    """Advance one persisted world without exposing database concerns to the engine."""

    def __init__(self, engine: SimulationEngine, repository: PersistenceRepository) -> None:
        self._engine = engine
        self._repository = repository

    def advance_world(self, world_id: UUID, *, expected_tick: int | None = None) -> TickResult:
        """Resolve and atomically persist exactly the expected next tick.

        Supplying ``expected_tick`` gives schedulers/callers an optimistic concurrency token.
        When omitted, the current persisted tick is read immediately before the transaction.
        """

        if expected_tick is None:
            expected_tick = self._repository.load_world(world_id).time.tick
        return self._repository.execute_tick(
            world_id,
            expected_tick=expected_tick,
            resolver=self._resolve,
        )

    def _resolve(self, world: WorldState, inputs: tuple[SimulationInput, ...]) -> TickResult:
        return self._engine.step(world, inputs=inputs)
