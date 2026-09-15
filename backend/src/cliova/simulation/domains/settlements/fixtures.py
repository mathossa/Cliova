"""Small generic settlement fixture expressed through authoritative inputs."""

from cliova.simulation.domains.settlements.domain import (
    establish_settlement_input,
    establish_structure_input,
)
from cliova.simulation.types import EntityId, SimulationInput, WorldState, entity_id


def starter_settlement_inputs(
    world: WorldState,
    *,
    society_id: EntityId,
    core_region_id: EntityId,
    camp_region_id: EntityId,
    core_population_estimate: int = 700,
    camp_population_estimate: int = 120,
) -> tuple[SimulationInput, ...]:
    """Prove the boundary with one permanent place, one seasonal camp, and three structures."""

    permanent_key = f"{society_id.value}:river-haven"
    camp_key = f"{society_id.value}:seasonal-upland-camp"
    permanent_id = entity_id(world.id, "settlement", permanent_key)
    camp_id = entity_id(world.id, "settlement", camp_key)
    return (
        establish_settlement_input(
            world,
            key=permanent_key,
            name="River Haven",
            region_id=core_region_id,
            archetype="permanent",
            associated_subject=society_id,
            population_estimate=core_population_estimate,
        ),
        establish_settlement_input(
            world,
            key=camp_key,
            name="Upland Seasonal Camp",
            region_id=camp_region_id,
            archetype="seasonal_camp",
            associated_subject=society_id,
            population_estimate=camp_population_estimate,
            status="dormant",
        ),
        establish_structure_input(
            world,
            key=f"{permanent_key}:storage",
            definition_id="storage",
            settlement_id=permanent_id,
        ),
        establish_structure_input(
            world,
            key=f"{permanent_key}:workshop",
            definition_id="workshop",
            settlement_id=permanent_id,
        ),
        establish_structure_input(
            world,
            key=f"{camp_key}:livestock-enclosure",
            definition_id="livestock_enclosure",
            settlement_id=camp_id,
        ),
    )
