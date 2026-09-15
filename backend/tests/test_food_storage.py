from math import isfinite

import pytest
from simulation_quality import HeadlessTrace, assert_core_invariants, assert_replay_equivalent

from cliova.simulation.domains.economy import (
    DEFAULT_FOOD_STORAGE_CONFIG,
    EconomyDomain,
    FoodStorageConfig,
    initialize_economy,
    population_food_pressure_inputs,
)
from cliova.simulation.domains.economy.storage import balance_food_storage
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.scenarios import ScenarioDomain
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import (
    CapabilityProgress,
    FoodReserveState,
    ResourceEconomyState,
    SimulationInput,
    SimulationRunResult,
    SocietyKnowledgeState,
    TickResult,
    WorldState,
    entity_id,
)


def _food_resource(*, perishable: float = 0.0, durable: float = 0.0) -> ResourceEconomyState:
    reserves = FoodReserveState(perishable=perishable, durable=durable)
    return ResourceEconomyState(
        resource="food",
        stockpile=reserves.total,
        food_reserves=reserves,
    )


def _advance_storage(
    current: ResourceEconomyState,
    *,
    production: float,
    demand: float,
    preservation_modifier: float = 1.0,
    config: FoodStorageConfig = DEFAULT_FOOD_STORAGE_CONFIG,
) -> ResourceEconomyState:
    balance = balance_food_storage(
        current,
        production=production,
        demand=demand,
        preservation_modifier=preservation_modifier,
        config=config,
    )
    return ResourceEconomyState(
        resource="food",
        production=production,
        demand=demand,
        consumed=balance.consumed,
        stockpile=balance.stockpile,
        surplus=max(0.0, production - demand),
        deficit=balance.deficit,
        shortage_severity=balance.shortage_severity,
        food_reserves=balance.reserves,
    )


def _initialized_world(*, seed: int, total_per_region: int = 1_000) -> WorldState:
    return initialize_economy(
        initialize_population(
            create_starter_world(seed=seed, world_key=f"food-storage-{seed}"),
            total_per_region=total_per_region,
        )
    )


def _run_with_food_boundary(initial: WorldState, years: int) -> HeadlessTrace:
    engine = SimulationEngine((PopulationDomain(), EconomyDomain()))
    world = initial
    pending: tuple[SimulationInput, ...] = ()
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


def test_perishable_reserves_decay_faster_than_durable_reserves() -> None:
    config = FoodStorageConfig(
        perishable_retention=0.50,
        durable_retention=0.95,
        preservation_fraction=0.0,
    )
    current = _food_resource(perishable=100.0, durable=100.0)

    balance = balance_food_storage(
        current,
        production=0.0,
        demand=0.0,
        preservation_modifier=1.0,
        config=config,
    )

    assert balance.reserves.perishable == pytest.approx(50.0)
    assert balance.reserves.durable == pytest.approx(95.0)
    assert balance.reserves.perishable_spoilage == pytest.approx(50.0)
    assert balance.reserves.durable_spoilage == pytest.approx(5.0)


def test_food_accounting_and_consumption_order_are_explicit_and_conservative() -> None:
    no_loss = FoodStorageConfig(
        perishable_retention=1.0,
        durable_retention=1.0,
        preservation_fraction=0.0,
    )
    current = _food_resource(perishable=40.0, durable=100.0)
    ordered = balance_food_storage(
        current,
        production=30.0,
        demand=90.0,
        preservation_modifier=1.0,
        config=no_loss,
    )

    assert ordered.reserves.consumed_from_production == pytest.approx(30.0)
    assert ordered.reserves.consumed_from_perishable == pytest.approx(40.0)
    assert ordered.reserves.consumed_from_durable == pytest.approx(20.0)
    assert ordered.reserves.perishable == 0.0
    assert ordered.reserves.durable == pytest.approx(80.0)
    assert ordered.deficit == 0.0

    current = _food_resource(perishable=80.0, durable=40.0)
    balance = balance_food_storage(
        current,
        production=70.0,
        demand=100.0,
        preservation_modifier=1.0,
    )
    opening_supply = current.stockpile + 70.0
    accounted = balance.consumed + balance.reserves.spoilage_loss + balance.stockpile
    assert opening_supply == pytest.approx(accounted, abs=2e-6)
    assert balance.reserves.preserved <= opening_supply - balance.consumed + 1e-6
    assert min(
        balance.reserves.perishable,
        balance.reserves.durable,
        balance.deficit,
        balance.stockpile,
    ) >= 0.0


def test_stronger_preservation_retains_more_food_across_ticks() -> None:
    weak = _food_resource()
    strong = _food_resource()

    for _ in range(20):
        weak = _advance_storage(weak, production=120.0, demand=100.0, preservation_modifier=1.0)
        strong = _advance_storage(
            strong,
            production=120.0,
            demand=100.0,
            preservation_modifier=1.75,
        )

    assert weak.food_reserves is not None
    assert strong.food_reserves is not None
    assert strong.stockpile > weak.stockpile
    assert strong.food_reserves.durable > weak.food_reserves.durable


def test_moderate_surplus_converges_instead_of_accumulating_without_bound() -> None:
    current = _food_resource()
    stockpiles: list[float] = []

    for _ in range(400):
        current = _advance_storage(current, production=120.0, demand=100.0)
        stockpiles.append(current.stockpile)

    assert stockpiles[-1] < 3.0 * current.demand
    assert stockpiles[-1] == pytest.approx(stockpiles[199], abs=1e-3)


def test_production_shock_exhausts_reserves_then_recovery_rebuilds_them() -> None:
    current = _food_resource()
    for _ in range(12):
        current = _advance_storage(current, production=130.0, demand=100.0)
    assert current.stockpile > 0.0

    shortage = None
    for _ in range(12):
        current = _advance_storage(current, production=0.0, demand=100.0)
        if current.shortage_severity > 0.0:
            shortage = current
            break

    assert shortage is not None
    assert shortage.stockpile == 0.0
    assert shortage.deficit > 0.0

    recovered = _advance_storage(shortage, production=130.0, demand=100.0)
    assert recovered.shortage_severity == 0.0
    assert recovered.stockpile > 0.0


def test_preservation_capability_is_scoped_to_storage_not_food_methods() -> None:
    base = _initialized_world(seed=211)
    assert base.geography is not None
    fertile = base.geography.region("fertile-lowlands")
    society_id = entity_id(base.id, "society", "preservation-test")

    baseline = initialize_knowledge(
        base,
        (SocietyKnowledgeState(society_id=society_id, region_ids=(fertile.id,)),),
    )
    improved = initialize_knowledge(
        base,
        (
            SocietyKnowledgeState(
                society_id=society_id,
                region_ids=(fertile.id,),
                capabilities=(
                    CapabilityProgress(capability_key="food_preservation", proficiency=1.0),
                ),
            ),
        ),
    )
    knowledge = KnowledgeDomain()

    assert knowledge.capability_modifier(improved, fertile.id, "food", "preservation") == 1.75
    for method in ("cultivation", "pastoralism", "foraging", "fishing"):
        assert knowledge.capability_modifier(improved, fertile.id, "food", method) == 1.0

    baseline_tick = SimulationEngine(
        (EconomyDomain(knowledge.capability_modifier),)
    ).step(baseline)
    improved_tick = SimulationEngine(
        (EconomyDomain(knowledge.capability_modifier),)
    ).step(improved)
    assert baseline_tick.world.economy is not None
    assert improved_tick.world.economy is not None
    baseline_food = baseline_tick.world.economy.region(fertile.id).resource("food")
    improved_food = improved_tick.world.economy.region(fertile.id).resource("food")

    assert improved_food.production == baseline_food.production
    assert improved_food.food_production == baseline_food.food_production
    assert improved_food.stockpile > baseline_food.stockpile
    assert baseline_food.food_reserves is not None
    assert improved_food.food_reserves is not None
    assert improved_food.food_reserves.durable > baseline_food.food_reserves.durable


def test_aggregate_shortage_population_and_scenario_boundaries_remain_compatible() -> None:
    world = _initialized_world(seed=223)
    assert world.geography is not None
    dry = world.geography.region("dry-basin")

    tick = SimulationEngine((EconomyDomain(), ScenarioDomain())).step(world)
    assert tick.world.economy is not None
    food = tick.world.economy.region(dry.id).resource("food")
    assert food.food_reserves is not None
    assert food.shortage_severity > 0.0

    pressures = population_food_pressure_inputs(tick.world, events=tick.events)
    dry_pressure = next(item for item in pressures if item.subjects == (dry.id,))
    food_security = next(change for change in dry_pressure.changes if change.target == dry.id)
    assert food_security.delta == pytest.approx(-food.shortage_severity)
    assert any(pressure.region_id == dry.id for pressure in tick.world.pressures)


def test_storage_replay_includes_equivalent_reserves_and_history() -> None:
    def world_factory() -> WorldState:
        return _initialized_world(seed=227, total_per_region=1_500)

    def engine_factory() -> SimulationEngine:
        return SimulationEngine((PopulationDomain(), EconomyDomain(), ScenarioDomain()))

    first, second = assert_replay_equivalent(
        world_factory,
        engine_factory,
        years=8,
    )
    assert first.run.world == second.run.world


@pytest.mark.parametrize("years", (25, 50, 100))
def test_food_storage_long_run_accounting_and_invariants(years: int) -> None:
    initial = _initialized_world(seed=229 + years, total_per_region=2_000)
    trace = _run_with_food_boundary(initial, years)
    assert_core_invariants(trace)
    assert initial.geography is not None
    geography_ids = {region.id for region in initial.geography.regions}

    previous_world = initial
    for tick in trace.run.ticks:
        assert tick.world.economy is not None
        assert previous_world.economy is not None
        assert {regional.region_id for regional in tick.world.economy.regions} <= geography_ids
        for regional in tick.world.economy.regions:
            food = regional.resource("food")
            previous_food = previous_world.economy.region(regional.region_id).resource("food")
            assert food.food_reserves is not None
            reserves = food.food_reserves
            assert all(
                isfinite(value) and value >= 0.0
                for value in (
                    food.production,
                    food.demand,
                    food.consumed,
                    food.stockpile,
                    food.deficit,
                    reserves.perishable,
                    reserves.durable,
                    reserves.preserved,
                    reserves.perishable_spoilage,
                    reserves.durable_spoilage,
                )
            )
            assert food.stockpile == pytest.approx(reserves.total, abs=1e-6)
            assert food.consumed == pytest.approx(reserves.consumed, abs=1e-6)
            assert previous_food.stockpile + food.production == pytest.approx(
                food.consumed + reserves.spoilage_loss + food.stockpile,
                abs=3e-6,
            )
        previous_world = tick.world
