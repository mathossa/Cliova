from math import isfinite

import pytest
from simulation_quality import HeadlessTrace, assert_core_invariants

from cliova.simulation.domains.economy import (
    FOOD_PRODUCTION_RULES,
    EconomyDomain,
    initialize_economy,
)
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.knowledge.catalog import MOBILE_PASTORALISM_KEY
from cliova.simulation.domains.population import (
    SEASONAL_PASTORAL_ACCESS_SHARE,
    SeasonalSubsistenceAccessDomain,
    initialize_population,
    initialize_society_region_relationships,
)
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    CapabilityProgress,
    GeographyState,
    RegionConnection,
    RegionState,
    ResourcePotential,
    SocietyKnowledgeState,
    SocietyRegionRelationshipState,
    WorldState,
    entity_id,
)


def _region(world: WorldState, key: str, *, grazing: float) -> RegionState:
    return RegionState(
        id=entity_id(world.id, "region", key),
        key=key,
        terrain="plain",
        biome="temperate",
        habitability=0.7,
        water_access=0.4,
        climate_pressure=0.2,
        resources=(
            ResourcePotential(resource="arable_land", potential=0.01),
            ResourcePotential(resource="grazing", potential=grazing),
            ResourcePotential(resource="wild_food", potential=0.01),
            ResourcePotential(resource="aquatic_food", potential=0.01),
            ResourcePotential(resource="timber", potential=0.2),
            ResourcePotential(resource="stone", potential=0.2),
            ResourcePotential(resource="metal_ores", potential=0.2),
        ),
    )


def _world(
    *,
    seed: int = 211,
    mobile: bool,
    adjacent_a_grazing: float = 1.0,
    adjacent_b_grazing: float = 0.6,
    equal_neighbors: bool = False,
) -> tuple[WorldState, dict[str, object]]:
    world = WorldState.create(seed=seed, world_key="seasonal-access")
    core = _region(world, "core", grazing=0.05)
    adjacent_a = _region(world, "adjacent-a", grazing=adjacent_a_grazing)
    adjacent_b = _region(
        world,
        "adjacent-b",
        grazing=adjacent_a_grazing if equal_neighbors else adjacent_b_grazing,
    )
    distant = _region(world, "distant", grazing=1.0)
    travel_b = 1.0 if equal_neighbors else 1.5
    geography = GeographyState(
        regions=(core, adjacent_a, adjacent_b, distant),
        connections=(
            RegionConnection(a=core.id, b=adjacent_a.id, travel_cost=1.0),
            RegionConnection(a=core.id, b=adjacent_b.id, travel_cost=travel_b),
            RegionConnection(a=adjacent_a.id, b=distant.id, travel_cost=1.0),
        ),
    )
    world = world.model_copy(update={"geography": geography})
    world = initialize_economy(initialize_population(world, total_per_region=300))
    society_id = entity_id(world.id, "society", "mobile-herders")
    capabilities = (
        (CapabilityProgress(capability_key=MOBILE_PASTORALISM_KEY, proficiency=0.8),)
        if mobile
        else ()
    )
    world = initialize_knowledge(
        world,
        (
            SocietyKnowledgeState(
                society_id=society_id,
                region_ids=(core.id,),
                capabilities=capabilities,
            ),
        ),
    )
    world = initialize_society_region_relationships(
        world,
        (
            SocietyRegionRelationshipState(
                society_id=society_id,
                core_region_id=core.id,
            ),
        ),
    )
    return world, {
        "society": society_id,
        "core": core,
        "adjacent_a": adjacent_a,
        "adjacent_b": adjacent_b,
        "distant": distant,
    }


def _engine() -> SimulationEngine:
    knowledge = KnowledgeDomain()
    return SimulationEngine(
        (
            SeasonalSubsistenceAccessDomain(),
            EconomyDomain(knowledge.capability_modifier),
        )
    )


def _pastoral(world: WorldState, region_id):
    assert world.economy is not None
    food = world.economy.region(region_id).resource("food")
    return next(method for method in food.food_production if method.method == "pastoralism")


def test_without_mobile_capability_pastoralism_remains_local_only() -> None:
    world, ids = _world(mobile=False)
    result = _engine().step(world)

    relationship = result.world.society_regions[0]
    pastoral = _pastoral(result.world, ids["core"].id)
    assert relationship.temporary_access == ()
    assert pastoral.regional_potential == pytest.approx(0.05)
    assert pastoral.external_potential == 0.0


def test_adjacent_mobile_access_materially_increases_pastoral_production() -> None:
    local_world, local_ids = _world(mobile=False)
    mobile_world, mobile_ids = _world(mobile=True)

    local = _engine().step(local_world).world
    mobile_tick = _engine().step(mobile_world)
    mobile = mobile_tick.world
    access = mobile.society_regions[0].temporary_access
    assert len(access) == 1
    assert access[0].region_id == mobile_ids["adjacent_a"].id
    assert access[0].access_share == pytest.approx(SEASONAL_PASTORAL_ACCESS_SHARE)

    local_pastoral = _pastoral(local, local_ids["core"].id)
    mobile_pastoral = _pastoral(mobile, mobile_ids["core"].id)
    assert mobile_pastoral.external_potential > 0.0
    assert mobile_pastoral.output > 2.0 * local_pastoral.output


def test_non_adjacent_region_and_missing_capability_are_blocked() -> None:
    inaccessible, ids = _world(
        mobile=True,
        adjacent_a_grazing=0.0,
        adjacent_b_grazing=0.0,
    )
    inaccessible_tick = _engine().step(inaccessible)
    assert inaccessible_tick.world.society_regions[0].temporary_access == ()
    assert _pastoral(inaccessible_tick.world, ids["core"].id).external_potential == 0.0
    assert ids["distant"].id not in {
        access.region_id for access in inaccessible_tick.world.society_regions[0].temporary_access
    }

    no_capability, no_capability_ids = _world(mobile=False)
    no_capability_tick = _engine().step(no_capability)
    assert no_capability_tick.world.society_regions[0].temporary_access == ()
    no_capability_pastoral = _pastoral(no_capability_tick.world, no_capability_ids["core"].id)
    assert no_capability_pastoral.external_potential == 0.0


def test_temporary_access_preserves_core_identity_and_population() -> None:
    world, ids = _world(mobile=True)
    assert world.population is not None
    total_before = sum(region.total for region in world.population.regions)
    society_before = world.knowledge.societies[0]

    result = _engine().step(world).world
    assert result.population is not None
    total_after = sum(region.total for region in result.population.regions)
    relationship = result.society_regions[0]
    accessed = relationship.temporary_access[0].region_id

    assert relationship.core_region_id == ids["core"].id
    assert total_after == total_before
    assert result.knowledge.societies[0].society_id == society_before.society_id
    assert result.knowledge.societies[0].region_ids == (ids["core"].id,)
    assert accessed not in result.knowledge.societies[0].region_ids
    assert result.governance == world.governance


def test_multiple_neighbors_choose_deterministically_without_double_counting() -> None:
    first_world, first_ids = _world(mobile=True, equal_neighbors=True)
    second_world, _ = _world(mobile=True, equal_neighbors=True)

    first = _engine().step(first_world)
    second = _engine().step(second_world)
    assert first.model_dump_json() == second.model_dump_json()

    access = first.world.society_regions[0].temporary_access
    assert len(access) == 1
    expected = min(
        (first_ids["adjacent_a"].id, first_ids["adjacent_b"].id),
        key=lambda region_id: region_id.value.hex,
    )
    assert access[0].region_id == expected

    selected_region = next(
        region for region in first.world.geography.regions if region.id == expected
    )
    core_pastoral = _pastoral(first.world, first_ids["core"].id)
    source_pastoral = _pastoral(first.world, expected)
    assert core_pastoral.external_potential == pytest.approx(
        selected_region.resource_potential("grazing") * SEASONAL_PASTORAL_ACCESS_SHARE
    )
    assert core_pastoral.external_potential + source_pastoral.regional_potential == pytest.approx(
        selected_region.resource_potential("grazing")
    )


def test_external_access_respects_authoritative_sustainable_yield_limit() -> None:
    world, ids = _world(mobile=True)
    result = _engine().step(world).world
    access = result.society_regions[0].temporary_access[0]
    source = next(region for region in result.geography.regions if region.id == access.region_id)
    core_pastoral = _pastoral(result, ids["core"].id)
    source_pastoral = _pastoral(result, access.region_id)
    pastoral_rule = next(rule for rule in FOOD_PRODUCTION_RULES if rule.method == "pastoralism")

    assert core_pastoral.output <= core_pastoral.sustainable_limit + 1e-6
    assert source_pastoral.output <= source_pastoral.sustainable_limit + 1e-6
    assert core_pastoral.sustainable_limit == pytest.approx(
        (core_pastoral.regional_potential + core_pastoral.external_potential)
        * pastoral_rule.sustainable_yield_scale
    )
    assert core_pastoral.external_potential + source_pastoral.regional_potential == pytest.approx(
        source.resource_potential("grazing")
    )


def test_history_records_significant_access_once_and_replay_is_deterministic() -> None:
    first_world, ids = _world(mobile=True, seed=223)
    second_world, _ = _world(mobile=True, seed=223)
    first = _engine().run(first_world, years=4)
    second = _engine().run(second_world, years=4)
    assert first.model_dump_json() == second.model_dump_json()

    history = EventHistory.from_run(first)
    access_events = history.query(
        subject=ids["society"],
        event_type="seasonal-subsistence-access",
        source="seasonal_access",
    )
    assert len(access_events) == 1
    event = access_events[0]
    accessed_region = first.world.society_regions[0].temporary_access[0].region_id
    assert ids["society"] in event.subjects
    assert ids["core"].id in event.subjects
    assert accessed_region in event.subjects
    assert event.changes[0].key == "society_regions.temporary_access"
    assert history.causal_chain(event.id)[-1] == event


def test_seasonal_access_long_run_references_and_numeric_invariants() -> None:
    world, _ = _world(mobile=True, seed=227)
    run = _engine().run(world, years=25)
    assert_core_invariants(HeadlessTrace(initial_world=world, run=run))

    assert run.world.geography is not None
    known_regions = {region.id for region in run.world.geography.regions}
    society_ids = [relationship.society_id for relationship in run.world.society_regions]
    assert len(society_ids) == len(set(society_ids))
    for relationship in run.world.society_regions:
        assert relationship.core_region_id in known_regions
        for access in relationship.temporary_access:
            assert access.region_id in known_regions
            assert access.region_id != relationship.core_region_id
            assert 0.0 < access.access_share <= SEASONAL_PASTORAL_ACCESS_SHARE

    for tick in run.ticks:
        assert tick.world.economy is not None
        for regional in tick.world.economy.regions:
            food = regional.resource("food")
            for method in food.food_production:
                assert all(
                    isfinite(value) and value >= 0.0
                    for value in (
                        method.regional_potential,
                        method.external_potential,
                        method.allocated_labour,
                        method.labour_limited_output,
                        method.sustainable_limit,
                        method.output,
                    )
                )
