import pytest

from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.domains.world.graph import (
    is_connected,
    shortest_path,
    shortest_travel_cost,
)
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import WorldState


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
