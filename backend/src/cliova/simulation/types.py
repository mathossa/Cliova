"""Serializable primitives shared by authoritative simulation domains."""

import json
from typing import Annotated, Final, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
EntityKind = Literal["world", "region", "society", "polity", "individual"]
TerrainKind = Literal["plain", "plateau", "basin", "highland", "forest", "wetland", "coast"]
BiomeKind = Literal["temperate", "semi_arid", "arid", "boreal", "tropical", "alpine"]
ResourceKind = Literal["food", "timber", "stone", "metal_ore"]
DirectiveIntent = Literal["strengthen_food_reserves"]
DirectivePriority = Literal["low", "normal", "high"]
DirectiveStatus = Literal[
    "queued",
    "accepted",
    "partial",
    "delayed",
    "resisted",
    "failed",
    "completed",
]
ChangeAttributeValue = str | int | float | bool
RNG_ALGORITHM: Final = "pcg64-sha256-v1"


class SimulationModel(BaseModel):
    """Only immutable fields belong here; nested domain state must follow suit."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class EntityId(SimulationModel):
    """A kind-qualified UUID; display names are never identities."""

    kind: EntityKind
    value: UUID


def entity_id(world_id: EntityId, kind: EntityKind, key: str) -> EntityId:
    """Derive an ID from a stable domain key, without consuming simulation RNG."""
    if world_id.kind != "world":
        raise ValueError("world_id must identify a world")
    if kind == "world" or not key:
        raise ValueError("use a non-world entity kind and a non-empty stable key")
    name = json.dumps([kind, key], ensure_ascii=True, separators=(",", ":"))
    return EntityId(kind=kind, value=uuid5(world_id.value, name))


class SimulationTime(SimulationModel):
    """Completed tick count and world year; phase is reserved for sub-year work."""

    year: Annotated[int, Field(strict=True)] = 0
    tick: NonNegativeInt = 0
    phase: NonEmptyString | None = None

    def next_year(self) -> "SimulationTime":
        if self.phase is not None:
            raise ValueError("yearly stepping does not support sub-year phases")
        return SimulationTime(year=self.year + 1, tick=self.tick + 1)


class WorldMetadata(SimulationModel):
    """Required snapshot header. Unsupported versions require an explicit migration."""

    schema_version: Literal[1]
    simulation_version: Literal[1]
    rng_algorithm: Literal["pcg64-sha256-v1"]

    @field_validator("schema_version", "simulation_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value


class ResourcePotential(SimulationModel):
    """A physical resource opportunity, not current extraction or production."""

    resource: NonEmptyString
    potential: UnitInterval


class RegionState(SimulationModel):
    """Authoritative headless geography inputs exposed to downstream domains."""

    id: EntityId
    key: NonEmptyString
    terrain: TerrainKind
    biome: BiomeKind
    habitability: UnitInterval
    water_access: UnitInterval
    climate_pressure: UnitInterval
    resources: tuple[ResourcePotential, ...] = ()

    @model_validator(mode="after")
    def validate_region(self) -> "RegionState":
        if self.id.kind != "region":
            raise ValueError("RegionState.id must identify a region")
        resource_names = [resource.resource for resource in self.resources]
        if len(resource_names) != len(set(resource_names)):
            raise ValueError("region resource names must be unique")
        return self

    def resource_potential(self, resource: str) -> float:
        """Return physical potential without implying that the resource is being extracted."""
        for candidate in self.resources:
            if candidate.resource == resource:
                return candidate.potential
        return 0.0


class RegionConnection(SimulationModel):
    """Serializable authoritative travel adjacency between two regions."""

    a: EntityId
    b: EntityId
    travel_cost: PositiveFloat

    @model_validator(mode="after")
    def validate_connection(self) -> "RegionConnection":
        if self.a.kind != "region" or self.b.kind != "region":
            raise ValueError("region connections must reference region IDs")
        if self.a == self.b:
            raise ValueError("region connections cannot be self-referential")
        return self


class GeographyState(SimulationModel):
    """Deterministic serializable physical-world state; graph objects are adapters only."""

    regions: tuple[RegionState, ...]
    connections: tuple[RegionConnection, ...]

    @model_validator(mode="after")
    def validate_geography(self) -> "GeographyState":
        region_ids = [region.id for region in self.regions]
        region_keys = [region.key for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region IDs must be unique")
        if len(region_keys) != len(set(region_keys)):
            raise ValueError("region keys must be unique")

        known_ids = set(region_ids)
        seen_connections: set[frozenset[EntityId]] = set()
        for connection in self.connections:
            if connection.a not in known_ids or connection.b not in known_ids:
                raise ValueError("region connections must reference regions in the same geography")
            edge = frozenset((connection.a, connection.b))
            if edge in seen_connections:
                raise ValueError("duplicate undirected region connection")
            seen_connections.add(edge)
        return self

    def region(self, key: str) -> RegionState:
        """Resolve a stable region key without exposing a graph implementation."""
        for region in self.regions:
            if region.key == key:
                return region
        raise KeyError(key)


class PopulationNeeds(SimulationModel):
    """Minimal aggregate conditions that demographic rules and later domains can consume."""

    food_security: UnitInterval = 1.0
    material_security: UnitInterval = 1.0
    safety: UnitInterval = 1.0
    social_confidence: UnitInterval = 1.0
    health: UnitInterval = 1.0


class RegionalPopulationState(SimulationModel):
    """Aggregate population state for one inhabited region."""

    region_id: EntityId
    total: NonNegativeInt
    needs: PopulationNeeds = Field(default_factory=PopulationNeeds)
    migration_pressure: UnitInterval = 0.0

    @model_validator(mode="after")
    def validate_region_id(self) -> "RegionalPopulationState":
        if self.region_id.kind != "region":
            raise ValueError("RegionalPopulationState.region_id must identify a region")
        return self


class PopulationDomainState(SimulationModel):
    """Region-keyed aggregate population state; absent regions are currently unpopulated."""

    regions: tuple[RegionalPopulationState, ...] = ()

    @model_validator(mode="after")
    def validate_population(self) -> "PopulationDomainState":
        region_ids = [population.region_id for population in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("population region IDs must be unique")
        return self

    def region(self, region_id: EntityId) -> RegionalPopulationState:
        """Resolve an aggregate population by its authoritative region ID."""
        for population in self.regions:
            if population.region_id == region_id:
                return population
        raise KeyError(region_id)


class ResourceEconomyState(SimulationModel):
    """One regional resource flow plus the reserve carried into future ticks."""

    resource: ResourceKind
    production_capacity: NonNegativeFloat = 0.0
    production: NonNegativeFloat = 0.0
    demand: NonNegativeFloat = 0.0
    consumed: NonNegativeFloat = 0.0
    stockpile: NonNegativeFloat = 0.0
    surplus: NonNegativeFloat = 0.0
    deficit: NonNegativeFloat = 0.0
    shortage_severity: UnitInterval = 0.0


class RegionalEconomyState(SimulationModel):
    """Deterministic aggregate economy for one inhabited region."""

    region_id: EntityId
    resources: tuple[ResourceEconomyState, ...]

    @model_validator(mode="after")
    def validate_region(self) -> "RegionalEconomyState":
        if self.region_id.kind != "region":
            raise ValueError("RegionalEconomyState.region_id must identify a region")
        resource_names = [resource.resource for resource in self.resources]
        if len(resource_names) != len(set(resource_names)):
            raise ValueError("economy resource names must be unique per region")
        return self

    def resource(self, resource: ResourceKind) -> ResourceEconomyState:
        """Resolve one resource balance without exposing storage order."""
        for candidate in self.resources:
            if candidate.resource == resource:
                return candidate
        raise KeyError(resource)


class EconomyDomainState(SimulationModel):
    """Region-keyed economy state for inhabited regions."""

    regions: tuple[RegionalEconomyState, ...] = ()

    @model_validator(mode="after")
    def validate_economy(self) -> "EconomyDomainState":
        region_ids = [economy.region_id for economy in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("economy region IDs must be unique")
        return self

    def region(self, region_id: EntityId) -> RegionalEconomyState:
        """Resolve one regional economy by authoritative region ID."""
        for economy in self.regions:
            if economy.region_id == region_id:
                return economy
        raise KeyError(region_id)


class InstitutionProfile(SimulationModel):
    """Structural parameters, without political labels or a progression ladder."""

    key: NonEmptyString
    coordination_efficiency: UnitInterval
    stress_resilience: UnitInterval
    adaptation_rate: UnitInterval


class GovernanceState(SimulationModel):
    """One playable society/polity and its current presence, not territorial ownership.

    All starting political values are explicitly supplied by the caller.
    """

    subject_id: EntityId
    region_id: EntityId
    institution: InstitutionProfile
    legitimacy: UnitInterval
    execution_capacity: UnitInterval
    internal_resistance: UnitInterval

    @model_validator(mode="after")
    def validate_identity(self) -> "GovernanceState":
        if self.subject_id.kind not in {"society", "polity"}:
            raise ValueError("governance subject must identify a society or polity")
        if self.region_id.kind != "region":
            raise ValueError("governance presence must identify a region")
        return self


class DirectiveSubmission(SimulationModel):
    """Player intent carried by a queued input; it does not directly replace domain state."""

    intent: DirectiveIntent
    priority: DirectivePriority = "normal"


class DirectiveState(SimulationModel):
    """Persistent lifecycle state for one indirect player directive."""

    id: UUID
    author: NonEmptyString
    target_subject: EntityId
    intent: DirectiveIntent
    priority: DirectivePriority
    submitted_tick: NonNegativeInt
    submission_event_id: UUID
    status: DirectiveStatus = "queued"
    progress: UnitInterval = 0.0

    @model_validator(mode="after")
    def validate_target(self) -> "DirectiveState":
        if self.target_subject.kind not in {"society", "polity"}:
            raise ValueError("directive target must identify a society or polity")
        return self


class CapabilityProgress(SimulationModel):
    capability_key: NonEmptyString
    proficiency: UnitInterval = 0.0


class ExperienceTrack(SimulationModel):
    key: NonEmptyString
    amount: NonNegativeFloat = 0.0


class SocietyKnowledgeState(SimulationModel):
    """Knowledge travels with society identity; participation is not land ownership."""

    society_id: EntityId
    region_ids: tuple[EntityId, ...] = ()
    capabilities: tuple[CapabilityProgress, ...] = ()
    experience: tuple[ExperienceTrack, ...] = ()

    @model_validator(mode="after")
    def validate_knowledge(self) -> "SocietyKnowledgeState":
        if self.society_id.kind != "society":
            raise ValueError("knowledge requires a society ID")
        if any(region.kind != "region" for region in self.region_ids):
            raise ValueError("participation requires region IDs")
        for keys in (
            self.region_ids,
            tuple(item.capability_key for item in self.capabilities),
            tuple(item.key for item in self.experience),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError("knowledge keys and participation regions must be unique")
        return self

    def proficiency(self, key: str) -> float:
        return next((c.proficiency for c in self.capabilities if c.capability_key == key), 0.0)

    def practice(self, key: str) -> float:
        return next((e.amount for e in self.experience if e.key == key), 0.0)


class KnowledgeDomainState(SimulationModel):
    societies: tuple[SocietyKnowledgeState, ...] = ()

    @model_validator(mode="after")
    def validate_societies(self) -> "KnowledgeDomainState":
        ids = [society.society_id for society in self.societies]
        if len(ids) != len(set(ids)):
            raise ValueError("knowledge society IDs must be unique")
        # Economy currently exposes whole-region activity only. Reject ambiguous
        # attribution instead of crediting the same production to multiple societies.
        regions = [region for society in self.societies for region in society.region_ids]
        if len(regions) != len(set(regions)):
            raise ValueError("regional economy participation must be unambiguous")
        return self


class WorldState(SimulationModel):
    """Authoritative aggregate; optional domain state keeps legacy snapshots loadable."""

    id: EntityId
    seed: Annotated[int, Field(strict=True)]
    metadata: WorldMetadata
    time: SimulationTime
    geography: GeographyState | None = None
    population: PopulationDomainState | None = None
    economy: EconomyDomainState | None = None
    knowledge: KnowledgeDomainState | None = None
    governance: tuple[GovernanceState, ...] = ()
    directives: tuple[DirectiveState, ...] = ()

    @model_validator(mode="after")
    def check_world_id(self) -> "WorldState":
        if self.id.kind != "world":
            raise ValueError("WorldState.id must identify a world")
        return self

    @model_validator(mode="after")
    def validate_population_region_references(self) -> "WorldState":
        if self.population is None or not self.population.regions:
            return self
        if self.geography is None:
            raise ValueError("populated world state requires geography")
        region_ids = {region.id for region in self.geography.regions}
        if any(population.region_id not in region_ids for population in self.population.regions):
            raise ValueError("population regions must reference regions in world geography")
        return self

    @model_validator(mode="after")
    def validate_knowledge_regions(self) -> "WorldState":
        if self.knowledge is not None:
            regions = {region.id for region in self.geography.regions} if self.geography else set()
            if any(
                region not in regions
                for society in self.knowledge.societies
                for region in society.region_ids
            ):
                raise ValueError("knowledge participation must reference world geography")
        return self

    @model_validator(mode="after")
    def validate_governance(self) -> "WorldState":
        subjects = [state.subject_id for state in self.governance]
        if len(subjects) != len(set(subjects)):
            raise ValueError("governance subject IDs must be unique")
        for state in self.governance:
            if self.geography is None or state.region_id not in {
                region.id for region in self.geography.regions
            }:
                raise ValueError("governance presence must reference world geography")
            if self.population is None or self.economy is None:
                raise ValueError("governance requires population and economy pressure inputs")
            try:
                self.population.region(state.region_id)
                self.economy.region(state.region_id).resource("food")
            except KeyError as exc:
                raise ValueError("governance region requires population and food economy") from exc
        return self

    @model_validator(mode="after")
    def validate_directives(self) -> "WorldState":
        ids = [state.id for state in self.directives]
        if len(ids) != len(set(ids)):
            raise ValueError("directive IDs must be unique")
        return self

    @property
    def year(self) -> int:
        """Read-only convenience for the existing headless CLI."""
        return self.time.year

    @classmethod
    def create(cls, *, seed: int, world_key: str = "default") -> "WorldState":
        """Identical seed/key pairs identify the same reproducible initial world."""
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        if not isinstance(world_key, str) or not world_key:
            raise ValueError("world_key must be a non-empty string")
        name = json.dumps(
            ["cliova.world.v1", seed, world_key], ensure_ascii=True, separators=(",", ":")
        )
        world_id = EntityId(kind="world", value=uuid5(NAMESPACE_URL, name))

        # Import lazily so the world domain can depend on shared simulation primitives.
        from cliova.simulation.domains.world.generation import generate_geography

        return cls(
            id=world_id,
            seed=seed,
            metadata=WorldMetadata(
                schema_version=1, simulation_version=1, rng_algorithm=RNG_ALGORITHM
            ),
            time=SimulationTime(),
            geography=generate_geography(world_id=world_id, seed=seed),
        )


class ChangeAttribute(SimulationModel):
    """Small immutable typed metadata item for domain-owned non-numeric change context."""

    key: NonEmptyString
    value: ChangeAttributeValue


class SimulationChange(SimulationModel):
    """A proposed change applied centrally by its owning simulation domain."""

    source: NonEmptyString
    key: NonEmptyString
    delta: float
    reason: NonEmptyString
    target: EntityId | None = None
    cause_event_ids: tuple[UUID, ...] = ()
    attributes: tuple[ChangeAttribute, ...] = ()

    @model_validator(mode="after")
    def validate_attributes(self) -> "SimulationChange":
        keys = [attribute.key for attribute in self.attributes]
        if len(keys) != len(set(keys)):
            raise ValueError("simulation change attribute keys must be unique")
        return self


class SimulationEvent(SimulationModel):
    """Immutable event envelope, with ordered changes and explicit causal references."""

    id: UUID
    time: SimulationTime
    source: NonEmptyString
    kind: NonEmptyString
    reason: NonEmptyString
    subjects: tuple[EntityId, ...] = ()
    cause_event_ids: tuple[UUID, ...] = ()
    changes: tuple[SimulationChange, ...] = ()


class EventProposal(SimulationModel):
    """Domain-emitted event data; the engine assigns its deterministic event ID/time/source."""

    kind: NonEmptyString
    reason: NonEmptyString
    subjects: tuple[EntityId, ...] = ()
    cause_event_ids: tuple[UUID, ...] = ()
    changes: tuple[SimulationChange, ...] = ()


class SimulationInput(SimulationModel):
    """Ordered player/world input queued for the next tick."""

    source: NonEmptyString
    kind: NonEmptyString
    reason: NonEmptyString
    subjects: tuple[EntityId, ...] = ()
    changes: tuple[SimulationChange, ...] = ()
    directive: DirectiveSubmission | None = None


class SimulationExplanation(SimulationModel):
    """Structured human-facing causal explanation emitted during a tick or history query."""

    source: NonEmptyString
    message: NonEmptyString
    event_id: UUID | None = None
    cause_event_ids: tuple[UUID, ...] = ()


class SimulationDiagnostic(SimulationModel):
    """Deterministic debug information for replaying and inspecting a tick."""

    phase: NonEmptyString
    source: NonEmptyString
    message: NonEmptyString


class DomainResult(SimulationModel):
    """A domain proposal. No authoritative state is committed by returning this model."""

    changes: tuple[SimulationChange, ...] = ()
    events: tuple[EventProposal, ...] = ()
    explanations: tuple[SimulationExplanation, ...] = ()
    diagnostics: tuple[SimulationDiagnostic, ...] = ()


class TickResult(SimulationModel):
    """Authoritative committed result of exactly one completed tick."""

    world: WorldState
    phases: tuple[NonEmptyString, ...]
    changes: tuple[SimulationChange, ...] = ()
    events: tuple[SimulationEvent, ...] = ()
    explanations: tuple[SimulationExplanation, ...] = ()
    diagnostics: tuple[SimulationDiagnostic, ...] = ()


class SimulationRunResult(SimulationModel):
    """Headless multi-tick result with each committed tick retained for inspection."""

    world: WorldState
    ticks: tuple[TickResult, ...] = ()
