import pytest

from cliova.simulation.domains.population import (
    FOOD_SECURITY,
    MATERIAL_SECURITY,
    PopulationDomain,
    initialize_population,
)
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine, TickExecutionError
from cliova.simulation.history import EventHistory
from cliova.simulation.types import SimulationChange, SimulationInput, WorldState


def _initialized_world(*, seed: int = 41, total_per_region: int = 1_000) -> WorldState:
    return initialize_population(
        create_starter_world(seed=seed, world_key="population-tests"),
        total_per_region=total_per_region,
    )


def test_population_initialization_creates_region_aggregates_and_round_trips() -> None:
    world = _initialized_world()

    assert world.geography is not None
    assert world.population is not None
    assert tuple(population.region_id for population in world.population.regions) == tuple(
        region.id for region in world.geography.regions
    )
    assert all(population.total == 1_000 for population in world.population.regions)
    assert all(population.needs.food_security == 1.0 for population in world.population.regions)
    assert WorldState.model_validate_json(world.model_dump_json()) == world


def test_secure_fertile_population_grows_without_mutating_geography() -> None:
    world = _initialized_world()
    assert world.geography is not None
    assert world.population is not None
    fertile = world.geography.region("fertile-lowlands")
    before = world.population.region(fertile.id)

    result = SimulationEngine((PopulationDomain(),)).step(world)

    assert result.world.population is not None
    after = result.world.population.region(fertile.id)
    assert after.total > before.total
    assert after.migration_pressure >= 0.0
    assert result.world.geography == world.geography
    assert any(
        change.target == fertile.id and change.key == "population.total" and change.delta > 0
        for change in result.changes
    )


def test_food_and_material_shortage_reduce_population_and_raise_migration_pressure() -> None:
    world = _initialized_world()
    assert world.geography is not None
    assert world.population is not None
    fertile = world.geography.region("fertile-lowlands")

    control = SimulationEngine((PopulationDomain(),)).step(world)
    shortage = SimulationInput(
        source="scenario",
        kind="shortage",
        reason="Food stores and basic materials became scarce",
        subjects=(fertile.id,),
        changes=(
            SimulationChange(
                source="population",
                key=FOOD_SECURITY,
                delta=-0.8,
                reason="food shortage",
                target=fertile.id,
            ),
            SimulationChange(
                source="population",
                key=MATERIAL_SECURITY,
                delta=-0.4,
                reason="material shortage",
                target=fertile.id,
            ),
        ),
    )
    stressed = SimulationEngine((PopulationDomain(),)).step(world, inputs=(shortage,))

    assert control.world.population is not None
    assert stressed.world.population is not None
    control_population = control.world.population.region(fertile.id)
    stressed_population = stressed.world.population.region(fertile.id)

    assert stressed_population.total < 1_000
    assert stressed_population.total < control_population.total
    assert stressed_population.migration_pressure > control_population.migration_pressure
    assert stressed_population.needs.food_security == pytest.approx(0.2)
    assert stressed_population.needs.material_security == pytest.approx(0.6)


def test_significant_shortage_emits_causal_demographic_event_and_explanation() -> None:
    world = _initialized_world(seed=43)
    assert world.geography is not None
    fertile = world.geography.region("fertile-lowlands")
    shortage = SimulationInput(
        source="scenario",
        kind="food-shortage",
        reason="Regional food reserves collapsed",
        subjects=(fertile.id,),
        changes=(
            SimulationChange(
                source="population",
                key=FOOD_SECURITY,
                delta=-0.8,
                reason="food shortage",
                target=fertile.id,
            ),
        ),
    )

    result = SimulationEngine((PopulationDomain(),)).step(world, inputs=(shortage,))
    input_event = next(event for event in result.events if event.source == "scenario")
    decline = next(
        event
        for event in result.events
        if event.source == "population"
        and event.kind == "population-decline"
        and fertile.id in event.subjects
    )

    assert decline.cause_event_ids == (input_event.id,)
    assert decline.changes
    explanation = next(
        explanation
        for explanation in result.explanations
        if explanation.source == "population" and explanation.cause_event_ids
    )
    assert explanation.cause_event_ids == (input_event.id,)

    history = EventHistory.from_ticks((result,))
    why = history.why(decline.id)
    assert tuple(item.event_id for item in why) == (input_event.id, decline.id)


def test_population_replay_is_deterministic_across_multiple_ticks() -> None:
    first_world = _initialized_world(seed=47, total_per_region=2_000)
    second_world = _initialized_world(seed=47, total_per_region=2_000)

    first = SimulationEngine((PopulationDomain(),)).run(first_world, years=3)
    second = SimulationEngine((PopulationDomain(),)).run(second_world, years=3)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first.world.population is not None
    assert first.world.population.regions != first_world.population.regions


def test_population_reducer_rejects_out_of_range_pressure() -> None:
    world = _initialized_world(seed=53)
    assert world.geography is not None
    fertile = world.geography.region("fertile-lowlands")
    invalid = SimulationInput(
        source="scenario",
        kind="invalid-pressure",
        reason="invalid test input",
        changes=(
            SimulationChange(
                source="population",
                key=FOOD_SECURITY,
                delta=-1.1,
                reason="invalid",
                target=fertile.id,
            ),
        ),
    )

    with pytest.raises(TickExecutionError, match="must remain between 0 and 1"):
        SimulationEngine((PopulationDomain(),)).step(world, inputs=(invalid,))
