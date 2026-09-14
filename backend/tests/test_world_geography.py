from statistics import mean

import pytest

from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.domains.world.graph import (
    is_connected,
    shortest_path,
    shortest_travel_cost,
)
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import RegionState, WorldState


def test_seeded_world_geography_is_reproducible_connected_and_serializable() -> None:
    first = WorldState.create(seed=42)
    second = WorldState.create(seed=42)

    assert first.geography is not None
    assert len(first.geography.regions) == 6
    assert is_connected(first.geography)
    assert first.geography == second.geography
    assert first.model_dump_json() == second.model_dump_json()

    restored = WorldState.model_validate_json(first.model_dump_json())
    assert restored == first
    assert restored.geography is not None
    assert is_connected(restored.geography)


def test_seed_changes_generated_geography() -> None:
    first = WorldState.create(seed=42)
    second = WorldState.create(seed=43)

    assert first.geography is not None
    assert second.geography is not None
    assert first.geography != second.geography


def test_regions_expose_environmental_and_resource_inputs() -> None:
    geography = WorldState.create(seed=7).geography
    assert geography is not None

    for region in geography.regions:
        assert 0.0 <= region.habitability <= 1.0
        assert 0.0 <= region.water_access <= 1.0
        assert 0.0 <= region.climate_pressure <= 1.0
        assert region.resources
        assert 0.0 <= region.resource_potential("metal_ores") <= 1.0
        assert region.resource_potential("not-present") == 0.0


def test_seeded_geography_applies_physical_biases_without_fixed_templates() -> None:
    regions: list[RegionState] = []
    for seed in range(64):
        geography = WorldState.create(seed=seed).geography
        assert geography is not None
        regions.extend(geography.regions)

    arid = [region for region in regions if region.biome == "arid"]
    tropical = [region for region in regions if region.biome == "tropical"]
    alpine = [region for region in regions if region.biome == "alpine"]
    temperate = [region for region in regions if region.biome == "temperate"]
    forests = [region for region in regions if region.terrain == "forest"]
    highlands = [region for region in regions if region.terrain == "highland"]
    wetlands = [region for region in regions if region.terrain == "wetland"]

    assert arid and tropical and alpine and temperate and forests and highlands and wetlands

    assert mean(region.water_access for region in arid) < mean(
        region.water_access for region in tropical
    )
    assert mean(region.climate_pressure for region in alpine) > mean(
        region.climate_pressure for region in temperate
    )
    assert mean(region.resource_potential("timber") for region in forests) > mean(
        region.resource_potential("timber") for region in highlands
    )

    assert all(region.habitability <= 0.54 for region in arid)
    assert all(region.climate_pressure >= 0.55 for region in arid)
    assert all(region.water_access >= 0.48 for region in wetlands)
    assert all(region.resource_potential("metal_ores") >= 0.44 for region in highlands)

    arid_forest_or_wetland = mean(region.terrain in {"forest", "wetland"} for region in arid)
    tropical_forest_or_wetland = mean(
        region.terrain in {"forest", "wetland"} for region in tropical
    )
    assert arid_forest_or_wetland < tropical_forest_or_wetland

    # Profiles bias outcomes without turning a label into one fixed template.
    assert len({region.water_access for region in tropical}) > 1
    assert len({region.resource_potential("timber") for region in forests}) > 1


def test_starter_fixture_has_meaningfully_different_connected_regions() -> None:
    world = create_starter_world(seed=11)
    replay = create_starter_world(seed=11)
    geography = world.geography

    assert geography is not None
    assert world.model_dump_json() == replay.model_dump_json()
    assert is_connected(geography)

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


def test_tick_engine_preserves_static_geography_without_world_changes() -> None:
    world = create_starter_world(seed=5)
    result = SimulationEngine().step(world)

    assert result.world.geography == world.geography
    assert result.world.time.tick == 1
    assert result.world.time.year == 1
