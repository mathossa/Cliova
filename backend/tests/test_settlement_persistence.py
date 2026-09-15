import os

import pytest

from cliova.infrastructure.persistence.migrations import apply_migrations
from cliova.infrastructure.persistence.postgres import PostgresPersistence
from cliova.simulation.domains.settlements import initialize_settlements
from cliova.simulation.types import SettlementState, StructureState, WorldState, entity_id

pytestmark = pytest.mark.integration


def test_nonempty_settlement_state_round_trips_through_world_persistence() -> None:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    apply_migrations(url)

    world = WorldState.create(seed=653, world_key="settlement-persistence")
    assert world.geography is not None
    region_id = world.geography.regions[0].id
    settlement_key = "persistent-harbour"
    settlement_id = entity_id(world.id, "settlement", settlement_key)
    structure_key = f"{settlement_key}:storage"
    world = initialize_settlements(
        world,
        settlements=(
            SettlementState(
                id=settlement_id,
                key=settlement_key,
                name="Persistent Harbour",
                region_id=region_id,
                established_year=0,
                population_estimate=80,
                archetype="permanent",
            ),
        ),
        structures=(
            StructureState(
                id=entity_id(world.id, "structure", structure_key),
                key=structure_key,
                definition_id="storage",
                settlement_id=settlement_id,
                established_year=0,
            ),
        ),
    )
    repository = PostgresPersistence(url)
    repository.create_world(world)

    assert repository.load_world(world.id.value) == world
    assert repository.load_snapshot(world.id.value, 0) == world
