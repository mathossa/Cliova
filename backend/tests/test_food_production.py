from math import isfinite

import pytest

from simulation_quality import HeadlessTrace, assert_core_invariants

from cliova.simulation.domains.economy import (
    LABOUR_SHARE,
    EconomyDomain,
    initialize_economy,
    population_food_pressure_inputs,
)
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import (
    CapabilityProgress,
    GeographyState,
    RegionState,
    ResourcePotential,
    SimulationRunResult,
    SocietyKnowledgeState,
    TickResult,
    WorldState,
    entity_id,
)


def _profile_world(
    *,
    seed: int = 151,
    total: int = 1_000,
    arable: float,
    grazing: float,
    wild_food: float,
    aquatic_food: float,
) -> WorldState:
    world = WorldState.create(seed=seed, world_key="food-profile")
    region_id = entity_id(world.id, "region", "food-profile")
    region = RegionState(
        id=region_id,
        key="food-profile",
        terrain="plain",
        biome="temperate",
        habitability=0.7,
        water_access=0.6,
        climate_pressure=0.3,
        resources=(
            ResourcePotential(resource="arable_land", potential=arable),
            ResourcePotential(resource="grazing", potential=grazing),
            ResourcePotential(resource="wild_food", potential=wild_food),
            ResourcePotential(resource="aquatic_food", potential=aquatic_food),
            ResourcePotential(resource="metal_ores", potential=0.2),
            ResourcePotential(resource="stone", potential=0.3),
            ResourcePotential(resource="timber", potential=0.4),
        ),
    )
    world = world.model_copy(update={"geography": GeographyState(regions=(region,), connections=())})
    return initialize_economy(initialize_population(world, total_per_region=total))


def _food_after_tick(world: WorldState, domain: EconomyDomain | None = None):
    result = SimulationEngine((domain or EconomyDomain(),)).step(world)
    assert result.world.economy is not None
    return result, result.world.economy.regions[0].resource("food")


@pytest.mark.parametrize(
    ("profile", "expected_strong_method"),
    [
        ((1.0, 0.05, 0.05, 0.05), "cultivation"),
        ((0.05, 1.0, 0.05, 0.05), "pastoralism"),
        ((0.05, 0.05, 0.05, 1.0), "fishing"),
        ((0.05, 0.05, 0.05, 0.05), None),
    ],
)
def test_contrasting_regional_subsistence_profiles(
    profile: tuple[float, float, float, float], expected_strong_method: str | None
) -> None:
    world = _profile_world(
        arable=profile[0],
        grazing=profile[1],
        wild_food=profile[2],
        aquatic_food=profile[3],
    )
    _, food = _food_after_tick(world)

    methods = {method.method: method for method in food.food_production}
    assert set(methods) == {"cultivation", "pastoralism", "foraging", "fishing"}
    if expected_strong_method is not None:
        strongest = max(methods.values(), key=lambda method: method.regional_potential)
        assert strongest.method == expected_strong_method
        assert strongest.output > 0.0
    else:
        assert food.production < 0.2 * food.demand
        assert food.shortage_severity > 0.8


def test_low_arable_region_benefits_materially_from_alternative_food_opportunities() -> None:
    poor = _profile_world(arable=0.05, grazing=0.05, wild_food=0.05, aquatic_food=0.05)
    diverse = _profile_world(arable=0.05, grazing=1.0, wild_food=1.0, aquatic_food=1.0)

    _, poor_food = _food_after_tick(poor)
    _, diverse_food = _food_after_tick(diverse)

    assert diverse_food.production > 5.0 * poor_food.production
    assert diverse_food.shortage_severity < poor_food.shortage_severity


def test_sustainable_yield_caps_extra_labour_and_population_reduction_can_end_shortage() -> None:
    high = _profile_world(
        total=3_000,
        arable=1.0,
        grazing=1.0,
        wild_food=1.0,
        aquatic_food=1.0,
    )
    higher = _profile_world(
        total=6_000,
        arable=1.0,
        grazing=1.0,
        wild_food=1.0,
        aquatic_food=1.0,
    )
    reduced = _profile_world(
        total=1_500,
        arable=1.0,
        grazing=1.0,
        wild_food=1.0,
        aquatic_food=1.0,
    )

    _, high_food = _food_after_tick(high)
    _, higher_food = _food_after_tick(higher)
    _, reduced_food = _food_after_tick(reduced)

    assert high_food.production == pytest.approx(higher_food.production)
    assert higher_food.production_capacity > high_food.production_capacity
    assert high_food.shortage_severity > 0.0
    assert reduced_food.demand < high_food.demand
    assert reduced_food.shortage_severity == 0.0


def test_food_labour_is_allocated_once_across_methods() -> None:
    world = _profile_world(arable=1.0, grazing=1.0, wild_food=1.0, aquatic_food=1.0)
    _, food = _food_after_tick(world)
    assert world.population is not None
    population = world.population.regions[0]
    available = population.total * LABOUR_SHARE

    allocations = [method.allocated_labour for method in food.food_production]
    assert sum(allocations) <= available + 1e-6
    assert sum(allocations) == pytest.approx(available)
    assert all(allocation < available for allocation in allocations)


def test_cultivation_capability_changes_only_cultivation_output() -> None:
    base = _profile_world(arable=1.0, grazing=1.0, wild_food=1.0, aquatic_food=1.0)
    assert base.geography is not None
    region_id = base.geography.regions[0].id
    society = SocietyKnowledgeState(
        society_id=entity_id(base.id, "society", "food-capability-test"),
        region_ids=(region_id,),
        capabilities=(
            CapabilityProgress(capability_key="cultivation_efficiency", proficiency=0.8),
        ),
    )
    improved = initialize_knowledge(base, (society,))
    knowledge = KnowledgeDomain()

    assert knowledge.capability_modifier(improved, region_id, "food", "cultivation") == 1.2
    assert knowledge.capability_modifier(improved, region_id, "food", "pastoralism") == 1.0
    assert knowledge.capability_modifier(improved, region_id, "food", "foraging") == 1.0
    assert knowledge.capability_modifier(improved, region_id, "food", "fishing") == 1.0

    _, base_food = _food_after_tick(base)
    _, improved_food = _food_after_tick(
        improved, EconomyDomain(knowledge.capability_modifier)
    )
    base_methods = {method.method: method for method in base_food.food_production}
    improved_methods = {method.method: method for method in improved_food.food_production}

    assert improved_methods["cultivation"].output > base_methods["cultivation"].output
    for method in ("pastoralism", "foraging", "fishing"):
        assert improved_methods[method].output == base_methods[method].output


def test_food_method_constraints_are_structured_in_state_and_tick_changes() -> None:
    world = _profile_world(arable=0.05, grazing=0.05, wild_food=0.05, aquatic_food=0.05)
    result, food = _food_after_tick(world)

    for method in food.food_production:
        assert method.output <= method.labour_limited_output + 1e-6
        assert method.output <= method.sustainable_limit + 1e-6
    production_change = next(
        change for change in result.changes if change.key == "economy.food.production"
    )
    keys = {attribute.key for attribute in production_change.attributes}
    assert "food_method.cultivation.allocated_labour" in keys
    assert "food_method.pastoralism.sustainable_limit" in keys
    assert "food_method.foraging.labour_limited_output" in keys
    assert "food_method.fishing.output" in keys


def test_diversified_food_replay_is_deterministic() -> None:
    first_world = _profile_world(
        seed=157,
        total=1_800,
        arable=0.2,
        grazing=0.9,
        wild_food=0.7,
        aquatic_food=0.8,
    )
    second_world = _profile_world(
        seed=157,
        total=1_800,
        arable=0.2,
        grazing=0.9,
        wild_food=0.7,
        aquatic_food=0.8,
    )
    engine = SimulationEngine((PopulationDomain(), EconomyDomain()))

    first = engine.run(first_world, years=5)
    second = engine.run(second_world, years=5)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def _run_with_food_boundary(initial: WorldState, years: int) -> HeadlessTrace:
    engine = SimulationEngine((PopulationDomain(), EconomyDomain()))
    world = initial
    pending = ()
    ticks: list[TickResult] = []
    for _ in range(years):
        tick = engine.step(world, inputs=pending)
        ticks.append(tick)
        world = tick.world
        pending = population_food_pressure_inputs(world, events=tick.events)
    return HeadlessTrace(
        initial_world=initial,
        run=SimulationRunResult(world=world, ticks=tuple(ticks)),
    )


@pytest.mark.parametrize("years", (25, 50, 100))
def test_diversified_food_long_run_invariants(years: int) -> None:
    initial = initialize_economy(
        initialize_population(
            create_starter_world(seed=163, world_key=f"food-long-run-{years}"),
            total_per_region=2_000,
        )
    )
    trace = _run_with_food_boundary(initial, years)
    assert_core_invariants(trace)

    geography_ids = {region.id for region in trace.initial_world.geography.regions}
    for tick in trace.run.ticks:
        assert tick.world.population is not None
        assert tick.world.economy is not None
        population_by_region = {
            population.region_id: population for population in tick.world.population.regions
        }
        assert set(population_by_region) <= geography_ids
        assert {region.region_id for region in tick.world.economy.regions} <= geography_ids
        for regional in tick.world.economy.regions:
            population = population_by_region[regional.region_id]
            food = regional.resource("food")
            assert all(
                isfinite(value)
                for value in (
                    food.production_capacity,
                    food.production,
                    food.demand,
                    food.consumed,
                    food.stockpile,
                    food.surplus,
                    food.deficit,
                    food.shortage_severity,
                )
            )
            assert sum(method.allocated_labour for method in food.food_production) <= (
                population.total * LABOUR_SHARE + 1e-6
            )
            assert food.production == pytest.approx(
                sum(method.output for method in food.food_production), abs=1e-6
            )
            assert all(method.output >= 0.0 for method in food.food_production)
