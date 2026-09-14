from __future__ import annotations

import pytest
from simulation_quality import (
    HeadlessTrace,
    SimulationQualityError,
    assert_core_invariants,
    assert_finite_values,
    assert_monotonic_ticks,
    assert_replay_equivalent,
    assert_stable_entity_ids,
    assert_unique_event_ids,
    measure_tick_runtime,
    run_headless,
)

from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine, TickContext, TickPhase
from cliova.simulation.history import EventHistory
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EventProposal,
    SimulationChange,
    SimulationInput,
    WorldState,
)


class SeededEventDomain:
    name = "quality-world"
    phase = TickPhase.WORLD_ENVIRONMENT

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
        return DomainResult(
            events=(
                EventProposal(
                    kind="quality-sample",
                    reason=f"year={context.time.year} sample={rng.random():.17g}",
                ),
            )
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        return world


def _world() -> WorldState:
    return create_starter_world(seed=42)


def _engine() -> SimulationEngine:
    return SimulationEngine((SeededEventDomain(),))


def test_replay_helper_compares_seeded_state_history_and_ordered_inputs() -> None:
    inputs = (
        (SimulationInput(source="player:1", kind="priority", reason="hold course"),),
        (),
    )

    first, second = assert_replay_equivalent(_world, _engine, years=2, inputs=inputs)

    assert first.run.world == second.run.world
    assert EventHistory.from_run(first.run).events == EventHistory.from_run(second.run).events
    assert len(EventHistory.from_run(first.run).events) == 3


def test_core_invariants_cover_ticks_events_finite_values_and_core_ids() -> None:
    trace = run_headless(_world, _engine, years=3)

    assert_core_invariants(trace)
    assert trace.run.world.id == trace.initial_world.id
    assert [tick.world.time.tick for tick in trace.run.ticks] == [1, 2, 3]


def test_entity_ids_survive_authoritative_json_round_trip() -> None:
    world = _world()

    assert_stable_entity_ids(world, seed=world.seed, tick=world.time.tick)


def test_duplicate_tick_failure_reports_seed_and_tick() -> None:
    trace = run_headless(_world, _engine, years=2)
    first_tick, second_tick = trace.run.ticks
    duplicated_world = second_tick.world.model_copy(update={"time": first_tick.world.time})
    duplicated_tick = second_tick.model_copy(update={"world": duplicated_world})
    broken = HeadlessTrace(
        initial_world=trace.initial_world,
        run=trace.run.model_copy(update={"ticks": (first_tick, duplicated_tick)}),
    )

    with pytest.raises(
        SimulationQualityError,
        match=r"monotonic-ticks failed: seed=42 tick=1; expected tick 2, got 1",
    ):
        assert_monotonic_ticks(broken)


def test_duplicate_event_id_failure_reports_seed_and_tick() -> None:
    trace = run_headless(_world, _engine, years=2)
    first_tick, second_tick = trace.run.ticks
    duplicated_event = second_tick.events[0].model_copy(update={"id": first_tick.events[0].id})
    duplicated_tick = second_tick.model_copy(update={"events": (duplicated_event,)})
    broken = HeadlessTrace(
        initial_world=trace.initial_world,
        run=trace.run.model_copy(update={"ticks": (first_tick, duplicated_tick)}),
    )

    with pytest.raises(
        SimulationQualityError,
        match=r"unique-event-ids failed: seed=42 tick=2;.*first_seen_tick=1",
    ):
        assert_unique_event_ids(broken)


def test_finite_value_failure_reports_nested_path_seed_and_tick() -> None:
    payload = {"stable": 1.0, "nested": (2.0, float("nan"))}

    with pytest.raises(
        SimulationQualityError,
        match=r"finite-values failed: seed=73 tick=9;.*nested.*value=nan",
    ):
        assert_finite_values(payload, seed=73, tick=9)


def test_tick_timing_helper_returns_repeatable_samples_without_threshold() -> None:
    timing = measure_tick_runtime(_world, _engine, repeats=3)

    assert len(timing.durations_ns) == 3
    assert all(duration >= 0 for duration in timing.durations_ns)
    assert timing.median_ns >= 0
    assert timing.median_ms >= 0
