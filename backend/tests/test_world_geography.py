import json
from uuid import NAMESPACE_URL, uuid5

import numpy as np
import pytest
from simulation_quality import assert_core_invariants, assert_replay_equivalent, run_headless

from cliova.simulation.domains.economy import EconomyDomain, initialize_economy
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.knowledge.catalog import MOBILE_PASTORALISM_KEY
from cliova.simulation.domains.population import (
    SeasonalSubsistenceAccessDomain,
    initialize_population,
    initialize_society_region_relationships,
)
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.domains.world.generation import generate_geography
from cliova.simulation.domains.world.graph import (
    is_connected,
    shortest_path,
    shortest_travel_cost,
)
from cliova.simulation.domains.world.worldengine_adapter import (
    ADAPTER_VERSION,
    WORLDENGINE_PACKAGE_VERSION,
    WORLDENGINE_REVISION,
    WorldEngineConfig,
    generate_physical_world,
)
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import (
    CapabilityProgress,
    EntityId,
    SocietyKnowledgeState,
    SocietyRegionRelationshipState,
    WorldState,
    entity_id,
)


def _world_id(seed: int, key: str) -> EntityId:
    name = json.dumps(["cliova.world.v1", seed, key], ensure_ascii=True, separators=(",", ":"))
    return EntityId(kind="world", value=uuid5(NAMESPACE_URL, name))


def _initialized_generated_world(seed: int = 42) -> WorldState:
    return initialize_economy(initialize_population(WorldState.create(seed=seed), total_per_region=300))


def test_worldengine_generation_is_reproducible_connected_and_serializable() -> None:
    first = WorldState.create(seed=42)
    second = WorldState.create(seed=42)

    assert first.geography is not None
    assert len(first.geography.regions) == 8
    assert is_connected(first.geography)
    assert first.geography == second.geography
    assert first.model_dump_json() == second.model_dump_json()

    generation = first.geography.generation
    assert generation is not None
    assert generation.generator == "worldengine"
    assert generation.adapter_version == ADAPTER_VERSION
    assert generation.upstream_version == WORLDENGINE_PACKAGE_VERSION
    assert generation.upstream_revision == WORLDENGINE_REVISION
    assert generation.world_seed == 42
    assert {parameter.key for parameter in generation.parameters} == {
        "width",
        "height",
        "region_count",
        "num_plates",
        "ocean_level",
        "gamma_curve",
        "curve_offset",
        "fade_borders",
    }

    restored = WorldState.model_validate_json(first.model_dump_json())
    assert restored == first
    assert restored.geography is not None
    assert is_connected(restored.geography)


def test_different_seeds_produce_meaningfully_different_physical_geography() -> None:
    first = WorldState.create(seed=42)
    second = WorldState.create(seed=43)

    assert first.geography is not None
    assert second.geography is not None
    assert first.geography != second.geography
    first_signature = tuple(
        (
            region.surface,
            region.land_fraction,
            region.mean_elevation,
            region.mean_precipitation,
            region.resource_potential("arable_land"),
        )
        for region in first.geography.regions
    )
    second_signature = tuple(
        (
            region.surface,
            region.land_fraction,
            region.mean_elevation,
            region.mean_precipitation,
            region.resource_potential("arable_land"),
        )
        for region in second.geography.regions
    )
    assert first_signature != second_signature


def test_worldengine_adapter_restores_numpy_global_rng_and_detaches_upstream_objects() -> None:
    np.random.seed(12345)
    before = np.random.get_state()
    physical = generate_physical_world(seed=7)
    after = np.random.get_state()

    assert before[0] == after[0]
    assert np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]
    assert physical.width == 32
    assert physical.height == 16
    assert physical.elevation.shape == (16, 32)
    assert physical.ocean.dtype == np.bool_

    world = WorldState.create(seed=7)
    assert world.geography is not None
    assert not any(
        type(value).__module__.startswith("worldengine")
        for value in (world, world.geography, *world.geography.regions)
    )


def test_region_partition_is_configurable_deterministic_and_has_stable_ids() -> None:
    config = WorldEngineConfig(width=32, height=16, region_count=10, num_plates=8)
    world_id = _world_id(91, "partition")
    first = generate_geography(world_id=world_id, seed=91, config=config)
    second = generate_geography(world_id=world_id, seed=91, config=config)

    assert first == second
    assert len(first.regions) == 10
    assert is_connected(first)
    assert tuple(region.id for region in first.regions) == tuple(region.id for region in second.regions)
    assert [region.key for region in first.regions] == [f"worldengine-v1:{i}" for i in range(10)]
    assert all(connection.travel_cost > 0.0 for connection in first.connections)


def test_generated_regions_expose_land_water_contrast_and_physical_opportunities() -> None:
    geography = WorldState.create(seed=17).geography
    assert geography is not None

    assert all(
        0.0 <= region.resource_potential(resource) <= 1.0
        for region in geography.regions
        for resource in (
            "arable_land",
            "grazing",
            "wild_food",
            "aquatic_food",
            "metal_ores",
            "stone",
            "timber",
        )
    )
    assert all(0.0 <= region.land_fraction <= 1.0 for region in geography.regions)
    assert all(0.0 <= region.topographic_constraint <= 1.0 for region in geography.regions)
    assert len({region.land_fraction for region in geography.regions}) > 1
    assert len({region.mean_elevation for region in geography.regions}) > 1
    assert len({region.resource_potential("arable_land") for region in geography.regions}) > 1
    assert len({region.resource_potential("aquatic_food") for region in geography.regions}) > 1

    wettest = max(geography.regions, key=lambda region: 1.0 - region.land_fraction)
    driest = max(geography.regions, key=lambda region: region.land_fraction)
    assert wettest.resource_potential("aquatic_food") >= driest.resource_potential("aquatic_food")


def test_presentation_geometry_covers_world_without_becoming_simulation_cells() -> None:
    geography = WorldState.create(seed=23).geography
    assert geography is not None
    presentation = geography.presentation
    assert presentation is not None
    assert presentation.width == 32
    assert presentation.height == 16
    assert {geometry.region_id for geometry in presentation.regions} == {
        region.id for region in geography.regions
    }
    assert sum(
        run.x_stop - run.x_start
        for geometry in presentation.regions
        for run in geometry.runs
    ) == presentation.width * presentation.height
    land_cells = sum(run.x_stop - run.x_start for run in presentation.land_runs)
    assert 0 < land_cells < presentation.width * presentation.height


def test_legacy_serialized_geography_loads_without_generation_metadata_or_regeneration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = WorldState.create(seed=31)
    data = world.model_dump(mode="python")
    geography = data["geography"]
    assert isinstance(geography, dict)
    geography.pop("generation", None)
    geography.pop("presentation", None)
    for region in geography["regions"]:
        for field in (
            "surface",
            "land_fraction",
            "coast_fraction",
            "mean_elevation",
            "mean_temperature",
            "mean_precipitation",
            "topographic_constraint",
        ):
            region.pop(field, None)

    def fail_generation(*args, **kwargs):
        del args, kwargs
        raise AssertionError("legacy load must not regenerate physical geography")

    monkeypatch.setattr(
        "cliova.simulation.domains.world.generation.generate_physical_world", fail_generation
    )
    restored = WorldState.model_validate(data)
    assert restored.geography is not None
    assert restored.geography.generation is None
    assert restored.geography.presentation is None
    assert all(region.surface == "land" for region in restored.geography.regions)


def test_generated_geography_is_compatible_with_food_storage_and_seasonal_access() -> None:
    world = _initialized_generated_world(seed=37)
    assert world.geography is not None
    knowledge = KnowledgeDomain()
    society_id = entity_id(world.id, "society", "generated-mobile-herders")
    core = min(world.geography.regions, key=lambda region: region.resource_potential("grazing"))
    world = initialize_knowledge(
        world,
        (
            SocietyKnowledgeState(
                society_id=society_id,
                region_ids=(core.id,),
                capabilities=(
                    CapabilityProgress(capability_key=MOBILE_PASTORALISM_KEY, proficiency=0.8),
                ),
            ),
        ),
    )
    world = initialize_society_region_relationships(
        world,
        (SocietyRegionRelationshipState(society_id=society_id, core_region_id=core.id),),
    )
    result = SimulationEngine(
        (
            SeasonalSubsistenceAccessDomain(),
            EconomyDomain(knowledge.capability_modifier),
        )
    ).step(world)

    assert result.world.economy is not None
    assert result.world.society_regions[0].core_region_id == core.id
    assert all(
        access.region_id in {region.id for region in world.geography.regions}
        for access in result.world.society_regions[0].temporary_access
    )
    for regional_economy in result.world.economy.regions:
        food = regional_economy.resource("food")
        assert {method.method for method in food.food_production} == {
            "cultivation",
            "pastoralism",
            "foraging",
            "fishing",
        }
        assert food.food_reserves is not None
        assert food.food_reserves.total == pytest.approx(food.stockpile)


@pytest.mark.parametrize("years", [25, 50, 100])
def test_generated_world_runs_headless_for_long_horizons(years: int) -> None:
    trace = run_headless(
        lambda: _initialized_generated_world(seed=53),
        SimulationEngine,
        years=years,
    )
    assert_core_invariants(trace)
    assert trace.run.world.time.year == years


def test_generated_world_replays_deterministically() -> None:
    first, second = assert_replay_equivalent(
        lambda: _initialized_generated_world(seed=61),
        SimulationEngine,
        years=25,
    )
    assert first.run.world == second.run.world


def test_starter_fixture_remains_meaningfully_different_and_connected() -> None:
    world = create_starter_world(seed=11)
    replay = create_starter_world(seed=11)
    geography = world.geography

    assert geography is not None
    assert world.model_dump_json() == replay.model_dump_json()
    assert is_connected(geography)
    assert geography.generation is None

    fertile = geography.region("fertile-lowlands")
    dry = geography.region("dry-basin")
    highlands = geography.region("mineral-highlands")
    forest = geography.region("river-forest")

    assert fertile.habitability > dry.habitability
    assert fertile.water_access > dry.water_access
    assert dry.climate_pressure > fertile.climate_pressure
    assert highlands.resource_potential("metal_ores") > fertile.resource_potential("metal_ores")
    assert forest.resource_potential("timber") > dry.resource_potential("timber")

    route = shortest_path(geography, fertile.id, highlands.id)
    assert route == (fertile.id, forest.id, highlands.id)
    assert shortest_travel_cost(geography, fertile.id, highlands.id) == pytest.approx(2.8)


def test_tick_engine_preserves_static_generated_geography() -> None:
    world = WorldState.create(seed=5)
    result = SimulationEngine().step(world)

    assert result.world.geography == world.geography
    assert result.world.time.tick == 1
    assert result.world.time.year == 1
