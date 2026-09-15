from cliova.api.v1.map_projection import MAP_RENDER_VERSION, world_map_projection
from cliova.api.v1.map_rendering import render_physical_base_svg, svg_etag
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.domains.world.generation import generate_geography
from cliova.simulation.domains.world.worldengine_adapter import WorldEngineConfig
from cliova.simulation.types import (
    SeasonalSubsistenceAccessState,
    SettlementDomainState,
    SettlementState,
    SocietyRegionRelationshipState,
    StructureState,
    WorldState,
    entity_id,
)


def _world_with_presence_and_settlements() -> WorldState:
    world = WorldState.create(seed=2401, world_key="strategic-map")
    assert world.geography is not None
    core = world.geography.regions[0]
    temporary = world.geography.regions[1]
    society_id = entity_id(world.id, "society", "map-society")
    permanent_id = entity_id(world.id, "settlement", "river-haven")
    camp_id = entity_id(world.id, "settlement", "seasonal-camp")
    storage_id = entity_id(world.id, "structure", "river-haven:storage")
    settlements = SettlementDomainState(
        settlements=(
            SettlementState(
                id=permanent_id,
                key="river-haven",
                name="River Haven",
                region_id=core.id,
                associated_subject=society_id,
                established_year=0,
                population_estimate=640,
                archetype="permanent",
            ),
            SettlementState(
                id=camp_id,
                key="seasonal-camp",
                name="Seasonal Camp",
                region_id=temporary.id,
                associated_subject=society_id,
                established_year=0,
                population_estimate=90,
                archetype="seasonal_camp",
                status="dormant",
            ),
        ),
        structures=(
            StructureState(
                id=storage_id,
                key="river-haven:storage",
                definition_id="storage",
                settlement_id=permanent_id,
                established_year=0,
            ),
        ),
    )
    relationship = SocietyRegionRelationshipState(
        society_id=society_id,
        core_region_id=core.id,
        temporary_access=(
            SeasonalSubsistenceAccessState(
                region_id=temporary.id,
                production_method="pastoralism",
                access_share=0.5,
            ),
        ),
    )
    return world.model_copy(
        update={
            "society_regions": (relationship,),
            "settlements": settlements,
        }
    )


def test_map_projection_is_deterministic_and_represents_every_generated_region() -> None:
    world = _world_with_presence_and_settlements()

    first = world_map_projection(world)
    second = world_map_projection(world)

    assert first == second
    assert first.available
    assert first.render_version == MAP_RENDER_VERSION
    assert first.coordinate_system == "cliova-grid-bottom-left-v1"
    assert world.geography is not None
    assert {region.id for region in first.regions} == {
        region.id.value for region in world.geography.regions
    }
    assert all(feature.geometry.type == "MultiPolygon" for feature in first.regions)
    assert all(feature.geometry.coordinates for feature in first.regions)
    serialized = first.model_dump_json()
    assert "PhysicalWorld" not in serialized
    assert "worldengine_seed" not in serialized
    assert "RasterRun" not in serialized


def test_core_temporary_presence_and_authoritative_settlements_remain_distinct() -> None:
    world = _world_with_presence_and_settlements()
    projection = world_map_projection(world)
    relationship = world.society_regions[0]

    core = next(region for region in projection.regions if region.id == relationship.core_region_id.value)
    temporary = next(
        region
        for region in projection.regions
        if region.id == relationship.temporary_access[0].region_id.value
    )

    assert core.core_society_ids == (relationship.society_id.value,)
    assert core.temporary_presence == ()
    assert temporary.core_society_ids == ()
    assert temporary.temporary_presence[0].society_id == relationship.society_id.value
    assert temporary.temporary_presence[0].production_method == "pastoralism"

    authoritative_ids = {settlement.id.value for settlement in world.settlements.settlements}
    assert {marker.id for marker in projection.settlements} == authoritative_ids
    assert {marker.archetype for marker in projection.settlements} == {"permanent", "seasonal_camp"}
    permanent = next(marker for marker in projection.settlements if marker.archetype == "permanent")
    assert permanent.structure_count == 1
    assert permanent.position_precision == "region_centroid"
    assert permanent.local_map_path.endswith(str(permanent.id))


def test_base_render_is_disposable_deterministic_and_does_not_mutate_world() -> None:
    world = _world_with_presence_and_settlements()
    before = world.model_dump_json()

    first = render_physical_base_svg(world)
    second = render_physical_base_svg(world)

    assert first == second
    assert svg_etag(first) == svg_etag(second)
    assert f'data-render-version="{MAP_RENDER_VERSION}"' in first
    assert "worldengine" in first
    assert world.model_dump_json() == before
    assert "settlement" not in first.lower()
    assert "society" not in first.lower()


def test_legacy_world_without_presentation_returns_explicit_unavailable_projection() -> None:
    world = create_starter_world(seed=7, world_key="legacy-map")
    projection = world_map_projection(world)

    assert not projection.available
    assert projection.unavailable_reason == "presentation_geometry_unavailable"
    assert projection.regions == ()
    assert projection.settlements == ()


def test_projection_supports_world_substantially_larger_than_old_six_region_fixture() -> None:
    world = WorldState.create(seed=99, world_key="large-map")
    geography = generate_geography(
        world_id=world.id,
        seed=world.seed,
        config=WorldEngineConfig(width=40, height=24, region_count=18, num_plates=12),
    )
    world = world.model_copy(update={"geography": geography})

    projection = world_map_projection(world)

    assert projection.available
    assert len(projection.regions) == 18
    assert projection.extent_width == 40
    assert projection.extent_height == 24
