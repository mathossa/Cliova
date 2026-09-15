"""Projection-only strategic map boundary for issue #24.

The simulation remains authoritative. This module converts persisted aggregate geography,
presence, settlement and status state into browser-facing game coordinates without exposing
WorldEngine objects or asking the browser to reproduce simulation formulas.
"""

from typing import cast

from cliova.api.v1.models import (
    EntityKindDto,
    EntityRef,
    MapMultiPolygon,
    MapRegionFeature,
    SettlementMapMarker,
    TemporaryPresence,
    WorldMapResponse,
)
from cliova.simulation.types import EntityId, RasterRun, RegionPresentationGeometry, WorldState

MAP_RENDER_VERSION = "strategic-svg-v1"
MAP_COORDINATE_SYSTEM = "cliova-grid-bottom-left-v1"


def _run_ring(run: RasterRun, *, height: int) -> tuple[tuple[float, float], ...]:
    """Convert #59's top-left raster row into Leaflet-friendly bottom-left game coordinates."""
    bottom = float(height - run.y - 1)
    top = bottom + 1.0
    left = float(run.x_start)
    right = float(run.x_stop)
    return (
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
        (left, bottom),
    )


def _region_geometry(geometry: RegionPresentationGeometry, *, height: int) -> MapMultiPolygon:
    return MapMultiPolygon(
        coordinates=tuple(((_run_ring(run, height=height)),) for run in geometry.runs)
    )


def _centroid(geometry: RegionPresentationGeometry, *, height: int) -> tuple[float, float]:
    return (
        round(geometry.centroid_x + 0.5, 6),
        round(height - geometry.centroid_y - 0.5, 6),
    )


def _population(world: WorldState, region_id: EntityId) -> int | None:
    if world.population is None:
        return None
    for state in world.population.regions:
        if state.region_id == region_id:
            return state.total
    return None


def _food_shortage(world: WorldState, region_id: EntityId) -> float | None:
    if world.economy is None:
        return None
    for state in world.economy.regions:
        if state.region_id != region_id:
            continue
        try:
            return state.resource("food").shortage_severity
        except KeyError:
            return None
    return None


def world_map_projection(world: WorldState) -> WorldMapResponse:
    """Return a deterministic strategic-map projection or an explicit no-map state."""
    geography = world.geography
    presentation = geography.presentation if geography is not None else None
    if geography is None or presentation is None:
        return WorldMapResponse(
            world_id=world.id.value,
            tick=world.time.tick,
            available=False,
            unavailable_reason="presentation_geometry_unavailable",
            render_version=MAP_RENDER_VERSION,
        )

    presentation_by_region = {geometry.region_id: geometry for geometry in presentation.regions}
    active_pressure_by_region: dict[EntityId, float] = {}
    for pressure in world.pressures:
        if pressure.milestone == "resolved":
            continue
        active_pressure_by_region[pressure.region_id] = max(
            pressure.intensity,
            active_pressure_by_region.get(pressure.region_id, 0.0),
        )

    core_by_region: dict[EntityId, list[EntityId]] = {}
    temporary_by_region: dict[EntityId, list[TemporaryPresence]] = {}
    for relationship in world.society_regions:
        core_by_region.setdefault(relationship.core_region_id, []).append(relationship.society_id)
        for access in relationship.temporary_access:
            temporary_by_region.setdefault(access.region_id, []).append(
                TemporaryPresence(
                    society_id=relationship.society_id.value,
                    production_method=access.production_method,
                    access_share=access.access_share,
                )
            )

    regions: list[MapRegionFeature] = []
    for region in geography.regions:
        geometry = presentation_by_region[region.id]
        regions.append(
            MapRegionFeature(
                id=region.id.value,
                key=region.key,
                centroid=_centroid(geometry, height=presentation.height),
                geometry=_region_geometry(geometry, height=presentation.height),
                terrain=region.terrain,
                biome=region.biome,
                surface=region.surface,
                land_fraction=region.land_fraction,
                mean_elevation=region.mean_elevation,
                population=_population(world, region.id),
                food_shortage_severity=_food_shortage(world, region.id),
                pressure_intensity=active_pressure_by_region.get(region.id),
                core_society_ids=tuple(
                    society.value
                    for society in sorted(
                        core_by_region.get(region.id, []), key=lambda item: item.value.hex
                    )
                ),
                temporary_presence=tuple(
                    sorted(
                        temporary_by_region.get(region.id, []),
                        key=lambda item: (item.society_id.hex, item.production_method),
                    )
                ),
            )
        )

    structure_counts: dict[EntityId, int] = {}
    for structure in world.settlements.structures:
        settlement_id = structure.settlement_id
        structure_counts[settlement_id] = structure_counts.get(settlement_id, 0) + 1

    settlements: list[SettlementMapMarker] = []
    for settlement in sorted(world.settlements.settlements, key=lambda item: item.id.value.hex):
        settlement_geometry = presentation_by_region.get(settlement.region_id)
        if settlement_geometry is None:
            continue
        associated = None
        if settlement.associated_subject is not None:
            associated = EntityRef(
                kind=cast(EntityKindDto, settlement.associated_subject.kind),
                id=settlement.associated_subject.value,
            )
        settlements.append(
            SettlementMapMarker(
                id=settlement.id.value,
                region_id=settlement.region_id.value,
                name=settlement.name,
                archetype=settlement.archetype,
                status=settlement.status,
                population_estimate=settlement.population_estimate,
                associated_subject=associated,
                position=_centroid(settlement_geometry, height=presentation.height),
                structure_count=structure_counts.get(settlement.id, 0),
                local_map_path=f"/settlements/{settlement.id.value}",
            )
        )

    return WorldMapResponse(
        world_id=world.id.value,
        tick=world.time.tick,
        available=True,
        render_version=MAP_RENDER_VERSION,
        extent_width=presentation.width,
        extent_height=presentation.height,
        base_map_url=(f"/api/v1/worlds/{world.id.value}/map/base.svg?v={MAP_RENDER_VERSION}"),
        regions=tuple(regions),
        settlements=tuple(settlements),
    )
