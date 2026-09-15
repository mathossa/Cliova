from uuid import UUID

from cliova.api.v1.map_projection import _region_geometry, world_map_projection
from cliova.api.v1.map_rendering import render_physical_base_svg
from cliova.application.development import create_development_world
from cliova.simulation.types import EntityId, RasterRun, RegionPresentationGeometry


def test_region_projection_dissolves_adjacent_raster_runs() -> None:
    geometry = RegionPresentationGeometry(
        region_id=EntityId(kind="region", value=UUID(int=1)),
        centroid_x=1.0,
        centroid_y=0.5,
        runs=(
            RasterRun(y=0, x_start=0, x_stop=3),
            RasterRun(y=1, x_start=0, x_stop=3),
        ),
    )

    projected = _region_geometry(geometry, height=2)

    assert len(projected.coordinates) == 1
    assert len(projected.coordinates[0]) == 1
    assert len(projected.coordinates[0][0]) == 5


def test_generated_development_world_populates_only_society_core_region() -> None:
    world = create_development_world(
        seed=2402,
        world_key="map-habitation",
        generated_geography=True,
    )

    assert world.geography is not None
    assert world.population is not None
    assert len(world.society_regions) == 1
    assert len(world.population.regions) == 1

    relationship = world.society_regions[0]
    population = world.population.regions[0]
    core_region = next(
        region for region in world.geography.regions if region.id == relationship.core_region_id
    )

    assert population.region_id == relationship.core_region_id
    assert core_region.surface != "ocean"

    projection = world_map_projection(world)
    populated_features = [region for region in projection.regions if region.population is not None]
    assert len(populated_features) == 1
    assert populated_features[0].id == relationship.core_region_id.value
    assert all(
        region.population is None
        for region in projection.regions
        if region.id != relationship.core_region_id.value
    )


def test_generated_world_uses_stylized_worldengine_terrain_base() -> None:
    world = create_development_world(
        seed=2403,
        world_key="map-terrain",
        generated_geography=True,
    )

    svg = render_physical_base_svg(world)

    assert 'data-render-theme="stylized-strategic-terrain"' in svg
    assert "data:image/png;base64," in svg
    assert "terrain-grade" in svg
    assert "terrain-texture" in svg
