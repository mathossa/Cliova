import pytest

from cliova.simulation.domains.population import initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.types import EntityId, WorldState, entity_id


def test_world_state_rejects_population_region_outside_geography() -> None:
    world = initialize_population(
        create_starter_world(seed=59, world_key="population-integrity"),
        total_per_region=100,
    )
    assert world.population is not None

    payload = world.model_dump(mode="python")
    orphan: EntityId = entity_id(world.id, "region", "orphan-region")
    payload["population"]["regions"][0]["region_id"] = orphan.model_dump(mode="python")

    with pytest.raises(
        ValueError,
        match="population regions must reference regions in world geography",
    ):
        WorldState.model_validate(payload)
