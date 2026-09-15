"""Minimal deterministic governance over explicit regional pressure observations."""

from collections.abc import Iterable
from uuid import UUID

from cliova.simulation.domains.economy import resource_change_key
from cliova.simulation.domains.population.domain import MIGRATION_PRESSURE, SOCIAL_CONFIDENCE
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EventProposal,
    GovernanceState,
    SimulationChange,
    SimulationExplanation,
    SimulationModel,
    UnitInterval,
    WorldState,
)

GOVERNANCE_FIELDS = ("legitimacy", "execution_capacity", "internal_resistance")
SIGNIFICANT_GOVERNANCE_CHANGE = 0.05
_PRESSURE_KEYS = {
    ("population", SOCIAL_CONFIDENCE),
    ("population", MIGRATION_PRESSURE),
    ("economy", resource_change_key("food", "shortage_severity")),
}


class GovernancePressure(SimulationModel):
    """Governance-owned interpretation boundary; population/economy own the facts."""

    social_confidence: UnitInterval
    migration_pressure: UnitInterval
    food_shortage_severity: UnitInterval
    cause_event_ids: tuple[UUID, ...] = ()


def initialize_governance(world: WorldState, *, states: Iterable[GovernanceState]) -> WorldState:
    """Attach explicitly configured societies; never infer identity or starting values."""
    if world.governance:
        raise ValueError("governance is already initialized")
    return WorldState.model_validate({**world.model_dump(), "governance": tuple(states)})


def governance_pressure(
    world: WorldState, state: GovernanceState, context: TickContext
) -> GovernancePressure:
    """Observe finalized same-tick facts, retaining only matching regional causes."""
    if world.population is None or world.economy is None:
        raise ValueError("governance requires population and economy")
    population = world.population.region(state.region_id)
    food = world.economy.region(state.region_id).resource("food")
    causes = tuple(
        dict.fromkeys(
            event.id
            for event in context.prior_events
            if any(
                change.target == state.region_id and (change.source, change.key) in _PRESSURE_KEYS
                for change in event.changes
            )
        )
    )
    return GovernancePressure(
        social_confidence=population.needs.social_confidence,
        migration_pressure=population.migration_pressure,
        food_shortage_severity=food.shortage_severity,
        cause_event_ids=causes,
    )


def advance_governance(state: GovernanceState, pressure: GovernancePressure) -> GovernanceState:
    """Move toward stress-dependent targets using the same rules for every institution."""
    profile = state.institution
    stress = max(
        1.0 - pressure.social_confidence,
        pressure.migration_pressure,
        pressure.food_shortage_severity,
    ) * (1.0 - profile.stress_resilience)

    def approach(current: float, target: float) -> float:
        return round(current + (target - current) * profile.adaptation_rate, 6)

    resistance = approach(state.internal_resistance, stress)
    legitimacy = approach(state.legitimacy, 1.0 - max(stress, resistance))
    capacity = approach(
        state.execution_capacity,
        profile.coordination_efficiency * legitimacy * (1.0 - resistance),
    )
    return GovernanceState(
        subject_id=state.subject_id,
        region_id=state.region_id,
        institution=profile,
        legitimacy=legitimacy,
        execution_capacity=capacity,
        internal_resistance=resistance,
    )


def execution_strength(state: GovernanceState) -> float:
    """Return #9's political bottleneck; no directive cost, status or effects are resolved."""
    return min(state.execution_capacity, state.legitimacy, 1.0 - state.internal_resistance)


class GovernanceDomain:
    name = "governance"
    phase = TickPhase.GOVERNANCE

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
        del rng
        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []
        for state in sorted(world.governance, key=lambda item: str(item.subject_id.value)):
            pressure = governance_pressure(world, state, context)
            outcome = advance_governance(state, pressure)
            reason = (
                f"Governance responded to social confidence={pressure.social_confidence:.6f}, "
                f"migration pressure={pressure.migration_pressure:.6f}, "
                f"food shortage={pressure.food_shortage_severity:.6f}; "
                f"institution={state.institution.key}, "
                f"coordination={state.institution.coordination_efficiency:.6f}, "
                f"resilience={state.institution.stress_resilience:.6f}, "
                f"adaptation={state.institution.adaptation_rate:.6f}."
            )
            subject_changes = tuple(
                SimulationChange(
                    source=self.name,
                    key=f"governance.{field}",
                    delta=round(getattr(outcome, field) - getattr(state, field), 6),
                    reason=reason,
                    target=state.subject_id,
                    cause_event_ids=pressure.cause_event_ids,
                )
                for field in GOVERNANCE_FIELDS
                if getattr(outcome, field) != getattr(state, field)
            )
            changes.extend(subject_changes)
            if any(
                abs(change.delta) >= SIGNIFICANT_GOVERNANCE_CHANGE for change in subject_changes
            ):
                events.append(
                    EventProposal(
                        kind="governance-condition-changed",
                        reason=reason,
                        subjects=(state.subject_id, state.region_id),
                        cause_event_ids=pressure.cause_event_ids,
                        changes=subject_changes,
                    )
                )
                explanations.append(
                    SimulationExplanation(
                        source=self.name,
                        message=reason,
                        cause_event_ids=pressure.cause_event_ids,
                    )
                )
        return DomainResult(
            changes=tuple(changes),
            events=tuple(events),
            explanations=tuple(explanations),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name:
            raise ValueError("governance reducer only accepts governance-owned changes")
        if change.key not in {f"governance.{field}" for field in GOVERNANCE_FIELDS}:
            raise ValueError("unsupported governance change key")
        index = next(
            (i for i, state in enumerate(world.governance) if state.subject_id == change.target),
            None,
        )
        if index is None:
            raise ValueError("governance change requires an initialized society/polity target")
        states = list(world.governance)
        state = states[index]
        field = change.key.split(".")[1]
        value = round(getattr(state, field) + change.delta, 6)
        states[index] = GovernanceState.model_validate({**state.model_dump(), field: value})
        return world.model_copy(update={"governance": tuple(states)})
