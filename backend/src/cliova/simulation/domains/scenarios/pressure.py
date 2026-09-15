"""Persistent emergent pressures interpreted from authoritative domain conditions."""

import json
from dataclasses import dataclass
from uuid import UUID, uuid5

from cliova.simulation.domains.economy import resource_change_key
from cliova.simulation.domains.politics import execution_strength
from cliova.simulation.domains.population import FOOD_SECURITY
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    ChangeAttribute,
    DomainResult,
    EntityId,
    EventProposal,
    ScenarioPressureState,
    SimulationChange,
    SimulationDiagnostic,
    SimulationEvent,
    SimulationExplanation,
    WorldState,
)

FOOD_INSECURITY = "food_insecurity"
_PRESSURE_CHANGE_KEY = "scenarios.pressure"
_FOOD_SHORTAGE_KEY = resource_change_key("food", "shortage_severity")
_MAX_RETAINED_CAUSES = 16


@dataclass(frozen=True, slots=True)
class FoodInsecurityRules:
    """Central tuning for the first pressure path; all values are deterministic."""

    shortage_weight: float = 0.60
    population_food_weight: float = 0.25
    governance_weight: float = 0.15
    accumulation_rate: float = 0.45
    recovery_rate: float = 0.20
    activation_signal: float = 0.12
    emerging_threshold: float = 0.05
    elevated_threshold: float = 0.35
    crisis_threshold: float = 0.65
    resolution_threshold: float = 0.03


FOOD_INSECURITY_RULES = FoodInsecurityRules()


@dataclass(frozen=True, slots=True)
class FoodInsecurityObservation:
    shortage_severity: float
    population_food_stress: float
    governance_stress: float
    signal: float
    subjects: tuple[EntityId, ...]


class ScenarioDomain:
    """Own persistent pressures while treating other domains as read-only facts."""

    name = "scenarios"
    phase = TickPhase.KNOWLEDGE_SCENARIOS

    def __init__(self, *, food_rules: FoodInsecurityRules = FOOD_INSECURITY_RULES) -> None:
        self._food_rules = food_rules

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
        del rng
        if world.economy is None or world.population is None:
            return DomainResult(
                diagnostics=(
                    SimulationDiagnostic(
                        phase=context.phase.value,
                        source=self.name,
                        message="completed food_pressure_regions=0 changes=0 events=0",
                    ),
                )
            )

        existing = {
            (pressure.key, pressure.region_id, pressure.subject_id): pressure
            for pressure in world.pressures
        }
        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []
        observed_regions = 0

        for regional_economy in sorted(
            world.economy.regions, key=lambda item: item.region_id.value.hex
        ):
            try:
                regional_economy.resource("food")
                world.population.region(regional_economy.region_id)
            except KeyError:
                continue

            observed_regions += 1
            scope = (FOOD_INSECURITY, regional_economy.region_id, None)
            current = existing.get(scope)
            observation = _food_observation(world, regional_economy.region_id, self._food_rules)
            updated = _advance_food_pressure(
                world,
                current=current,
                region_id=regional_economy.region_id,
                observation=observation,
                rules=self._food_rules,
            )
            if updated is None:
                continue

            current_causes = _relevant_causes(
                context.prior_events,
                world=world,
                region_id=regional_economy.region_id,
            )
            causes = _merge_causes(
                current.cause_event_ids if current is not None else (), current_causes
            )
            updated = updated.model_copy(update={"cause_event_ids": causes})
            if updated == current:
                continue

            region_key = _region_key(world, regional_economy.region_id)
            reason = _pressure_reason(region_key, current, updated, observation)
            change = _pressure_change(updated, previous=current, reason=reason)
            changes.append(change)

            if current is None or current.milestone != updated.milestone:
                event_kind = f"food-insecurity-{updated.milestone}"
                events.append(
                    EventProposal(
                        kind=event_kind,
                        reason=reason,
                        subjects=observation.subjects,
                        cause_event_ids=causes,
                        changes=(change,),
                    )
                )
                explanations.append(
                    SimulationExplanation(
                        source=self.name,
                        message=reason,
                        cause_event_ids=causes,
                    )
                )

        return DomainResult(
            changes=tuple(changes),
            events=tuple(events),
            explanations=tuple(explanations),
            diagnostics=(
                SimulationDiagnostic(
                    phase=context.phase.value,
                    source=self.name,
                    message=(
                        f"completed food_pressure_regions={observed_regions} "
                        f"changes={len(changes)} events={len(events)}"
                    ),
                ),
            ),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name or change.key != _PRESSURE_CHANGE_KEY:
            raise ValueError("scenario reducer only accepts scenario pressure changes")
        if change.target is None or change.target.kind != "region":
            raise ValueError("scenario pressure changes require a region target")

        state = _pressure_from_change(change)
        if state.region_id != change.target:
            raise ValueError("scenario pressure change target does not match pressure scope")

        pressures = list(world.pressures)
        index = next(
            (index for index, pressure in enumerate(pressures) if pressure.id == state.id),
            None,
        )
        scoped = next(
            (
                pressure
                for pressure in pressures
                if pressure.key == state.key
                and pressure.region_id == state.region_id
                and pressure.subject_id == state.subject_id
            ),
            None,
        )

        if index is None:
            if scoped is not None:
                raise ValueError("scenario pressure scope already has a different identity")
            if state.age_ticks != 1:
                raise ValueError("new scenario pressure must start at age one")
            if round(change.delta, 6) != round(state.intensity, 6):
                raise ValueError("new scenario pressure delta must equal its intensity")
            pressures.append(state)
        else:
            current = pressures[index]
            if (
                state.key != current.key
                or state.region_id != current.region_id
                or state.subject_id != current.subject_id
            ):
                raise ValueError("scenario pressure identity and scope are immutable")
            if state.age_ticks != current.age_ticks + 1:
                raise ValueError("scenario pressure age must advance exactly one evaluated tick")
            expected_delta = round(state.intensity - current.intensity, 6)
            if round(change.delta, 6) != expected_delta:
                raise ValueError("scenario pressure delta does not match replacement intensity")
            pressures[index] = state

        pressures.sort(key=lambda pressure: (pressure.key, pressure.region_id.value.hex, pressure.id.hex))
        return world.model_copy(update={"pressures": tuple(pressures)})


def _food_observation(
    world: WorldState, region_id: EntityId, rules: FoodInsecurityRules
) -> FoodInsecurityObservation:
    assert world.economy is not None and world.population is not None
    food = world.economy.region(region_id).resource("food")
    population = world.population.region(region_id)
    population_food_stress = round(1.0 - population.needs.food_security, 6)

    governance = sorted(
        (state for state in world.governance if state.region_id == region_id),
        key=lambda state: state.subject_id.value.hex,
    )
    governance_stress = round(
        max((1.0 - execution_strength(state) for state in governance), default=0.0),
        6,
    )
    food_gate = max(food.shortage_severity, population_food_stress)
    signal = round(
        min(
            1.0,
            rules.shortage_weight * food.shortage_severity
            + rules.population_food_weight * population_food_stress
            + rules.governance_weight * governance_stress * food_gate,
        ),
        6,
    )
    return FoodInsecurityObservation(
        shortage_severity=food.shortage_severity,
        population_food_stress=population_food_stress,
        governance_stress=governance_stress,
        signal=signal,
        subjects=(region_id, *(state.subject_id for state in governance)),
    )


def _advance_food_pressure(
    world: WorldState,
    *,
    current: ScenarioPressureState | None,
    region_id: EntityId,
    observation: FoodInsecurityObservation,
    rules: FoodInsecurityRules,
) -> ScenarioPressureState | None:
    if current is None and observation.signal < rules.activation_signal:
        return None
    if (
        current is not None
        and current.milestone == "resolved"
        and observation.signal < rules.activation_signal
    ):
        return None

    previous_intensity = current.intensity if current is not None else 0.0
    if observation.signal >= rules.activation_signal:
        intensity = previous_intensity + rules.accumulation_rate * observation.signal
    else:
        intensity = previous_intensity - rules.recovery_rate * (1.0 - observation.signal)
    intensity = round(min(1.0, max(0.0, intensity)), 6)

    if current is None and intensity < rules.emerging_threshold:
        return None
    if intensity <= rules.resolution_threshold:
        intensity = 0.0
        milestone = "resolved"
    elif observation.signal < rules.activation_signal:
        milestone = "recovering"
    elif intensity >= rules.crisis_threshold:
        milestone = "crisis"
    elif intensity >= rules.elevated_threshold:
        milestone = "elevated"
    else:
        milestone = "emerging"

    return ScenarioPressureState(
        id=current.id if current is not None else _pressure_id(world, FOOD_INSECURITY, region_id),
        key=FOOD_INSECURITY,
        region_id=region_id,
        subject_id=None,
        intensity=intensity,
        milestone=milestone,
        age_ticks=(current.age_ticks + 1) if current is not None else 1,
        cause_event_ids=current.cause_event_ids if current is not None else (),
    )


def _pressure_id(world: WorldState, key: str, region_id: EntityId) -> UUID:
    material = json.dumps(
        ["cliova.pressure.v1", key, str(region_id.value), None],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return uuid5(world.id.value, material)


def _pressure_reason(
    region_key: str,
    previous: ScenarioPressureState | None,
    updated: ScenarioPressureState,
    observation: FoodInsecurityObservation,
) -> str:
    before = previous.intensity if previous is not None else 0.0
    transition = {
        "emerging": "emerged",
        "elevated": "became elevated",
        "crisis": "entered crisis",
        "recovering": "began recovering",
        "resolved": "resolved",
    }[updated.milestone]
    return (
        f"Food insecurity in {region_key} {transition}: pressure={before:.3f}->"
        f"{updated.intensity:.3f}, shortage={observation.shortage_severity:.3f}, "
        f"population_food_stress={observation.population_food_stress:.3f}, "
        f"governance_stress={observation.governance_stress:.3f}, "
        f"signal={observation.signal:.3f}."
    )


def _relevant_causes(
    events: tuple[SimulationEvent, ...], *, world: WorldState, region_id: EntityId
) -> tuple[UUID, ...]:
    governance_subjects = {
        state.subject_id for state in world.governance if state.region_id == region_id
    }
    return tuple(
        event.id
        for event in events
        if _is_relevant_cause(event, region_id=region_id, governance_subjects=governance_subjects)
    )


def _is_relevant_cause(
    event: SimulationEvent,
    *,
    region_id: EntityId,
    governance_subjects: set[EntityId],
) -> bool:
    if event.source == "economy" and event.kind in {"resource-shortage", "resource-recovery"}:
        return any(
            change.target == region_id and change.key == _FOOD_SHORTAGE_KEY
            for change in event.changes
        )
    if event.source == "economy" and event.kind == "food-security-pressure":
        return any(
            change.source == "population"
            and change.target == region_id
            and change.key == FOOD_SECURITY
            for change in event.changes
        )
    if event.source == "population" and event.kind in {
        "population-decline",
        "population-growth",
        "migration-pressure",
    }:
        return region_id in event.subjects or any(
            change.target == region_id for change in event.changes
        )
    if event.source == "governance" and event.kind == "governance-condition-changed":
        return region_id in event.subjects or any(
            subject in governance_subjects for subject in event.subjects
        )
    if event.source == "directives" and event.kind.startswith("directive-"):
        if not any(subject in governance_subjects for subject in event.subjects):
            return False
        return any(
            change.source == "directives"
            and any(
                attribute.key == "intent" and attribute.value == "strengthen_food_reserves"
                for attribute in change.attributes
            )
            for change in event.changes
        )
    return False


def _merge_causes(previous: tuple[UUID, ...], current: tuple[UUID, ...]) -> tuple[UUID, ...]:
    merged = tuple(dict.fromkeys((*previous, *current)))
    return merged[-_MAX_RETAINED_CAUSES:]


def _pressure_change(
    state: ScenarioPressureState,
    *,
    previous: ScenarioPressureState | None,
    reason: str,
) -> SimulationChange:
    delta = state.intensity if previous is None else state.intensity - previous.intensity
    subject_kind = state.subject_id.kind if state.subject_id is not None else ""
    subject_value = str(state.subject_id.value) if state.subject_id is not None else ""
    return SimulationChange(
        source="scenarios",
        key=_PRESSURE_CHANGE_KEY,
        delta=round(delta, 6),
        reason=reason,
        target=state.region_id,
        cause_event_ids=state.cause_event_ids,
        attributes=(
            ChangeAttribute(key="id", value=str(state.id)),
            ChangeAttribute(key="key", value=state.key),
            ChangeAttribute(key="subject_kind", value=subject_kind),
            ChangeAttribute(key="subject_value", value=subject_value),
            ChangeAttribute(key="milestone", value=state.milestone),
            ChangeAttribute(key="age_ticks", value=state.age_ticks),
            ChangeAttribute(key="intensity", value=state.intensity),
        ),
    )


def _pressure_from_change(change: SimulationChange) -> ScenarioPressureState:
    attributes = {attribute.key: attribute.value for attribute in change.attributes}
    required = {
        "id",
        "key",
        "subject_kind",
        "subject_value",
        "milestone",
        "age_ticks",
        "intensity",
    }
    if set(attributes) != required:
        raise ValueError("scenario pressure change requires the complete pressure attribute set")
    assert change.target is not None

    subject_kind = str(attributes["subject_kind"])
    subject_value = str(attributes["subject_value"])
    if bool(subject_kind) != bool(subject_value):
        raise ValueError("scenario pressure subject kind/value must both be present or absent")
    subject = (
        EntityId.model_validate({"kind": subject_kind, "value": subject_value})
        if subject_kind
        else None
    )
    return ScenarioPressureState.model_validate(
        {
            "id": UUID(str(attributes["id"])),
            "key": str(attributes["key"]),
            "region_id": change.target,
            "subject_id": subject,
            "intensity": float(attributes["intensity"]),
            "milestone": str(attributes["milestone"]),
            "age_ticks": int(attributes["age_ticks"]),
            "cause_event_ids": change.cause_event_ids,
        }
    )


def _region_key(world: WorldState, region_id: EntityId) -> str:
    if world.geography is None:
        return str(region_id.value)
    for region in world.geography.regions:
        if region.id == region_id:
            return region.key
    return str(region_id.value)
