"""Deterministic headless generation of authoritative physical geography."""

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


def _choice[T](rng: RandomSource, values: tuple[T, ...]) -> T:
    index = min(int(rng.random() * len(values)), len(values) - 1)
    return values[index]


def _unit_value(rng: RandomSource) -> float:
    return round(rng.random(), 6)


def generate_geography(*, world_id: EntityId, seed: int) -> GeographyState:
    """Generate deterministic region state while keeping NetworkX non-authoritative."""
    if world_id.kind != "world":
        raise ValueError("world_id must identify a world")

    rng = random_for(seed, 0, "world.geography.v1")
    regions = tuple(
        RegionState(
            id=entity_id(world_id, "region", f"seeded:{index}"),
            key=f"seeded:{index}",
            terrain=_choice(rng, TERRAINS),
            biome=_choice(rng, BIOMES),
            habitability=_unit_value(rng),
            water_access=_unit_value(rng),
            climate_pressure=_unit_value(rng),
            resources=tuple(
                ResourcePotential(resource=resource, potential=_unit_value(rng))
                for resource in RESOURCE_KINDS
            ),
        )
        for index in range(REGION_COUNT)
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
