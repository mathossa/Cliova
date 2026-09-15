import pytest

from cliova.simulation.domains.economy import (
    RESOURCE_KINDS,
    EconomyDomain,
    initialize_economy,
    population_food_pressure_inputs,
    resource_change_key,
)
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    EconomyDomainState,
    EntityId,
    RegionalEconomyState,
    SimulationChange,
    SimulationInput,
    WorldState,
)


def _initialized_world(*, seed: int = 61, total_per_region: int = 1_000) -> WorldState:
    return initialize_economy(
        initialize_population(
            create_starter_world(seed=seed, world_key="economy-tests"),
            total_per_region=total_per_region,
        )
    )


def _with_food_stockpile(world: WorldState, region_id: EntityId, amount: float) -> WorldState:
    assert world.economy is not None
    regions = list(world.economy.regions)
    index = next(i for i, region in enumerate(regions) if region.region_id == region_id)
    regional = regions[index]
    resources = list(regional.resources)
    food_index = next(i for i, resource in enumerate(resources) if resource.resource == "food")
    resources[food_index] = resources[food_index].model_copy(update={"stockpile": amount})
    regions[index] = RegionalEconomyState(region_id=region_id, resources=tuple(resources))
    return world.model_copy(update={"economy": EconomyDomainState(regions=tuple(regions))})


def test_economy_initialization_and_normal_production_are_regional_and_serializable() -> None:
    world = _initialized_world()
    assert world.geography is not None
    assert world.economy is not None
    fertile = world.geography.region("fertile-lowlands")
    dry = world.geography.region("dry-basin")

    assert (
        tuple(resource.resource for resource in world.economy.region(fertile.id).resources)
        == RESOURCE_KINDS
    )
    assert WorldState.model_validate_json(world.model_dump_json()) == world

    result = SimulationEngine((EconomyDomain(),)).step(world)
    assert result.world.economy is not None
    fertile_food = result.world.economy.region(fertile.id).resource("food")
    dry_food = result.world.economy.region(dry.id).resource("food")

    assert fertile_food.production_capacity == fertile_food.production
    assert fertile_food.production > fertile_food.demand
    assert fertile_food.stockpile > 0.0
    assert fertile_food.surplus > 0.0
    assert fertile_food.shortage_severity == 0.0
    assert dry_food.production < dry_food.demand
    assert dry_food.production < fertile_food.production
    assert dry_food.shortage_severity > 0.0


def test_population_size_drives_resource_demand() -> None:
    small = _initialized_world(seed=63, total_per_region=1_000)
    large = _initialized_world(seed=63, total_per_region=2_000)
    assert small.geography is not None
    region = small.geography.region("fertile-lowlands")

    small_result = SimulationEngine((EconomyDomain(),)).step(small)
    large_result = SimulationEngine((EconomyDomain(),)).step(large)
    assert small_result.world.economy is not None
    assert large_result.world.economy is not None

    small_food = small_result.world.economy.region(region.id).resource("food")
    large_food = large_result.world.economy.region(region.id).resource("food")
    assert large_food.demand == pytest.approx(2.0 * small_food.demand)
    assert large_food.production_capacity == pytest.approx(2.0 * small_food.production_capacity)
    assert large_food.production < 2.0 * small_food.production


def test_reserves_accumulate_then_deplete_before_shortage() -> None:
    world = _initialized_world(seed=67)
    assert world.geography is not None
    dry = world.geography.region("dry-basin")
    world = _with_food_stockpile(world, dry.id, 1_000.0)
    engine = SimulationEngine((EconomyDomain(),))

    first = engine.step(world)
    second = engine.step(first.world)
    third = engine.step(second.world)
    assert first.world.economy is not None
    assert second.world.economy is not None
    assert third.world.economy is not None

    first_food = first.world.economy.region(dry.id).resource("food")
    second_food = second.world.economy.region(dry.id).resource("food")
    third_food = third.world.economy.region(dry.id).resource("food")
    assert first_food.stockpile < 1_000.0
    assert second_food.stockpile < first_food.stockpile
    assert first_food.shortage_severity == 0.0
    assert second_food.shortage_severity == 0.0
    assert third_food.stockpile == 0.0
    assert third_food.deficit > 0.0
    assert third_food.shortage_severity > 0.0


def test_food_shortage_becomes_next_tick_population_pressure_without_direct_mutation() -> None:
    world = _initialized_world(seed=71)
    assert world.geography is not None
    assert world.population is not None
    dry = world.geography.region("dry-basin")
    before_population = world.population

    economy_tick = SimulationEngine((EconomyDomain(),)).step(world)
    assert economy_tick.world.population == before_population
    assert economy_tick.world.economy is not None
    shortage = economy_tick.world.economy.region(dry.id).resource("food").shortage_severity
    assert shortage > 0.0
    shortage_event = next(
        event
        for event in economy_tick.events
        if event.source == "economy"
        and event.kind == "resource-shortage"
        and dry.id in event.subjects
        and any(change.key == "economy.food.shortage_severity" for change in event.changes)
    )

    pressures = population_food_pressure_inputs(economy_tick.world, events=economy_tick.events)
    dry_input = next(pressure for pressure in pressures if pressure.subjects == (dry.id,))
    dry_pressure = next(change for change in dry_input.changes if change.target == dry.id)
    assert dry_pressure.source == "population"
    assert dry_pressure.key == "population.food_security"
    assert dry_pressure.delta == pytest.approx(-shortage)
    assert dry_pressure.cause_event_ids == (shortage_event.id,)

    control = SimulationEngine((PopulationDomain(), EconomyDomain())).step(economy_tick.world)
    stressed = SimulationEngine((PopulationDomain(), EconomyDomain())).step(
        economy_tick.world, inputs=pressures
    )
    assert control.world.population is not None
    assert stressed.world.population is not None
    control_dry = control.world.population.region(dry.id)
    stressed_dry = stressed.world.population.region(dry.id)
    assert stressed_dry.needs.food_security == pytest.approx(1.0 - shortage)
    assert stressed_dry.total < control_dry.total
    assert stressed_dry.migration_pressure > control_dry.migration_pressure

    pressure_event = next(
        event
        for event in stressed.events
        if event.source == "economy"
        and event.kind == "food-security-pressure"
        and event.subjects == (dry.id,)
    )
    population_event = next(
        event
        for event in stressed.events
        if event.source == "population" and dry.id in event.subjects
    )
    assert pressure_event.cause_event_ids == (shortage_event.id,)
    assert population_event.cause_event_ids == (pressure_event.id,)

    history = EventHistory.from_ticks((economy_tick, stressed))
    why = history.why(population_event.id)
    assert tuple(item.event_id for item in why) == (
        shortage_event.id,
        pressure_event.id,
        population_event.id,
    )


def test_recovery_clears_shortage_and_rebuilds_food_security_pressure() -> None:
    world = _initialized_world(seed=73)
    assert world.geography is not None
    dry = world.geography.region("dry-basin")
    engine = SimulationEngine((PopulationDomain(), EconomyDomain()))

    shortage_tick = SimulationEngine((EconomyDomain(),)).step(world)
    shortage_pressures = population_food_pressure_inputs(
        shortage_tick.world, events=shortage_tick.events
    )
    assert shortage_pressures
    stressed = engine.step(shortage_tick.world, inputs=shortage_pressures)
    assert stressed.world.population is not None
    assert stressed.world.economy is not None
    assert stressed.world.population.region(dry.id).needs.food_security < 1.0

    relief = SimulationInput(
        source="scenario",
        kind="food-relief",
        reason="Emergency reserves reached the dry basin",
        subjects=(dry.id,),
        changes=(
            SimulationChange(
                source="economy",
                key=resource_change_key("food", "stockpile"),
                delta=2_000.0,
                reason="emergency food reserves",
                target=dry.id,
            ),
        ),
    )
    recovered = engine.step(stressed.world, inputs=(relief,))
    assert recovered.world.economy is not None
    recovered_food = recovered.world.economy.region(dry.id).resource("food")
    assert recovered_food.shortage_severity == 0.0
    recovery_event = next(
        event
        for event in recovered.events
        if event.source == "economy"
        and event.kind == "resource-recovery"
        and dry.id in event.subjects
    )

    recovery_pressures = population_food_pressure_inputs(recovered.world, events=recovered.events)
    dry_recovery_input = next(
        pressure for pressure in recovery_pressures if pressure.subjects == (dry.id,)
    )
    dry_recovery = next(change for change in dry_recovery_input.changes if change.target == dry.id)
    assert dry_recovery.cause_event_ids == (recovery_event.id,)

    restored = engine.step(recovered.world, inputs=recovery_pressures)
    assert restored.world.population is not None
    assert restored.world.population.region(dry.id).needs.food_security == pytest.approx(1.0)


def test_shortage_event_keeps_causal_reserve_loss_chain() -> None:
    world = _initialized_world(seed=79)
    assert world.geography is not None
    dry = world.geography.region("dry-basin")
    world = _with_food_stockpile(world, dry.id, 1_000.0)
    first = SimulationEngine((EconomyDomain(),)).step(world)
    assert first.world.economy is not None
    assert first.world.economy.region(dry.id).resource("food").shortage_severity == 0.0

    reserve_loss = SimulationInput(
        source="scenario",
        kind="reserve-loss",
        reason="A storage failure destroyed emergency food reserves",
        subjects=(dry.id,),
        changes=(
            SimulationChange(
                source="economy",
                key=resource_change_key("food", "stockpile"),
                delta=-500.0,
                reason="food reserves were lost",
                target=dry.id,
            ),
        ),
    )
    second = SimulationEngine((EconomyDomain(),)).step(first.world, inputs=(reserve_loss,))
    input_event = next(event for event in second.events if event.source == "scenario")
    shortage_event = next(
        event
        for event in second.events
        if event.source == "economy"
        and event.kind == "resource-shortage"
        and dry.id in event.subjects
        and any(change.key.endswith("shortage_severity") for change in event.changes)
    )
    assert shortage_event.cause_event_ids == (input_event.id,)
    assert shortage_event.changes

    history = EventHistory.from_ticks((second,))
    why = history.why(shortage_event.id)
    assert tuple(item.event_id for item in why) == (input_event.id, shortage_event.id)


def test_economy_replay_is_deterministic_across_multiple_ticks() -> None:
    first_world = _initialized_world(seed=83, total_per_region=1_500)
    second_world = _initialized_world(seed=83, total_per_region=1_500)

    first = SimulationEngine((PopulationDomain(), EconomyDomain())).run(first_world, years=3)
    second = SimulationEngine((PopulationDomain(), EconomyDomain())).run(second_world, years=3)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
