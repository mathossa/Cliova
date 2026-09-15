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
from cliova.simulation.domains.population.seasonal_access import (
    SEASONAL_PASTORAL_ACCESS_SHARE,
    SeasonalSubsistenceAccessDomain,
    initialize_society_region_relationships,
)

__all__ = [
    "DEFAULT_INITIAL_POPULATION",
    "FOOD_SECURITY",
    "HEALTH",
    "MATERIAL_SECURITY",
    "MIGRATION_PRESSURE",
    "POPULATION_TOTAL",
    "SAFETY",
    "SEASONAL_PASTORAL_ACCESS_SHARE",
    "SOCIAL_CONFIDENCE",
    "PopulationDomain",
    "PopulationNeedTarget",
    "SeasonalSubsistenceAccessDomain",
    "initialize_population",
    "initialize_society_region_relationships",
    "population_need_input",
]
