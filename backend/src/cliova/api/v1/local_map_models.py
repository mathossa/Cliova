"""Stable HTTP v1 DTOs for derived local settlement-map presentation.

These models project authoritative settlement/geography state for a renderer. They
are not simulation state and deliberately contain no Settlemaker/WorldEngine
objects.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from cliova.api.v1.models import ApiModel, EntityRef

SettlementArchetypeDto = Literal["permanent", "seasonal_camp", "temporary_camp"]
SettlementStatusDto = Literal["active", "dormant", "abandoned", "destroyed"]
StructureStatusDto = Literal["active", "damaged", "destroyed"]
LocalMapRendererDto = Literal["settlemaker", "cliova_camp"]


class SettlementSummary(ApiModel):
    id: UUID
    key: str
    name: str
    region_id: UUID
    associated_subject: EntityRef | None = None
    established_year: int
    population_estimate: int
    archetype: SettlementArchetypeDto
    status: SettlementStatusDto


class StructureProjection(ApiModel):
    id: UUID
    key: str
    definition_id: str
    display_name: str
    established_year: int
    status: StructureStatusDto


class SettlementListResponse(ApiModel):
    world_id: UUID
    tick: int
    settlements: tuple[SettlementSummary, ...] = ()


class SettlementDetailResponse(ApiModel):
    world_id: UUID
    tick: int
    settlement: SettlementSummary
    structures: tuple[StructureProjection, ...] = ()


class LocalMapPhysicalContext(ApiModel):
    """Small Cliova-owned physical-context seam; richer #59 data may be added later."""

    terrain: str
    biome: str
    surface: str
    water_access: float = Field(ge=0.0, le=1.0)
    coast_fraction: float = Field(ge=0.0, le=1.0)
    mean_elevation: float = Field(ge=0.0, le=1.0)
    region_centroid_x: float | None = None
    region_centroid_y: float | None = None
    world_extent_width: int | None = None
    world_extent_height: int | None = None


class LocalMapRequest(ApiModel):
    """Deterministic rendering request derived from authoritative state.

    The browser/presentation adapter turns this request into SVG + normalized
    structured geometry. Deleting either result never changes WorldState.
    """

    contract_version: Literal["v1"] = "v1"
    world_id: UUID
    settlement_id: UUID
    layout_seed: int = Field(strict=True, gt=0)
    generation_version: str
    render_version: str
    renderer: LocalMapRendererDto
    renderer_version: str
    state_fingerprint: str
    settlement: SettlementSummary
    physical_context: LocalMapPhysicalContext
    authoritative_structures: tuple[StructureProjection, ...] = ()
    visual_style_key: str | None = None
