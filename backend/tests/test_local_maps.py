from uuid import uuid4

import pytest

from cliova.api.v1.local_maps import local_map_request
from cliova.application.development import create_development_world, create_simulation_engine
from cliova.simulation.domains.settlements.domain import initialize_settlements
from cliova.simulation.types import SettlementState, StructureState, entity_id


def _world_with_settlements():
    world = create_development_world(seed=734, world_key="local-map-tests")
    assert world.geography is not None
    regions = world.geography.regions
    society_id = world.governance[0].subject_id

    permanent_key = "test-river-haven"
    camp_key = "test-upland-camp"
    permanent_id = entity_id(world.id, "settlement", permanent_key)
    camp_id = entity_id(world.id, "settlement", camp_key)
    storage_key = f"{permanent_key}:storage"
    enclosure_key = f"{camp_key}:livestock"

    return initialize_settlements(
        world,
        settlements=(
            SettlementState(
                id=permanent_id,
                key=permanent_key,
                name="River Haven",
                region_id=regions[0].id,
                associated_subject=society_id,
                established_year=0,
                population_estimate=700,
                archetype="permanent",
            ),
            SettlementState(
                id=camp_id,
                key=camp_key,
                name="Upland Camp",
                region_id=regions[1].id,
                associated_subject=society_id,
                established_year=0,
                population_estimate=120,
                archetype="seasonal_camp",
                status="dormant",
            ),
        ),
        structures=(
            StructureState(
                id=entity_id(world.id, "structure", storage_key),
                key=storage_key,
                definition_id="storage",
                settlement_id=permanent_id,
                established_year=0,
            ),
            StructureState(
                id=entity_id(world.id, "structure", enclosure_key),
                key=enclosure_key,
                definition_id="livestock_enclosure",
                settlement_id=camp_id,
                established_year=0,
            ),
        ),
    )


def test_local_map_projection_is_stable_and_uses_distinct_renderer_paths() -> None:
    world = _world_with_settlements()
    permanent = next(
        item for item in world.settlements.settlements if item.archetype == "permanent"
    )
    camp = next(
        item for item in world.settlements.settlements if item.archetype != "permanent"
    )

    permanent_first = local_map_request(world, permanent.id.value)
    permanent_second = local_map_request(world, permanent.id.value)
    camp_request = local_map_request(world, camp.id.value)

    assert permanent_first.model_dump_json() == permanent_second.model_dump_json()
    assert permanent_first.layout_seed > 0
    assert permanent_first.generation_version == "local-map-v1"
    assert permanent_first.renderer == "settlemaker"
    assert permanent_first.renderer_version == "3.0.1"
    assert permanent_first.authoritative_structures[0].definition_id == "storage"
    assert camp_request.renderer == "cliova_camp"
    assert camp_request.renderer_version == "cliova-camp-v1"
    assert camp_request.authoritative_structures[0].definition_id == "livestock_enclosure"


def test_layout_identity_is_independent_from_unrelated_process_state() -> None:
    world = _world_with_settlements()
    settlement = world.settlements.settlements[0]
    first = local_map_request(world, settlement.id.value)

    # Exercise unrelated UUID/global process state. Layout identity is derived
    # only from stable authoritative identity and the explicit generation version.
    for _ in range(20):
        uuid4()

    second = local_map_request(world, settlement.id.value)
    assert first.layout_seed == second.layout_seed
    assert first.state_fingerprint == second.state_fingerprint


def test_relevant_state_changes_fingerprint_without_reinterpreting_layout_seed() -> None:
    world = _world_with_settlements()
    settlement = world.settlements.settlements[0]
    first = local_map_request(world, settlement.id.value)
    changed = settlement.model_copy(
        update={"population_estimate": settlement.population_estimate + 25}
    )
    changed_world = world.model_copy(
        update={
            "settlements": world.settlements.model_copy(
                update={
                    "settlements": tuple(
                        changed if item.id == settlement.id else item
                        for item in world.settlements.settlements
                    )
                }
            )
        }
    )
    second = local_map_request(changed_world, settlement.id.value)

    assert first.layout_seed == second.layout_seed
    assert first.state_fingerprint != second.state_fingerprint


def test_unknown_settlement_is_explicit() -> None:
    world = _world_with_settlements()
    with pytest.raises(KeyError):
        local_map_request(world, uuid4())


def test_headless_engine_advances_without_local_map_generation() -> None:
    world = create_development_world(seed=735, world_key="headless-local-map-isolation")
    result = create_simulation_engine().step(world)

    assert result.world.time.tick == world.time.tick + 1
    assert result.world.id == world.id