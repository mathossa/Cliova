import pytest

from cliova.simulation.engine import (
    PHASE_ORDER,
    SimulationEngine,
    TickContext,
    TickExecutionError,
    TickPhase,
)
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EventProposal,
    SimulationChange,
    SimulationDiagnostic,
    SimulationExplanation,
    SimulationInput,
    WorldState,
)


class SampleDomain:
    def __init__(self, name: str, phase: TickPhase) -> None:
        self.name = name
        self.phase = phase
        self.applied: list[SimulationChange] = []

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
        change = SimulationChange(
            source=self.name,
            key="sample",
            delta=rng.random(),
            reason="seeded sample",
        )
        return DomainResult(
            changes=(change,),
            events=(EventProposal(kind="sample", reason="sample event", changes=(change,)),),
            explanations=(
                SimulationExplanation(source=self.name, message=f"ran {context.phase.value}"),
            ),
            diagnostics=(
                SimulationDiagnostic(
                    phase=context.phase.value,
                    source=self.name,
                    message=f"year={context.time.year}",
                ),
            ),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        self.applied.append(change)
        return world


def test_phase_order_is_explicit_and_not_constructor_order() -> None:
    economy = SampleDomain("economy-domain", TickPhase.ECONOMY)
    world_domain = SampleDomain("world-domain", TickPhase.WORLD_ENVIRONMENT)
    result = SimulationEngine([economy, world_domain]).step(WorldState.create(seed=42))

    assert result.phases == tuple(phase.value for phase in PHASE_ORDER)
    assert [change.source for change in result.changes] == ["world-domain", "economy-domain"]
    assert [event.source for event in result.events] == ["world-domain", "economy-domain"]


def test_same_state_seed_and_inputs_produce_byte_equivalent_output() -> None:
    domains = [
        SampleDomain("world-domain", TickPhase.WORLD_ENVIRONMENT),
        SampleDomain("economy-domain", TickPhase.ECONOMY),
    ]
    queued = (SimulationInput(source="player:1", kind="directive", reason="hold course"),)
    first = SimulationEngine(domains).step(WorldState.create(seed=42), inputs=queued)

    replay_domains = [
        SampleDomain("world-domain", TickPhase.WORLD_ENVIRONMENT),
        SampleDomain("economy-domain", TickPhase.ECONOMY),
    ]
    second = SimulationEngine(replay_domains).step(WorldState.create(seed=42), inputs=queued)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_changes_are_applied_centrally_by_the_owning_domain() -> None:
    domain = SampleDomain("economy-domain", TickPhase.ECONOMY)
    result = SimulationEngine([domain]).step(WorldState.create(seed=7))

    assert tuple(domain.applied) == result.changes
    assert result.world.year == 1


def test_failure_is_atomic_and_retry_replays_cleanly() -> None:
    class FailingDomain(SampleDomain):
        def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
            raise RuntimeError("domain reducer failed")

    initial = WorldState.create(seed=42)
    snapshot = initial.model_dump_json()
    first = SampleDomain("world-domain", TickPhase.WORLD_ENVIRONMENT)
    failing = FailingDomain("economy-domain", TickPhase.ECONOMY)

    with pytest.raises(TickExecutionError, match="economy-domain.*domain reducer failed"):
        SimulationEngine([first, failing]).step(initial)

    assert initial.model_dump_json() == snapshot
    replay_initial = WorldState.model_validate_json(snapshot)
    expected = SimulationEngine(
        [
            SampleDomain("world-domain", TickPhase.WORLD_ENVIRONMENT),
            SampleDomain("economy-domain", TickPhase.ECONOMY),
        ]
    ).step(replay_initial)
    actual = SimulationEngine(
        [
            SampleDomain("world-domain", TickPhase.WORLD_ENVIRONMENT),
            SampleDomain("economy-domain", TickPhase.ECONOMY),
        ]
    ).step(initial)
    assert actual == expected


def test_headless_multi_tick_run_keeps_tick_outputs() -> None:
    result = SimulationEngine().run(WorldState.create(seed=42), years=3)
    assert result.world.year == 3
    assert result.world.time.tick == 3
    assert [tick.world.year for tick in result.ticks] == [1, 2, 3]


def test_zero_ticks_returns_same_state() -> None:
    world = WorldState.create(seed=42)
    result = SimulationEngine().run(world, years=0)
    assert result.world is world
    assert result.ticks == ()


def test_engine_rejects_negative_years_and_extra_input_batches() -> None:
    world = WorldState.create(seed=42)
    with pytest.raises(ValueError, match="years must be non-negative"):
        SimulationEngine().run(world, years=-1)
    with pytest.raises(ValueError, match="input batches"):
        SimulationEngine().run(
            world,
            years=0,
            inputs=((SimulationInput(source="x", kind="x", reason="x"),),),
        )


def test_domain_cannot_emit_change_owned_by_another_domain() -> None:
    class BadDomain(SampleDomain):
        def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
            return DomainResult(
                changes=(
                    SimulationChange(source="other", key="x", delta=1, reason="invalid"),
                )
            )

    with pytest.raises(TickExecutionError, match="cannot emit change owned by"):
        SimulationEngine([BadDomain("bad", TickPhase.ECONOMY)]).step(WorldState.create(seed=1))
