"""Explicit helpers for creating inhabited aggregate population state."""

from cliova.simulation.types import (
    EntityId,
    PopulationDomainState,
    RegionalPopulationState,
    WorldState,
)

DEFAULT_INITIAL_POPULATION = 1_000


def initialize_population(
    world: WorldState,
    *,
    total_per_region: int = DEFAULT_INITIAL_POPULATION,
    region_ids: tuple[EntityId, ...] | None = None,
) -> WorldState:
    """Create neutral aggregate starting population in selected geography regions.

    Omitting ``region_ids`` preserves the original fixture behavior and populates every region.
    Passing explicit IDs is useful for generated development worlds where uninhabitable/ocean
    regions should remain empty until a simulation mechanic moves population there.
    """
    if type(total_per_region) is not int or total_per_region <= 0:
        raise ValueError("total_per_region must be a positive integer")
    if world.geography is None:
        raise ValueError("population initialization requires geography")
    if world.population is not None and world.population.regions:
        raise ValueError("population is already initialized")

    geography_ids = {region.id for region in world.geography.regions}
    if region_ids is None:
        selected = geography_ids
    else:
        if not region_ids:
            raise ValueError("region_ids must contain at least one region when provided")
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region_ids must be unique")
        selected = set(region_ids)
        if not selected.issubset(geography_ids):
            raise ValueError("population regions must exist in world geography")

    population = PopulationDomainState(
        regions=tuple(
            RegionalPopulationState(region_id=region.id, total=total_per_region)
            for region in world.geography.regions
            if region.id in selected
        )
    )
    return world.model_copy(update={"population": population})
