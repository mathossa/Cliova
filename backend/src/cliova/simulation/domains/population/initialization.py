"""Explicit helpers for creating inhabited aggregate population state."""

from cliova.simulation.types import PopulationDomainState, RegionalPopulationState, WorldState

DEFAULT_INITIAL_POPULATION = 1_000


def initialize_population(
    world: WorldState, *, total_per_region: int = DEFAULT_INITIAL_POPULATION
) -> WorldState:
    """Populate every existing region with the same neutral aggregate starting state.

    Geography only defines physical opportunity. Population initialization is kept in
    this domain so the world domain does not decide where or how many people exist.
    """
    if type(total_per_region) is not int or total_per_region <= 0:
        raise ValueError("total_per_region must be a positive integer")
    if world.geography is None:
        raise ValueError("population initialization requires geography")
    if world.population is not None and world.population.regions:
        raise ValueError("population is already initialized")

    population = PopulationDomainState(
        regions=tuple(
            RegionalPopulationState(region_id=region.id, total=total_per_region)
            for region in world.geography.regions
        )
    )
    return world.model_copy(update={"population": population})
