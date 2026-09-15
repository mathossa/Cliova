"""Deterministic starter geography fixtures for integration and simulation tests."""

from cliova.simulation.domains.world.generation import derive_food_opportunities
from cliova.simulation.domains.world.graph import is_connected
from cliova.simulation.types import (
    EntityId,
    GeographyState,
    RegionConnection,
    RegionState,
    ResourcePotential,
    TerrainKind,
    WorldState,
    entity_id,
)


def _resources(
    *,
    terrain: TerrainKind,
    habitability: float,
    water_access: float,
    climate_pressure: float,
    arable_land: float,
    metal_ores: float,
    stone: float,
    timber: float,
) -> tuple[ResourcePotential, ...]:
    return (
        ResourcePotential(resource="arable_land", potential=arable_land),
        *derive_food_opportunities(
            terrain=terrain,
            habitability=habitability,
            water_access=water_access,
            climate_pressure=climate_pressure,
            arable_land=arable_land,
            timber=timber,
        ),
        ResourcePotential(resource="metal_ores", potential=metal_ores),
        ResourcePotential(resource="stone", potential=stone),
        ResourcePotential(resource="timber", potential=timber),
    )


def starter_geography(world_id: EntityId) -> GeographyState:
    """Return a small contrasting world without binding it to rendering or history."""
    fertile = RegionState(
        id=entity_id(world_id, "region", "starter:fertile-lowlands"),
        key="fertile-lowlands",
        terrain="plain",
        biome="temperate",
        habitability=0.92,
        water_access=0.9,
        climate_pressure=0.12,
        resources=_resources(
            terrain="plain",
            habitability=0.92,
            water_access=0.9,
            climate_pressure=0.12,
            arable_land=0.95,
            metal_ores=0.12,
            stone=0.3,
            timber=0.45,
        ),
    )
    dry = RegionState(
        id=entity_id(world_id, "region", "starter:dry-basin"),
        key="dry-basin",
        terrain="basin",
        biome="arid",
        habitability=0.32,
        water_access=0.18,
        climate_pressure=0.82,
        resources=_resources(
            terrain="basin",
            habitability=0.32,
            water_access=0.18,
            climate_pressure=0.82,
            arable_land=0.18,
            metal_ores=0.38,
            stone=0.72,
            timber=0.05,
        ),
    )
    highlands = RegionState(
        id=entity_id(world_id, "region", "starter:mineral-highlands"),
        key="mineral-highlands",
        terrain="highland",
        biome="alpine",
        habitability=0.27,
        water_access=0.52,
        climate_pressure=0.68,
        resources=_resources(
            terrain="highland",
            habitability=0.27,
            water_access=0.52,
            climate_pressure=0.68,
            arable_land=0.08,
            metal_ores=0.92,
            stone=0.9,
            timber=0.2,
        ),
    )
    forest = RegionState(
        id=entity_id(world_id, "region", "starter:river-forest"),
        key="river-forest",
        terrain="forest",
        biome="temperate",
        habitability=0.74,
        water_access=0.86,
        climate_pressure=0.24,
        resources=_resources(
            terrain="forest",
            habitability=0.74,
            water_access=0.86,
            climate_pressure=0.24,
            arable_land=0.62,
            metal_ores=0.2,
            stone=0.34,
            timber=0.92,
        ),
    )

    geography = GeographyState(
        regions=(fertile, dry, highlands, forest),
        connections=(
            RegionConnection(a=fertile.id, b=dry.id, travel_cost=1.4),
            RegionConnection(a=fertile.id, b=forest.id, travel_cost=1.0),
            RegionConnection(a=dry.id, b=highlands.id, travel_cost=1.6),
            RegionConnection(a=forest.id, b=highlands.id, travel_cost=1.8),
        ),
    )
    if not is_connected(geography):
        raise RuntimeError("starter geography must remain connected")
    return geography


def create_starter_world(*, seed: int = 0, world_key: str = "starter-v1") -> WorldState:
    """Create a reproducible starter world whose physical geography is fixture-defined."""
    world = WorldState.create(seed=seed, world_key=world_key)
    return world.model_copy(update={"geography": starter_geography(world.id)})
