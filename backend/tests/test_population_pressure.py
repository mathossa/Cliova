import pytest

from cliova.simulation.domains.population import (
    FOOD_SECURITY,
    PopulationNeedTarget,
    initialize_population,
    population_need_input,
)
from cliova.simulation.domains.world.fixtures import create_starter_world


def test_population_need_input_rejects_out_of_range_target() -> None:
    world = initialize_population(
        create_starter_world(seed=61, world_key="population-pressure-validation"),
        total_per_region=100,
    )
    assert world.geography is not None
    region = world.geography.regions[0]

    with pytest.raises(ValueError, match="target must be between 0 and 1"):
        population_need_input(
            world,
            source="economy",
            kind="food-security-pressure",
            reason="invalid pressure",
            targets=(
                PopulationNeedTarget(
                    region_id=region.id,
                    key=FOOD_SECURITY,
                    value=-0.1,
                    reason="invalid target",
                ),
            ),
        )
