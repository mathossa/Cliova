"""Immutable catalog rules and explicit regional learning inputs."""

from uuid import UUID

from cliova.simulation.types import (
    EntityId,
    NonEmptyString,
    NonNegativeFloat,
    PositiveFloat,
    ResourceKind,
    SimulationModel,
    UnitInterval,
)


class CapabilityRequirement(SimulationModel):
    capability_key: NonEmptyString
    min_proficiency: UnitInterval


class ResourcePotentialRequirement(SimulationModel):
    resource: NonEmptyString
    min_potential: UnitInterval


class ExperienceRequirement(SimulationModel):
    track: NonEmptyString
    minimum: NonNegativeFloat


class CapabilityEffect(SimulationModel):
    resource: ResourceKind
    production_method: NonEmptyString | None = None
    max_bonus: NonNegativeFloat


class CapabilityDefinition(SimulationModel):
    key: NonEmptyString
    requirements: tuple[
        CapabilityRequirement | ResourcePotentialRequirement | ExperienceRequirement, ...
    ]
    activation_threshold: PositiveFloat
    practice_track: NonEmptyString
    pressure_key: NonEmptyString
    effect: CapabilityEffect


class InnovationPressureSignal(SimulationModel):
    key: NonEmptyString
    magnitude: UnitInterval
    reason: NonEmptyString
    cause_event_ids: tuple[UUID, ...] = ()


class ExperienceGain(SimulationModel):
    track: NonEmptyString
    amount: NonNegativeFloat
    cause_event_ids: tuple[UUID, ...] = ()


class RegionalLearningInput(SimulationModel):
    society_id: EntityId
    region_id: EntityId
    pressures: tuple[InnovationPressureSignal, ...] = ()
    experience: tuple[ExperienceGain, ...] = ()
