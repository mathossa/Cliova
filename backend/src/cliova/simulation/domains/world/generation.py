"""Deterministic WorldEngine-backed generation of authoritative physical geography."""

from __future__ import annotations

from collections import Counter
from math import ceil, sqrt

import networkx as nx  # type: ignore[import-untyped]
import numpy as np
from numpy.typing import NDArray

from cliova.simulation.domains.world.worldengine_adapter import (
    ADAPTER_VERSION,
    DEFAULT_WORLDENGINE_CONFIG,
    WORLDENGINE_PACKAGE_VERSION,
    WORLDENGINE_REVISION,
    PhysicalWorld,
    WorldEngineConfig,
    generate_physical_world,
)
from cliova.simulation.types import (
    BiomeKind,
    EntityId,
    GenerationParameter,
    GeographyPresentationState,
    GeographyState,
    PhysicalGenerationMetadata,
    RasterRun,
    RegionConnection,
    RegionPresentationGeometry,
    RegionState,
    ResourcePotential,
    SurfaceKind,
    TerrainKind,
    entity_id,
)

PARTITION_VERSION = "networkx-grid-voronoi-v1"
RESOURCE_KINDS: tuple[str, ...] = (
    "arable_land",
    "grazing",
    "wild_food",
    "aquatic_food",
    "metal_ores",
    "stone",
    "timber",
)

# Kept as a small physical-opportunity helper for deterministic hand-authored fixtures.
# WorldEngine-backed geography derives the same opportunity keys from generated layers below.
_GRAZING_TERRAIN_BONUS: dict[TerrainKind, float] = {
    "plain": 0.05,
    "plateau": 0.08,
    "basin": 0.10,
    "highland": 0.12,
    "forest": -0.08,
    "wetland": -0.05,
    "coast": 0.0,
}
_WILD_FOOD_TERRAIN_BONUS: dict[TerrainKind, float] = {
    "plain": 0.0,
    "plateau": 0.0,
    "basin": 0.0,
    "highland": 0.0,
    "forest": 0.10,
    "wetland": 0.08,
    "coast": 0.0,
}
_AQUATIC_TERRAIN_FACTOR: dict[TerrainKind, float] = {
    "plain": 0.35,
    "plateau": 0.30,
    "basin": 0.75,
    "highland": 0.35,
    "forest": 0.55,
    "wetland": 0.90,
    "coast": 1.00,
}


def _unit(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 6)


def derive_food_opportunities(
    *,
    terrain: TerrainKind,
    habitability: float,
    water_access: float,
    climate_pressure: float,
    arable_land: float,
    timber: float,
) -> tuple[ResourcePotential, ...]:
    """Derive fixture physical opportunities without performing economy production."""
    grazing = _unit(
        0.40 * (1.0 - arable_land)
        + 0.35 * habitability
        + 0.25 * (1.0 - climate_pressure)
        + _GRAZING_TERRAIN_BONUS[terrain]
    )
    wild_food = _unit(
        0.50 * timber
        + 0.25 * water_access
        + 0.25 * habitability
        + _WILD_FOOD_TERRAIN_BONUS[terrain]
    )
    aquatic_food = _unit(water_access * _AQUATIC_TERRAIN_FACTOR[terrain])
    return (
        ResourcePotential(resource="grazing", potential=grazing),
        ResourcePotential(resource="wild_food", potential=wild_food),
        ResourcePotential(resource="aquatic_food", potential=aquatic_food),
    )


def _normalize(layer: NDArray[np.float64]) -> NDArray[np.float64]:
    minimum = float(np.nanmin(layer))
    maximum = float(np.nanmax(layer))
    if not np.isfinite(minimum) or not np.isfinite(maximum):
        raise ValueError("WorldEngine produced a non-finite physical layer")
    if maximum <= minimum:
        return np.zeros_like(layer, dtype=np.float64)
    return np.asarray((layer - minimum) / (maximum - minimum), dtype=np.float64)


def _edge_mask(values: NDArray[np.generic]) -> NDArray[np.bool_]:
    mask = np.zeros(values.shape, dtype=np.bool_)
    horizontal = values[:, 1:] != values[:, :-1]
    vertical = values[1:, :] != values[:-1, :]
    mask[:, 1:] |= horizontal
    mask[:, :-1] |= horizontal
    mask[1:, :] |= vertical
    mask[:-1, :] |= vertical
    return mask


def _coast_mask(ocean: NDArray[np.bool_]) -> NDArray[np.bool_]:
    return _edge_mask(ocean)


def _grid_centers(*, width: int, height: int, count: int) -> tuple[tuple[int, int], ...]:
    """Choose deterministic, evenly distributed markers for graph Voronoi partitioning."""
    columns = max(1, ceil(sqrt(count * (width / height))))
    rows = max(1, ceil(count / columns))
    slots: list[tuple[int, int]] = []
    for row in range(rows):
        y = min(height - 1, max(0, round(((row + 0.5) * height / rows) - 0.5)))
        for column in range(columns):
            x = min(width - 1, max(0, round(((column + 0.5) * width / columns) - 0.5)))
            slots.append((y, x))
    if len(slots) == count:
        return tuple(sorted(slots))

    indices = np.linspace(0, len(slots) - 1, num=count)
    chosen = {slots[int(round(index))] for index in indices}
    if len(chosen) != count:
        for slot in slots:
            chosen.add(slot)
            if len(chosen) == count:
                break
    return tuple(sorted(chosen))


def _partition(
    physical: PhysicalWorld,
    *,
    region_count: int,
    elevation: NDArray[np.float64],
    temperature: NDArray[np.float64],
) -> NDArray[np.int64]:
    """Partition the physical grid using NetworkX's mature graph-Voronoi implementation."""
    graph = nx.grid_2d_graph(physical.height, physical.width)
    for a, b in graph.edges:
        ay, ax = a
        by, bx = b
        surface_change = 1.75 if physical.ocean[ay, ax] != physical.ocean[by, bx] else 0.0
        physical_change = 0.60 * abs(
            float(elevation[ay, ax]) - float(elevation[by, bx])
        ) + 0.20 * abs(float(temperature[ay, ax]) - float(temperature[by, bx]))
        graph.edges[a, b]["weight"] = 1.0 + surface_change + physical_change

    centers = _grid_centers(width=physical.width, height=physical.height, count=region_count)
    cells = nx.voronoi_cells(graph, centers, weight="weight")
    if "unreachable" in cells:
        raise RuntimeError("physical grid partition unexpectedly contains unreachable cells")

    labels = np.full((physical.height, physical.width), -1, dtype=np.int64)
    for index, center in enumerate(centers):
        for y, x in cells[center]:
            labels[y, x] = index
    if np.any(labels < 0):
        raise RuntimeError("physical region partition left cells unassigned")
    return labels


def _broad_biome(
    name: str, *, elevation: float, temperature: float, precipitation: float
) -> BiomeKind:
    normalized = name.lower()
    if elevation >= 0.72 and temperature <= 0.48:
        return "alpine"
    if any(token in normalized for token in ("polar", "ice", "subpolar", "boreal")):
        return "boreal"
    if "desert" in normalized and precipitation < 0.45:
        return "arid"
    if (
        any(token in normalized for token in ("steppe", "scrub", "thorn", "dry"))
        and precipitation < 0.58
    ):
        return "semi_arid"
    if any(token in normalized for token in ("tropical", "subtropical")):
        return "tropical"
    return "temperate"


def _dominant_biome(
    physical: PhysicalWorld,
    cells: tuple[tuple[int, int], ...],
    *,
    elevation: NDArray[np.float64],
    temperature: NDArray[np.float64],
    precipitation: NDArray[np.float64],
) -> BiomeKind:
    categories: list[BiomeKind] = []
    for y, x in cells:
        if physical.ocean[y, x]:
            continue
        categories.append(
            _broad_biome(
                str(physical.biome[y, x]),
                elevation=float(elevation[y, x]),
                temperature=float(temperature[y, x]),
                precipitation=float(precipitation[y, x]),
            )
        )
    if not categories:
        mean_temperature = float(np.mean([temperature[y, x] for y, x in cells]))
        return "boreal" if mean_temperature < 0.30 else "temperate"

    counts = Counter(categories)
    order: tuple[BiomeKind, ...] = (
        "temperate",
        "semi_arid",
        "arid",
        "boreal",
        "tropical",
        "alpine",
    )
    return max(order, key=lambda candidate: (counts[candidate], -order.index(candidate)))


def _forest_fraction(physical: PhysicalWorld, cells: tuple[tuple[int, int], ...]) -> float:
    land_names = [str(physical.biome[y, x]).lower() for y, x in cells if not physical.ocean[y, x]]
    if not land_names:
        return 0.0
    return sum("forest" in name or "rain forest" in name for name in land_names) / len(land_names)


def _surface_kind(land_fraction: float) -> SurfaceKind:
    if land_fraction <= 0.20:
        return "ocean"
    if land_fraction >= 0.80:
        return "land"
    return "mixed"


def _terrain(
    *,
    surface: SurfaceKind,
    coast_fraction: float,
    forest_fraction: float,
    elevation: float,
    topographic_constraint: float,
    precipitation: float,
    hydrology: float,
) -> TerrainKind:
    if surface == "ocean" or coast_fraction >= 0.28:
        return "coast"
    if forest_fraction >= 0.50:
        return "forest"
    if topographic_constraint >= 0.62 or elevation >= 0.76:
        return "highland"
    if topographic_constraint >= 0.38 or elevation >= 0.60:
        return "plateau"
    if precipitation >= 0.72 and hydrology >= 0.50:
        return "wetland"
    return "plain"


def _runs(mask: NDArray[np.bool_]) -> tuple[RasterRun, ...]:
    runs: list[RasterRun] = []
    height, width = mask.shape
    for y in range(height):
        x = 0
        while x < width:
            if not bool(mask[y, x]):
                x += 1
                continue
            start = x
            while x < width and bool(mask[y, x]):
                x += 1
            runs.append(RasterRun(y=y, x_start=start, x_stop=x))
    return tuple(runs)


def _presentation(
    *,
    physical: PhysicalWorld,
    labels: NDArray[np.int64],
    regions: tuple[RegionState, ...],
) -> GeographyPresentationState:
    geometries: list[RegionPresentationGeometry] = []
    for index, region in enumerate(regions):
        mask = labels == index
        ys, xs = np.nonzero(mask)
        geometries.append(
            RegionPresentationGeometry(
                region_id=region.id,
                centroid_x=round(float(np.mean(xs)), 6),
                centroid_y=round(float(np.mean(ys)), 6),
                runs=_runs(mask),
            )
        )
    return GeographyPresentationState(
        width=physical.width,
        height=physical.height,
        land_runs=_runs(np.logical_not(physical.ocean)),
        regions=tuple(geometries),
    )


def _region_cells(labels: NDArray[np.int64], index: int) -> tuple[tuple[int, int], ...]:
    return tuple((int(y), int(x)) for y, x in np.argwhere(labels == index))


def _mean(layer: NDArray[np.float64], cells: tuple[tuple[int, int], ...]) -> float:
    return float(np.mean([layer[y, x] for y, x in cells]))


def _derive_region(
    *,
    world_id: EntityId,
    index: int,
    physical: PhysicalWorld,
    cells: tuple[tuple[int, int], ...],
    elevation: NDArray[np.float64],
    temperature: NDArray[np.float64],
    precipitation: NDArray[np.float64],
    humidity: NDArray[np.float64],
    hydrology: NDArray[np.float64],
    topography: NDArray[np.float64],
    coast: NDArray[np.bool_],
    plate_boundaries: NDArray[np.bool_],
) -> RegionState:
    count = len(cells)
    land_fraction = sum(not bool(physical.ocean[y, x]) for y, x in cells) / count
    coast_fraction = sum(bool(coast[y, x]) for y, x in cells) / count
    mean_elevation = _mean(elevation, cells)
    mean_temperature = _mean(temperature, cells)
    mean_precipitation = _mean(precipitation, cells)
    mean_humidity = _mean(humidity, cells)
    mean_hydrology = _mean(hydrology, cells)
    mean_topography = _mean(topography, cells)
    plate_boundary_fraction = sum(bool(plate_boundaries[y, x]) for y, x in cells) / count
    forest_fraction = _forest_fraction(physical, cells)
    surface = _surface_kind(land_fraction)
    biome = _dominant_biome(
        physical,
        cells,
        elevation=elevation,
        temperature=temperature,
        precipitation=precipitation,
    )
    terrain = _terrain(
        surface=surface,
        coast_fraction=coast_fraction,
        forest_fraction=forest_fraction,
        elevation=mean_elevation,
        topographic_constraint=mean_topography,
        precipitation=mean_precipitation,
        hydrology=mean_hydrology,
    )

    water_fraction = 1.0 - land_fraction
    water_access = _unit(
        0.68 * water_fraction
        + 0.15 * coast_fraction
        + 0.10 * mean_hydrology
        + 0.07 * mean_precipitation
    )
    temperature_extreme = abs(mean_temperature - 0.50) * 2.0
    dryness = 1.0 - ((mean_precipitation + mean_humidity) / 2.0)
    climate_pressure = _unit(0.45 * temperature_extreme + 0.35 * dryness + 0.20 * mean_topography)
    habitability = _unit(
        land_fraction
        * (1.0 - (0.45 * climate_pressure))
        * (0.55 + (0.45 * water_access))
        * (1.0 - (0.35 * mean_topography))
    )
    climate_suitability = 1.0 - climate_pressure
    moisture = (mean_precipitation + mean_humidity) / 2.0
    arable_land = _unit(
        land_fraction
        * climate_suitability
        * (0.35 + (0.65 * moisture))
        * (1.0 - (0.70 * mean_topography))
        * (1.0 - (0.35 * forest_fraction))
    )
    grazing = _unit(
        land_fraction
        * climate_suitability
        * (1.0 - (0.55 * forest_fraction))
        * (1.0 - (0.45 * mean_topography))
    )
    wild_food = _unit(
        land_fraction * (0.55 * forest_fraction + 0.20 * moisture + 0.25 * habitability)
    )
    aquatic_food = _unit(0.75 * water_fraction + 0.45 * coast_fraction + 0.25 * mean_hydrology)
    timber = _unit(land_fraction * forest_fraction * (0.60 + (0.40 * mean_precipitation)))
    stone = _unit(land_fraction * (0.25 + (0.45 * mean_topography) + (0.30 * mean_elevation)))
    metal_ores = _unit(
        land_fraction * (0.20 + (0.45 * plate_boundary_fraction) + (0.35 * mean_topography))
    )

    resources = tuple(
        ResourcePotential(resource=resource, potential=potential)
        for resource, potential in (
            ("arable_land", arable_land),
            ("grazing", grazing),
            ("wild_food", wild_food),
            ("aquatic_food", aquatic_food),
            ("metal_ores", metal_ores),
            ("stone", stone),
            ("timber", timber),
        )
    )
    return RegionState(
        id=entity_id(world_id, "region", f"worldengine-v1:{index}"),
        key=f"worldengine-v1:{index}",
        terrain=terrain,
        biome=biome,
        habitability=habitability,
        water_access=water_access,
        climate_pressure=climate_pressure,
        resources=resources,
        surface=surface,
        land_fraction=_unit(land_fraction),
        coast_fraction=_unit(coast_fraction),
        mean_elevation=_unit(mean_elevation),
        mean_temperature=_unit(mean_temperature),
        mean_precipitation=_unit(mean_precipitation),
        topographic_constraint=_unit(mean_topography),
    )


def _connections(
    *, labels: NDArray[np.int64], regions: tuple[RegionState, ...]
) -> tuple[RegionConnection, ...]:
    pairs: set[tuple[int, int]] = set()
    height, width = labels.shape
    for y in range(height):
        for x in range(width):
            current = int(labels[y, x])
            if x + 1 < width:
                neighbour = int(labels[y, x + 1])
                if current != neighbour:
                    pairs.add((min(current, neighbour), max(current, neighbour)))
            if y + 1 < height:
                neighbour = int(labels[y + 1, x])
                if current != neighbour:
                    pairs.add((min(current, neighbour), max(current, neighbour)))

    connections: list[RegionConnection] = []
    for a, b in sorted(pairs):
        left = regions[a]
        right = regions[b]
        surface_penalty = 0.0
        if left.surface != right.surface:
            surface_penalty = 0.80 if "ocean" in {left.surface, right.surface} else 0.35
        elif left.surface == "ocean":
            surface_penalty = 0.25
        travel_cost = round(
            1.0
            + surface_penalty
            + 0.65 * ((left.topographic_constraint + right.topographic_constraint) / 2.0)
            + 0.25 * abs(left.mean_elevation - right.mean_elevation),
            6,
        )
        connections.append(
            RegionConnection(a=left.id, b=right.id, travel_cost=max(0.001, travel_cost))
        )
    return tuple(connections)


def _generation_metadata(
    *, seed: int, physical: PhysicalWorld, config: WorldEngineConfig
) -> PhysicalGenerationMetadata:
    return PhysicalGenerationMetadata(
        generator="worldengine",
        adapter_version=ADAPTER_VERSION,
        upstream_version=WORLDENGINE_PACKAGE_VERSION,
        upstream_revision=WORLDENGINE_REVISION,
        partition_version=PARTITION_VERSION,
        world_seed=seed,
        worldengine_seed=physical.worldengine_seed,
        schema_version=1,
        simulation_version=1,
        parameters=(
            GenerationParameter(key="width", value=config.width),
            GenerationParameter(key="height", value=config.height),
            GenerationParameter(key="region_count", value=config.region_count),
            GenerationParameter(key="num_plates", value=config.num_plates),
            GenerationParameter(key="ocean_level", value=config.ocean_level),
            GenerationParameter(key="gamma_curve", value=config.gamma_curve),
            GenerationParameter(key="curve_offset", value=config.curve_offset),
            GenerationParameter(key="fade_borders", value=config.fade_borders),
        ),
    )


def generate_geography(
    *,
    world_id: EntityId,
    seed: int,
    config: WorldEngineConfig = DEFAULT_WORLDENGINE_CONFIG,
) -> GeographyState:
    """Generate physical geography once, then persist only Cliova-owned aggregate state."""
    if world_id.kind != "world":
        raise ValueError("world_id must identify a world")

    physical = generate_physical_world(seed=seed, config=config)
    elevation = _normalize(physical.elevation)
    temperature = _normalize(physical.temperature)
    precipitation = _normalize(physical.precipitation)
    humidity = _normalize(physical.humidity)
    hydrology = _normalize(physical.watermap)
    gradient_y, gradient_x = np.gradient(elevation)
    topography = _normalize(np.sqrt((gradient_x**2) + (gradient_y**2)))
    coast = _coast_mask(physical.ocean)
    plate_boundaries = _edge_mask(physical.plates)
    labels = _partition(
        physical,
        region_count=config.region_count,
        elevation=elevation,
        temperature=temperature,
    )

    regions = tuple(
        _derive_region(
            world_id=world_id,
            index=index,
            physical=physical,
            cells=_region_cells(labels, index),
            elevation=elevation,
            temperature=temperature,
            precipitation=precipitation,
            humidity=humidity,
            hydrology=hydrology,
            topography=topography,
            coast=coast,
            plate_boundaries=plate_boundaries,
        )
        for index in range(config.region_count)
    )
    connections = _connections(labels=labels, regions=regions)
    geography = GeographyState(
        regions=regions,
        connections=connections,
        generation=_generation_metadata(seed=seed, physical=physical, config=config),
        presentation=_presentation(physical=physical, labels=labels, regions=regions),
    )

    graph = nx.Graph()
    graph.add_nodes_from(region.id for region in regions)
    graph.add_edges_from((connection.a, connection.b) for connection in connections)
    if not nx.is_connected(graph):
        raise RuntimeError("generated aggregate geography must be connected")
    return geography
