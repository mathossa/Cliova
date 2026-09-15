"""Stable HTTP v1 DTOs. These models are not simulation or persistence state."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EntityKindDto = Literal["world", "region", "society", "polity", "individual"]
DirectiveIntentDto = Literal["strengthen_food_reserves"]
DirectivePriorityDto = Literal["low", "normal", "high"]
DirectiveStatusDto = Literal[
    "queued", "accepted", "partial", "delayed", "resisted", "failed", "completed"
]
PressureMilestoneDto = Literal["emerging", "elevated", "crisis", "recovering", "resolved"]
AttentionPriorityDto = Literal["informational", "important", "urgent"]
DecisionOpportunityStatusDto = Literal["open", "responded", "expired"]
MapVisibilityDto = Literal["full"]
SettlementArchetypeDto = Literal["permanent", "seasonal_camp", "temporary_camp"]
SettlementStatusDto = Literal["active", "dormant", "abandoned", "destroyed"]
MapPositionPrecisionDto = Literal["region_centroid"]
NonNegativeStrictInt = Annotated[int, Field(strict=True, ge=0)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityRef(ApiModel):
    kind: EntityKindDto
    id: UUID


class VersionMetadata(ApiModel):
    contract_version: Literal["v1"] = "v1"
    world_schema_version: int
    simulation_version: int
    rng_algorithm: str


class FoodStatus(ApiModel):
    food_security: float | None = None
    production: float | None = None
    demand: float | None = None
    stockpile: float | None = None
    deficit: float | None = None
    shortage_severity: float | None = None


class GovernanceCondition(ApiModel):
    legitimacy: float
    execution_capacity: float
    internal_resistance: float


class PressureStatus(ApiModel):
    id: UUID
    key: str
    region_id: UUID
    subject: EntityRef | None = None
    intensity: float
    milestone: PressureMilestoneDto
    age_ticks: int
    cause_event_ids: tuple[UUID, ...] = ()


class SocietySummary(ApiModel):
    subject: EntityRef
    region_id: UUID
    population: int | None = None
    food: FoodStatus
    governance: GovernanceCondition


class RegionStatus(ApiModel):
    id: UUID
    key: str
    terrain: str
    biome: str
    habitability: float
    water_access: float
    climate_pressure: float
    population: int | None = None
    food: FoodStatus
    pressures: tuple[PressureStatus, ...] = ()


class MapMultiPolygon(ApiModel):
    """GeoJSON-compatible game-coordinate geometry; values are never earth lat/lon."""

    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: tuple[
        tuple[tuple[tuple[float, float], ...], ...],
        ...,
    ]


class TemporaryPresence(ApiModel):
    society_id: UUID
    production_method: str
    access_share: float


class MapRegionFeature(ApiModel):
    id: UUID
    key: str
    centroid: tuple[float, float]
    geometry: MapMultiPolygon
    terrain: str
    biome: str
    surface: str
    land_fraction: float
    mean_elevation: float
    population: int | None = None
    food_shortage_severity: float | None = None
    pressure_intensity: float | None = None
    core_society_ids: tuple[UUID, ...] = ()
    temporary_presence: tuple[TemporaryPresence, ...] = ()
    visibility: MapVisibilityDto = "full"


class SettlementMapMarker(ApiModel):
    id: UUID
    region_id: UUID
    name: str
    archetype: SettlementArchetypeDto
    status: SettlementStatusDto
    population_estimate: int
    associated_subject: EntityRef | None = None
    position: tuple[float, float]
    position_precision: MapPositionPrecisionDto = "region_centroid"
    structure_count: int = 0
    local_map_path: str
    visibility: MapVisibilityDto = "full"


class WorldMapResponse(ApiModel):
    world_id: UUID
    tick: int
    available: bool
    unavailable_reason: str | None = None
    render_version: str
    coordinate_system: Literal["cliova-grid-bottom-left-v1"] = "cliova-grid-bottom-left-v1"
    extent_width: int = 0
    extent_height: int = 0
    base_map_url: str | None = None
    visibility: MapVisibilityDto = "full"
    regions: tuple[MapRegionFeature, ...] = ()
    settlements: tuple[SettlementMapMarker, ...] = ()


class WorldListItem(ApiModel):
    id: UUID
    tick: int
    year: int
    region_count: int
    society_count: int
    population_total: int | None = None


class WorldListResponse(ApiModel):
    worlds: tuple[WorldListItem, ...]


class WorldSummary(ApiModel):
    id: UUID
    tick: int
    year: int
    versions: VersionMetadata
    region_count: int
    population_total: int | None = None
    food_shortage_severity: float | None = None
    societies: tuple[SocietySummary, ...] = ()
    pressures: tuple[PressureStatus, ...] = ()


class RegionStatusResponse(ApiModel):
    world_id: UUID
    tick: int
    regions: tuple[RegionStatus, ...]


class SocietyStatusResponse(ApiModel):
    world_id: UUID
    tick: int
    societies: tuple[SocietySummary, ...]


class CreateDevelopmentWorldRequest(ApiModel):
    seed: int = Field(strict=True)
    world_key: str = Field(default="development", min_length=1, max_length=100)
    generated_geography: bool = False


class HistoryEvent(ApiModel):
    id: UUID
    tick: int
    year: int
    source: str
    kind: str
    reason: str
    subjects: tuple[EntityRef, ...] = ()
    cause_event_ids: tuple[UUID, ...] = ()


class HistoryResponse(ApiModel):
    world_id: UUID
    events: tuple[HistoryEvent, ...]


class DirectiveTarget(ApiModel):
    kind: Literal["society", "polity"]
    id: UUID


class DirectiveSubmissionRequest(ApiModel):
    author: str = Field(min_length=1, max_length=100)
    target: DirectiveTarget
    intent: DirectiveIntentDto = "strengthen_food_reserves"
    priority: DirectivePriorityDto = "normal"
    decision_opportunity_id: UUID | None = None


class QueuedDirective(ApiModel):
    queue_id: int
    submitted_tick: int
    author: str
    target: DirectiveTarget
    intent: DirectiveIntentDto
    priority: DirectivePriorityDto


class AuthoritativeDirective(ApiModel):
    id: UUID
    author: str
    target: DirectiveTarget
    intent: DirectiveIntentDto
    priority: DirectivePriorityDto
    submitted_tick: int
    submission_event_id: UUID
    status: DirectiveStatusDto
    progress: float


class DirectiveListResponse(ApiModel):
    world_id: UUID
    pending: tuple[QueuedDirective, ...] = ()
    directives: tuple[AuthoritativeDirective, ...] = ()


class AttentionItemDto(ApiModel):
    id: UUID
    target: EntityRef | None = None
    created_tick: int
    created_year: int
    category: str
    priority: AttentionPriorityDto
    context: str
    related_event_ids: tuple[UUID, ...] = ()
    related_subjects: tuple[EntityRef, ...] = ()


class AttentionItemsResponse(ApiModel):
    world_id: UUID
    items: tuple[AttentionItemDto, ...] = ()


class DecisionOpportunityDto(ApiModel):
    id: UUID
    target: DirectiveTarget
    created_tick: int
    created_year: int
    category: str
    context: str
    related_event_ids: tuple[UUID, ...] = ()
    related_subjects: tuple[EntityRef, ...] = ()
    earliest_effect_tick: int
    expires_at_tick: int | None = None
    default_behavior: str
    response_intent: DirectiveIntentDto
    status: DecisionOpportunityStatusDto
    response_queue_id: int | None = None
    response_submitted_tick: int | None = None
    response_directive_id: UUID | None = None


class DecisionOpportunityListResponse(ApiModel):
    world_id: UUID
    opportunities: tuple[DecisionOpportunityDto, ...] = ()


class ManualTickRequest(ApiModel):
    expected_tick: NonNegativeStrictInt


class ManualTickResponse(ApiModel):
    world: WorldSummary
    event_ids: tuple[UUID, ...] = ()


class ApiErrorDetail(ApiModel):
    location: str | None = None
    message: str
    type: str | None = None


class ApiErrorBody(ApiModel):
    code: str
    message: str
    details: tuple[ApiErrorDetail, ...] = ()


class ApiErrorResponse(ApiModel):
    error: ApiErrorBody
