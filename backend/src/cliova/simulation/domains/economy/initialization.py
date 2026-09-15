"""Explicit initialization for regional economy state."""

from cliova.simulation.domains.economy.domain import RESOURCE_KINDS
from cliova.simulation.types import (
    EconomyDomainState,
    FoodReserveState,
    RegionalEconomyState,
    ResourceEconomyState,
    WorldState,
)


def initialize_economy(world: WorldState) -> WorldState:
    """Create neutral zero-reserve economies for all currently inhabited regions."""
    if world.population is None or not world.population.regions:
        raise ValueError("economy initialization requires populated regions")
    if world.geography is None:
        raise ValueError("economy initialization requires geography")
    if world.economy is not None and world.economy.regions:
        raise ValueError("economy is already initialized")

    geography_ids = {region.id for region in world.geography.regions}
    regions: list[RegionalEconomyState] = []
    for population in world.population.regions:
        if population.region_id not in geography_ids:
            raise ValueError("population region does not exist in geography")
        regions.append(
            RegionalEconomyState(
                region_id=population.region_id,
                resources=tuple(
                    ResourceEconomyState(
                        resource=resource,
                        food_reserves=FoodReserveState() if resource == "food" else None,
                    )
                    for resource in RESOURCE_KINDS
                ),
            )
        )

    return world.model_copy(update={"economy": EconomyDomainState(regions=tuple(regions))})
