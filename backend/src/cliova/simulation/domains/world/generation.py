"""Deterministic headless generation of authoritative physical geography."""

from dataclasses import dataclass

import networkx as nx  # type: ignore[import-untyped]

from cliova.simulation.randomness import RandomSource, random_for
from cliova.simulation.types import (
    BiomeKind,
    EntityId,
    GeographyState,
    RegionConnection,
    RegionState,
    ResourcePotential,
    TerrainKind,
    entity_id,
)

REGION_COUNT = 6
RESOURCE_KINDS: tuple[str, ...] = ("arable_land", "metal_ores", "stone", "timber")
TERRAINS: tuple[TerrainKind, ...] = (
    "plain",
    "plateau",
    "basin",
    "highland",
    "forest",
    "wetland",
    "coast",
)
BIOMES: tuple[BiomeKind, ...] = (
    "temperate",
    "semi_arid",
    "arid",
    "boreal",
    "tropical",
    "alpine",
)


@dataclass(frozen=True)
class _BiomeProfile:
    habitability: float
    water_access: float
    climate_pressure: float
    arable_land: float
    timber: float


@dataclass(frozen=True)
class _TerrainModifier:
    habitability: float = 0.0
    water_access: float = 0.0
    climate_pressure: float = 0.0
    arable_land: float = 0.0
    metal_ores: float = 0.0
    stone: float = 0.0
    timber: float = 0.0


# Profiles are broad physical tendencies, not fixed outcomes. Seeded local variation is
# applied after these values so two regions with the same labels can still differ.
BIOME_PROFILES: dict[BiomeKind, _BiomeProfile] = {
    "temperate": _BiomeProfile(0.72, 0.65, 0.25, 0.68, 0.62),
    "semi_arid": _BiomeProfile(0.48, 0.32, 0.55, 0.42, 0.22),
    "arid": _BiomeProfile(0.30, 0.15, 0.72, 0.18, 0.08),
    "boreal": _BiomeProfile(0.45, 0.58, 0.52, 0.28, 0.72),
    "tropical": _BiomeProfile(0.62, 0.78, 0.38, 0.58, 0.82),
    "alpine": _BiomeProfile(0.28, 0.48, 0.72, 0.12, 0.18),
}

TERRAIN_MODIFIERS: dict[TerrainKind, _TerrainModifier] = {
    "plain": _TerrainModifier(
        habitability=0.12,
        climate_pressure=-0.05,
        arable_land=0.15,
        metal_ores=-0.08,
        stone=-0.05,
        timber=-0.10,
    ),
    "plateau": _TerrainModifier(
        habitability=-0.04,
        water_access=-0.08,
        climate_pressure=0.08,
        arable_land=-0.08,
        metal_ores=0.12,
        stone=0.18,
        timber=-0.08,
    ),
    "basin": _TerrainModifier(
        water_access=0.12,
        climate_pressure=0.08,
        arable_land=0.05,
        metal_ores=0.05,
        stone=0.08,
        timber=-0.05,
    ),
    "highland": _TerrainModifier(
        habitability=-0.18,
        water_access=0.03,
        climate_pressure=0.16,
        arable_land=-0.16,
        metal_ores=0.22,
        stone=0.24,
        timber=-0.08,
    ),
    "forest": _TerrainModifier(
        habitability=0.02,
        water_access=0.12,
        climate_pressure=-0.03,
        arable_land=-0.05,
        metal_ores=-0.05,
        stone=-0.08,
        timber=0.38,
    ),
    "wetland": _TerrainModifier(
        habitability=-0.08,
        water_access=0.45,
        climate_pressure=0.03,
        arable_land=0.04,
        metal_ores=-0.08,
        stone=-0.12,
        timber=0.12,
    ),
    "coast": _TerrainModifier(
        habitability=0.08,
        water_access=0.25,
        climate_pressure=0.02,
        arable_land=0.03,
        metal_ores=0.02,
        stone=-0.02,
    ),
}

# Every terrain remains possible for every biome, but implausible combinations are rare.
# This keeps unusual local geography possible without making labels independent.
TERRAIN_WEIGHTS: dict[BiomeKind, tuple[float, ...]] = {
    "temperate": (1.4, 0.8, 1.0, 0.6, 1.3, 1.0, 1.0),
    "semi_arid": (1.0, 1.4, 1.3, 0.8, 0.25, 0.15, 0.7),
    "arid": (0.8, 1.4, 1.5, 1.0, 0.10, 0.05, 0.4),
    "boreal": (0.8, 0.8, 0.7, 0.8, 1.6, 1.0, 0.6),
    "tropical": (0.8, 0.6, 0.8, 0.5, 1.6, 1.2, 1.2),
    "alpine": (0.2, 1.0, 0.4, 1.8, 0.5, 0.2, 0.3),
}


def _choice[T](rng: RandomSource, values: tuple[T, ...]) -> T:
    index = min(int(rng.random() * len(values)), len(values) - 1)
    return values[index]


def _weighted_choice[T](
    rng: RandomSource,
    values: tuple[T, ...],
    weights: tuple[float, ...],
) -> T:
    if not values or len(values) != len(weights):
        raise ValueError("weighted choices require equally sized values and weights")

    total = sum(weights)
    if total <= 0.0:
        raise ValueError("weighted choices require positive total weight")

    target = rng.random() * total
    cumulative = 0.0
    for value, weight in zip(values, weights, strict=True):
        cumulative += weight
        if target < cumulative:
            return value
    return values[-1]


def _bounded_value(rng: RandomSource, center: float, *, spread: float) -> float:
    varied = center + (((2.0 * rng.random()) - 1.0) * spread)
    return round(min(1.0, max(0.0, varied)), 6)


def _generate_region(*, world_id: EntityId, index: int, rng: RandomSource) -> RegionState:
    biome = _choice(rng, BIOMES)
    terrain = _weighted_choice(rng, TERRAINS, TERRAIN_WEIGHTS[biome])
    biome_profile = BIOME_PROFILES[biome]
    terrain_modifier = TERRAIN_MODIFIERS[terrain]

    habitability = _bounded_value(
        rng,
        biome_profile.habitability + terrain_modifier.habitability,
        spread=0.12,
    )
    water_access = _bounded_value(
        rng,
        biome_profile.water_access + terrain_modifier.water_access,
        spread=0.12,
    )
    climate_pressure = _bounded_value(
        rng,
        biome_profile.climate_pressure + terrain_modifier.climate_pressure,
        spread=0.12,
    )
    resources = (
        ResourcePotential(
            resource="arable_land",
            potential=_bounded_value(
                rng,
                biome_profile.arable_land + terrain_modifier.arable_land,
                spread=0.15,
            ),
        ),
        ResourcePotential(
            resource="metal_ores",
            potential=_bounded_value(
                rng,
                0.40 + terrain_modifier.metal_ores,
                spread=0.18,
            ),
        ),
        ResourcePotential(
            resource="stone",
            potential=_bounded_value(
                rng,
                0.40 + terrain_modifier.stone,
                spread=0.18,
            ),
        ),
        ResourcePotential(
            resource="timber",
            potential=_bounded_value(
                rng,
                biome_profile.timber + terrain_modifier.timber,
                spread=0.15,
            ),
        ),
    )

    return RegionState(
        id=entity_id(world_id, "region", f"seeded:{index}"),
        key=f"seeded:{index}",
        terrain=terrain,
        biome=biome,
        habitability=habitability,
        water_access=water_access,
        climate_pressure=climate_pressure,
        resources=resources,
    )


def generate_geography(*, world_id: EntityId, seed: int) -> GeographyState:
    """Generate deterministic region state while keeping NetworkX non-authoritative."""
    if world_id.kind != "world":
        raise ValueError("world_id must identify a world")

    rng = random_for(seed, 0, "world.geography.v1")
    regions = tuple(
        _generate_region(world_id=world_id, index=index, rng=rng) for index in range(REGION_COUNT)
    )

    # NetworkX supplies the generic graph foundation.
    # Only serialized Cliova edges are authoritative.
    graph = nx.cycle_graph(REGION_COUNT)
    extra_candidates = {
        tuple(sorted((index, (index + 2) % REGION_COUNT))) for index in range(REGION_COUNT)
    }
    for a, b in sorted(extra_candidates):
        if rng.random() < 0.35:
            graph.add_edge(a, b)

    if not nx.is_connected(graph):
        raise RuntimeError("generated geography must be connected")

    connections = tuple(
        RegionConnection(
            a=regions[a].id,
            b=regions[b].id,
            travel_cost=round(1.0 + (2.0 * rng.random()), 6),
        )
        for a, b in sorted(tuple(sorted(edge)) for edge in graph.edges())
    )
    return GeographyState(regions=regions, connections=connections)
