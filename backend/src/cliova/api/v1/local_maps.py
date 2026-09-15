"""Projection-only local-map boundary for issue #61.

Cliova decides what exists. This module only prepares stable inputs for a
presentation generator; it never creates structures or affects a simulation tick.
"""

import hashlib
import json
from uuid import UUID

from cliova.api.v1.local_map_models import (
    LocalMapPhysicalContext,
    LocalMapRequest,
    SettlementDetailResponse,
    SettlementSummary,
    StructureProjection,
)
from cliova.api.v1.projections import entity_ref
from cliova.simulation.domains.settlements.catalog import structure_definition
from cliova.simulation.types import EntityId, SettlementState, StructureState, WorldState

LOCAL_MAP_GENERATION_VERSION = "local-map-v1"
LOCAL_MAP_RENDER_VERSION = "local-map-render-v1"
SETTLEMAKER_VERSION = "3.0.1"
CAMP_RENDERER_VERSION = "cliova-camp-v1"


def settlement_summary(settlement: SettlementState) -> SettlementSummary:
    return SettlementSummary(
        id=settlement.id.value,
        key=settlement.key,
        name=settlement.name,
        region_id=settlement.region_id.value,
        associated_subject=(
            entity_ref(settlement.associated_subject)
            if settlement.associated_subject is not None
            else None
        ),
        established_year=settlement.established_year,
        population_estimate=settlement.population_estimate,
        archetype=settlement.archetype,
        status=settlement.status,
    )


def structure_projection(structure: StructureState) -> StructureProjection:
    definition = structure_definition(structure.definition_id)
    return StructureProjection(
        id=structure.id.value,
        key=structure.key,
        definition_id=structure.definition_id,
        display_name=definition.display_name,
        established_year=structure.established_year,
        status=structure.status,
    )


def settlement_detail(world: WorldState, settlement_id: UUID) -> SettlementDetailResponse:
    settlement = _settlement(world, settlement_id)
    structures = tuple(
        structure_projection(structure)
        for structure in sorted(
            world.settlements.structures_for(settlement.id),
            key=lambda item: (item.established_year, item.id.value.hex),
        )
    )
    return SettlementDetailResponse(
        world_id=world.id.value,
        tick=world.time.tick,
        settlement=settlement_summary(settlement),
        structures=structures,
    )


def local_map_request(world: WorldState, settlement_id: UUID) -> LocalMapRequest:
    """Return the reproducible renderer input for one authoritative settlement."""

    settlement = _settlement(world, settlement_id)
    if world.geography is None:
        raise ValueError("settlement local map requires world geography")
    region = next(
        (
            candidate
            for candidate in world.geography.regions
            if candidate.id == settlement.region_id
        ),
        None,
    )
    if region is None:
        raise ValueError("settlement region is missing from world geography")

    presentation_region = None
    presentation = world.geography.presentation
    if presentation is not None:
        presentation_region = next(
            (candidate for candidate in presentation.regions if candidate.region_id == region.id),
            None,
        )

    physical_context = LocalMapPhysicalContext(
        terrain=region.terrain,
        biome=region.biome,
        surface=region.surface,
        water_access=region.water_access,
        coast_fraction=region.coast_fraction,
        mean_elevation=region.mean_elevation,
        region_centroid_x=(
            presentation_region.centroid_x if presentation_region is not None else None
        ),
        region_centroid_y=(
            presentation_region.centroid_y if presentation_region is not None else None
        ),
        world_extent_width=(presentation.width if presentation is not None else None),
        world_extent_height=(presentation.height if presentation is not None else None),
    )
    detail = settlement_detail(world, settlement_id)
    renderer = "settlemaker" if settlement.archetype == "permanent" else "cliova_camp"
    renderer_version = SETTLEMAKER_VERSION if renderer == "settlemaker" else CAMP_RENDERER_VERSION
    return LocalMapRequest(
        world_id=world.id.value,
        settlement_id=settlement.id.value,
        layout_seed=_layout_seed(world, settlement),
        generation_version=LOCAL_MAP_GENERATION_VERSION,
        render_version=LOCAL_MAP_RENDER_VERSION,
        renderer=renderer,
        renderer_version=renderer_version,
        state_fingerprint=_state_fingerprint(detail, physical_context),
        settlement=detail.settlement,
        physical_context=physical_context,
        authoritative_structures=detail.structures,
    )


def _layout_seed(world: WorldState, settlement: SettlementState) -> int:
    payload = json.dumps(
        [world.seed, settlement.id.value.hex, LOCAL_MAP_GENERATION_VERSION],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    # Settlemaker's seeded LCG has a fixed point at zero. Keep the adapter in
    # the positive signed-31-bit range without consuming simulation RNG.
    return int.from_bytes(digest[:8], "big") % 2_147_483_646 + 1


def _state_fingerprint(
    detail: SettlementDetailResponse,
    context: LocalMapPhysicalContext,
) -> str:
    payload = {
        "settlement": detail.settlement.model_dump(mode="json"),
        "structures": [item.model_dump(mode="json") for item in detail.structures],
        "physical_context": context.model_dump(mode="json"),
        "generation_version": LOCAL_MAP_GENERATION_VERSION,
        "render_version": LOCAL_MAP_RENDER_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _settlement(world: WorldState, settlement_id: UUID) -> SettlementState:
    target = EntityId(kind="settlement", value=settlement_id)
    try:
        return world.settlements.settlement(target)
    except KeyError as exc:
        raise KeyError(settlement_id) from exc
