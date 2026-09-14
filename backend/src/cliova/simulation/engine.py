import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from cliova.simulation.randomness import RandomSource, random_for
from cliova.simulation.types import (
    DomainResult,
    EventProposal,
    SimulationChange,
    SimulationDiagnostic,
    SimulationEvent,
    SimulationExplanation,
    SimulationInput,
    SimulationRunResult,
    SimulationTime,
    TickResult,
    WorldState,
)


class TickPhase(StrEnum):
    INGEST_INPUTS = "ingest_inputs"
    WORLD_ENVIRONMENT = "world_environment"
    POPULATION = "population"
    ECONOMY = "economy"
    GOVERNANCE = "governance"
    KNOWLEDGE_SCENARIOS = "knowledge_scenarios"
    HISTORY = "history"
    FINALIZE = "finalize"


PHASE_ORDER: tuple[TickPhase, ...] = (
    TickPhase.INGEST_INPUTS,
    TickPhase.WORLD_ENVIRONMENT,
    TickPhase.POPULATION,
    TickPhase.ECONOMY,
    TickPhase.GOVERNANCE,
    TickPhase.KNOWLEDGE_SCENARIOS,
    TickPhase.HISTORY,
    TickPhase.FINALIZE,
)


@dataclass(frozen=True, slots=True)
class TickContext:
    """Read-only tick context carried explicitly through every domain step."""

    time: SimulationTime
    phase: TickPhase
    prior_events: tuple[SimulationEvent, ...]
    queued_inputs: tuple[SimulationInput, ...]


class SimulationDomain(Protocol):
    """Domains propose changes and apply only their own changes when the engine asks."""

    name: str
    phase: TickPhase

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult: ...

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState: ...


class TickExecutionError(RuntimeError):
    """Identifies the phase/domain that failed without exposing a partial committed tick."""

    def __init__(self, phase: TickPhase, source: str, message: str) -> None:
        super().__init__(f"tick failed in {phase.value}/{source}: {message}")
        self.phase = phase
        self.source = source


class SimulationEngine:
    """Owns deterministic phase ordering and the atomic authoritative tick commit."""

    def __init__(
        self,
        domains: Iterable[SimulationDomain] = (),
        *,
        rng_factory: Callable[[int, int, str], RandomSource] = random_for,
    ) -> None:
        self._domains = tuple(domains)
        names = [domain.name for domain in self._domains]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError("domain names must be non-empty strings")
        if len(set(names)) != len(names):
            raise ValueError("domain names must be unique")
        for domain in self._domains:
            if not isinstance(domain.phase, TickPhase):
                raise ValueError(f"domain {domain.name!r} has invalid tick phase")
        self._domains_by_name = {domain.name: domain for domain in self._domains}
        self._domains_by_phase = {
            phase: tuple(domain for domain in self._domains if domain.phase is phase)
            for phase in PHASE_ORDER
        }
        self._rng_factory = rng_factory

    def step(self, world: WorldState, *, inputs: Iterable[SimulationInput] = ()) -> TickResult:
        queued_inputs = tuple(inputs)
        next_time = world.time.next_year()
        working = world
        changes: list[SimulationChange] = []
        events: list[SimulationEvent] = []
        explanations: list[SimulationExplanation] = []
        diagnostics: list[SimulationDiagnostic] = []

        # All state produced below is local. Nothing is committed until every phase succeeds.
        working = self._ingest_inputs(
            working, queued_inputs, next_time, changes, events, diagnostics
        )

        for phase in PHASE_ORDER[1:]:
            phase_changes = 0
            phase_events = 0
            domains = self._domains_by_phase[phase]
            for domain in domains:
                context = TickContext(
                    time=next_time,
                    phase=phase,
                    prior_events=tuple(events),
                    queued_inputs=queued_inputs,
                )
                rng = self._rng_factory(world.seed, next_time.tick, domain.name)
                try:
                    result = domain.step(working, context, rng)
                    self._validate_result(domain, phase, result)
                    working = self._apply_changes(working, result.changes, phase)
                except TickExecutionError:
                    raise
                except Exception as exc:
                    raise TickExecutionError(phase, domain.name, str(exc)) from exc

                materialized = self._materialize_events(
                    world, next_time, phase, domain.name, result.events
                )
                changes.extend(result.changes)
                events.extend(materialized)
                explanations.extend(result.explanations)
                diagnostics.extend(result.diagnostics)
                phase_changes += len(result.changes)
                phase_events += len(materialized)

            diagnostics.append(
                SimulationDiagnostic(
                    phase=phase.value,
                    source="engine",
                    message=(
                        f"completed domains={len(domains)} "
                        f"changes={phase_changes} events={phase_events}"
                    ),
                )
            )

        try:
            self._validate_core_identity(world, working)
            committed = working.model_copy(update={"time": next_time})
        except Exception as exc:
            raise TickExecutionError(TickPhase.FINALIZE, "engine", str(exc)) from exc

        return TickResult(
            world=committed,
            phases=tuple(phase.value for phase in PHASE_ORDER),
            changes=tuple(changes),
            events=tuple(events),
            explanations=tuple(explanations),
            diagnostics=tuple(diagnostics),
        )

    def run(
        self,
        world: WorldState,
        years: int,
        *,
        inputs: Sequence[Sequence[SimulationInput]] = (),
    ) -> SimulationRunResult:
        if type(years) is not int or years < 0:
            raise ValueError("years must be non-negative")
        if len(inputs) > years:
            raise ValueError("input batches cannot exceed requested years")

        ticks: list[TickResult] = []
        for index in range(years):
            tick = self.step(world, inputs=inputs[index] if index < len(inputs) else ())
            ticks.append(tick)
            world = tick.world
        return SimulationRunResult(world=world, ticks=tuple(ticks))

    def _ingest_inputs(
        self,
        working: WorldState,
        inputs: tuple[SimulationInput, ...],
        time: SimulationTime,
        changes: list[SimulationChange],
        events: list[SimulationEvent],
        diagnostics: list[SimulationDiagnostic],
    ) -> WorldState:
        for ordinal, queued in enumerate(inputs):
            working = self._apply_changes(working, queued.changes, TickPhase.INGEST_INPUTS)
            changes.extend(queued.changes)
            cause_event_ids = tuple(
                dict.fromkeys(
                    cause_id for change in queued.changes for cause_id in change.cause_event_ids
                )
            )
            events.append(
                SimulationEvent(
                    id=self._event_id(
                        working, time, TickPhase.INGEST_INPUTS, queued.source, ordinal
                    ),
                    time=time,
                    source=queued.source,
                    kind=queued.kind,
                    reason=queued.reason,
                    subjects=queued.subjects,
                    cause_event_ids=cause_event_ids,
                    changes=queued.changes,
                )
            )

        diagnostics.append(
            SimulationDiagnostic(
                phase=TickPhase.INGEST_INPUTS.value,
                source="engine",
                message=(
                    f"completed inputs={len(inputs)} changes={sum(len(i.changes) for i in inputs)}"
                ),
            )
        )
        return working

    def _validate_result(
        self, domain: SimulationDomain, phase: TickPhase, result: DomainResult
    ) -> None:
        if not isinstance(result, DomainResult):
            raise TickExecutionError(phase, domain.name, "domain must return DomainResult")

        for change in result.changes:
            if change.source != domain.name:
                raise TickExecutionError(
                    phase,
                    domain.name,
                    f"cannot emit change owned by {change.source!r}",
                )
        for event in result.events:
            for event_change in event.changes:
                if event_change not in result.changes:
                    raise TickExecutionError(
                        phase,
                        domain.name,
                        "event references a change not proposed by the same domain step",
                    )
        for explanation in result.explanations:
            if explanation.source != domain.name:
                raise TickExecutionError(
                    phase, domain.name, "explanation source must match the emitting domain"
                )
        for diagnostic in result.diagnostics:
            if diagnostic.source != domain.name or diagnostic.phase != phase.value:
                raise TickExecutionError(
                    phase, domain.name, "diagnostic source/phase must match the emitting domain"
                )

    def _apply_changes(
        self, world: WorldState, proposed: tuple[SimulationChange, ...], phase: TickPhase
    ) -> WorldState:
        working = world
        for change in proposed:
            owner = self._domains_by_name.get(change.source)
            if owner is None:
                raise TickExecutionError(
                    phase, change.source, "no registered owning domain for proposed change"
                )
            try:
                candidate = owner.apply_change(working, change)
            except Exception as exc:
                raise TickExecutionError(phase, owner.name, str(exc)) from exc
            if not isinstance(candidate, WorldState):
                raise TickExecutionError(phase, owner.name, "apply_change must return WorldState")
            try:
                self._validate_core_identity(working, candidate)
            except ValueError as exc:
                raise TickExecutionError(phase, owner.name, str(exc)) from exc
            working = candidate
        return working

    @staticmethod
    def _validate_core_identity(before: WorldState, after: WorldState) -> None:
        if (
            after.id != before.id
            or after.seed != before.seed
            or after.metadata != before.metadata
            or after.time != before.time
        ):
            raise ValueError("domain reducers cannot modify core identity, metadata or time")

    @staticmethod
    def _event_id(
        world: WorldState,
        time: SimulationTime,
        phase: TickPhase,
        source: str,
        ordinal: int,
    ) -> UUID:
        material = json.dumps(
            ["cliova.event.v1", time.tick, phase.value, source, ordinal],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return uuid5(world.id.value, material)

    def _materialize_events(
        self,
        world: WorldState,
        time: SimulationTime,
        phase: TickPhase,
        source: str,
        proposals: tuple[EventProposal, ...],
    ) -> tuple[SimulationEvent, ...]:
        return tuple(
            SimulationEvent(
                id=self._event_id(world, time, phase, source, ordinal),
                time=time,
                source=source,
                kind=proposal.kind,
                reason=proposal.reason,
                subjects=proposal.subjects,
                cause_event_ids=proposal.cause_event_ids,
                changes=proposal.changes,
            )
            for ordinal, proposal in enumerate(proposals)
        )
