"""Aggregate population, needs and deterministic demographic change."""

from cliova.simulation.domains.population.domain import (
    FOOD_SECURITY,
    HEALTH,
    MATERIAL_SECURITY,
    MIGRATION_PRESSURE,
    POPULATION_TOTAL,
    SAFETY,
    SOCIAL_CONFIDENCE,
    PopulationDomain,
)
from cliova.simulation.domains.population.initialization import (
    DEFAULT_INITIAL_POPULATION,
    initialize_population,
)
from cliova.simulation.domains.population.pressure import (
    PopulationNeedTarget,
    population_need_input,
)

__all__ = [
    "DEFAULT_INITIAL_POPULATION",
    "FOOD_SECURITY",
    "HEALTH",
    "MATERIAL_SECURITY",
    "MIGRATION_PRESSURE",
    "POPULATION_TOTAL",
    "SAFETY",
    "SOCIAL_CONFIDENCE",
    "PopulationDomain",
    "PopulationNeedTarget",
    "initialize_population",
    "population_need_input",
]
