"""Small generic capability catalog; tuning constants are simulation rules."""

from cliova.simulation.domains.knowledge.types import (
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityRequirement,
    ExperienceRequirement,
    ResourcePotentialRequirement,
)

LEARNING_RATE = 0.1
PRACTICE_SATURATION = 5.0
DEMAND_PRESSURE = 0.25

CAPABILITIES = (
    CapabilityDefinition(
        key="cultivation_efficiency",
        requirements=(
            ResourcePotentialRequirement(resource="arable_land", min_potential=0.25),
            ExperienceRequirement(track="cultivation", minimum=1.0),
        ),
        activation_threshold=0.2,
        practice_track="cultivation",
        pressure_key="food",
        effect=CapabilityEffect(resource="food", max_bonus=0.25),
    ),
    CapabilityDefinition(
        key="soil_management",
        requirements=(
            CapabilityRequirement(capability_key="cultivation_efficiency", min_proficiency=0.35),
            ResourcePotentialRequirement(resource="arable_land", min_potential=0.35),
            ExperienceRequirement(track="cultivation", minimum=5.0),
        ),
        activation_threshold=0.2,
        practice_track="cultivation",
        pressure_key="food",
        effect=CapabilityEffect(resource="food", max_bonus=0.15),
    ),
    CapabilityDefinition(
        key="ore_extraction",
        requirements=(
            ResourcePotentialRequirement(resource="metal_ores", min_potential=0.25),
            ExperienceRequirement(track="extraction", minimum=1.0),
        ),
        activation_threshold=0.2,
        practice_track="extraction",
        pressure_key="metal_ore",
        effect=CapabilityEffect(resource="metal_ore", max_bonus=0.25),
    ),
    CapabilityDefinition(
        key="advanced_extraction",
        requirements=(
            CapabilityRequirement(capability_key="ore_extraction", min_proficiency=0.4),
            ResourcePotentialRequirement(resource="metal_ores", min_potential=0.5),
            ExperienceRequirement(track="extraction", minimum=5.0),
        ),
        activation_threshold=0.2,
        practice_track="extraction",
        pressure_key="metal_ore",
        effect=CapabilityEffect(resource="metal_ore", max_bonus=0.15),
    ),
)
