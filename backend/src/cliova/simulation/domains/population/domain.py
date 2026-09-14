"""Deterministic aggregate demography and population-pressure rules."""

from dataclasses import dataclass
from uuid import UUID

from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EntityId,
    EventProposal,
    PopulationDomainState,
    RegionalPopulationState,
    RegionState,
    SimulationChange,
    SimulationDiagnostic,
    SimulationExplanation,
    WorldState,
)

POPULATION_TOTAL = "population.total"
FOOD_SECURITY = "population.food_security"
MATERIAL_SECURITY = "population.material_security"
SAFETY = "population.safety"
SOCIAL_CONFIDENCE = "population.social_confidence"
HEALTH = "population.health"
MIGRATION_PRESSURE = "population.migration_pressure"

PRESSURE_KEYS = frozenset(
    {FOOD_SECURITY, MATERIAL_SECURITY, SAFETY, SOCIAL_CONFIDENCE, HEALTH}
)

BASE_BIRTH_RATE = 0.024
BASE_MORTALITY_RATE = 0.012
FOOD_MORTALITY_WEIGHT = 0.035
MATERIAL_MORTALITY_WEIGHT = 0.008
HEALTH_MORTALITY_WEIGHT = 0.025
SAFETY_MORTALITY_WEIGHT = 0.020
ENVIRONMENT_MORTALITY_WEIGHT = 0.012
SIGNIFICANT_POPULATION_RATE = 0.02
SIGNIFICANT_MIGRATION_DELTA = 0.20


@dataclass(frozen=True, slots=True)
class DemographicOutcome:
    births: int
    deaths: int
    net_change: int
    migration_pressure: float


class PopulationDomain:
    """Aggregate population domain; it never mutates economy, governance or geography."""

    name = "population"
    phase = TickPhase.POPULATION

    def step(
        self,
        world: WorldState,
        context: TickContext,
        rng: RandomSource,
    ) -> DomainResult:
        del rng  # The first aggregate rules are deterministic without stochastic sampling.

        if world.population is None or not world.population.regions:
            return DomainResult(
                diagnostics=(
                    SimulationDiagnostic(
                        phase=context.phase.value,
                        source=self.name,
                        message="completed populated_regions=0 changes=0 events=0",
                    ),
                )
            )
        if world.geography is None:
            raise ValueError("population simulation requires geography")

        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []

        for population in world.population.regions:
            region = _region_by_id(world, population.region_id)
            causes = self._pressure_causes(context, population.region_id)
            outcome = _calculate_outcome(population, region)
            region_changes: list[SimulationChange] = []

            if outcome.net_change:
                region_changes.append(
                    SimulationChange(
                        source=self.name,
                        key=POPULATION_TOTAL,
                        delta=float(outcome.net_change),
                        reason=(
                            f"births={outcome.births}; deaths={outcome.deaths}; "
                            "aggregate demographic change"
                        ),
                        target=population.region_id,
                        cause_event_ids=causes,
                    )
                )

            migration_delta = round(
                outcome.migration_pressure - population.migration_pressure, 6
            )
            if migration_delta:
                region_changes.append(
                    SimulationChange(
                        source=self.name,
                        key=MIGRATION_PRESSURE,
                        delta=migration_delta,
                        reason="aggregate need and regional pressures changed migration pressure",
                        target=population.region_id,
                        cause_event_ids=causes,
                    )
                )

            changes.extend(region_changes)
            if region_changes and _is_significant(population, outcome, migration_delta):
                reason = _event_reason(region, population, outcome)
                kind = (
                    "population-decline"
                    if outcome.net_change < 0
                    else "population-growth"
                    if outcome.net_change > 0
                    else "migration-pressure"
                )
                events.append(
                    EventProposal(
                        kind=kind,
                        reason=reason,
                        subjects=(population.region_id,),
                        cause_event_ids=causes,
                        changes=tuple(region_changes),
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
                        f"completed populated_regions={len(world.population.regions)} "
                        f"changes={len(changes)} events={len(events)}"
                    ),
                ),
            ),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if world.population is None:
            raise ValueError("population change requires initialized population state")
        if change.target is None or change.target.kind != "region":
            raise ValueError("population changes require a region target")

        populations = list(world.population.regions)
        index = next(
            (
                position
                for position, population in enumerate(populations)
                if population.region_id == change.target
            ),
            None,
        )
        if index is None:
            raise ValueError("population change target is not an inhabited region")

        current = populations[index]
        if change.key == POPULATION_TOTAL:
            if not float(change.delta).is_integer():
                raise ValueError("population.total changes must use whole people")
            total = current.total + int(change.delta)
            if total < 0:
                raise ValueError("population total cannot become negative")
            updated = current.model_copy(update={"total": total})
        elif change.key == MIGRATION_PRESSURE:
            updated = current.model_copy(
                update={
                    "migration_pressure": _bounded_add(
                        current.migration_pressure, change.delta, MIGRATION_PRESSURE
                    )
                }
            )
        elif change.key in PRESSURE_KEYS:
            field = _need_field(change.key)
            needs = current.needs.model_copy(
                update={field: _bounded_add(getattr(current.needs, field), change.delta, change.key)}
            )
            updated = current.model_copy(update={"needs": needs})
        else:
            raise ValueError(f"unsupported population change key {change.key!r}")

        populations[index] = updated
        state = PopulationDomainState(regions=tuple(populations))
        return world.model_copy(update={"population": state})

    def _pressure_causes(self, context: TickContext, region_id: EntityId) -> tuple[UUID, ...]:
        return tuple(
            event.id
            for event in context.prior_events
            if any(
                change.source == self.name
                and change.target == region_id
                and change.key in PRESSURE_KEYS
                for change in event.changes
            )
        )


def _need_field(key: str) -> str:
    return {
        FOOD_SECURITY: "food_security",
        MATERIAL_SECURITY: "material_security",
        SAFETY: "safety",
        SOCIAL_CONFIDENCE: "social_confidence",
        HEALTH: "health",
    }[key]


def _bounded_add(current: float, delta: float, key: str) -> float:
    value = round(current + delta, 6)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{key} must remain between 0 and 1")
    return value


def _region_by_id(world: WorldState, region_id: EntityId) -> RegionState:
    assert world.geography is not None
    for region in world.geography.regions:
        if region.id == region_id:
            return region
    raise ValueError("population region does not exist in geography")


def _environment_stress(region: RegionState) -> float:
    return (
        0.40 * (1.0 - region.habitability)
        + 0.25 * (1.0 - region.water_access)
        + 0.35 * region.climate_pressure
    )


def _calculate_outcome(
    population: RegionalPopulationState, region: RegionState
) -> DemographicOutcome:
    needs = population.needs
    food_stress = 1.0 - needs.food_security
    material_stress = 1.0 - needs.material_security
    safety_stress = 1.0 - needs.safety
    confidence_stress = 1.0 - needs.social_confidence
    health_stress = 1.0 - needs.health
    environment_stress = _environment_stress(region)

    birth_factor = max(
        0.0,
        1.0 - 0.65 * food_stress - 0.15 * material_stress - 0.20 * health_stress,
    )
    birth_rate = BASE_BIRTH_RATE * birth_factor
    mortality_rate = min(
        1.0,
        BASE_MORTALITY_RATE
        + FOOD_MORTALITY_WEIGHT * food_stress
        + MATERIAL_MORTALITY_WEIGHT * material_stress
        + HEALTH_MORTALITY_WEIGHT * health_stress
        + SAFETY_MORTALITY_WEIGHT * safety_stress
        + ENVIRONMENT_MORTALITY_WEIGHT * environment_stress,
    )

    births = int(round(population.total * birth_rate))
    deaths = min(population.total + births, int(round(population.total * mortality_rate)))
    migration_pressure = round(
        min(
            1.0,
            0.45 * food_stress
            + 0.15 * material_stress
            + 0.15 * safety_stress
            + 0.10 * confidence_stress
            + 0.10 * health_stress
            + 0.05 * environment_stress,
        ),
        6,
    )

    return DemographicOutcome(
        births=births,
        deaths=deaths,
        net_change=births - deaths,
        migration_pressure=migration_pressure,
    )


def _is_significant(
    population: RegionalPopulationState,
    outcome: DemographicOutcome,
    migration_delta: float,
) -> bool:
    if population.total:
        population_rate = abs(outcome.net_change) / population.total
    else:
        population_rate = 0.0
    return (
        population_rate >= SIGNIFICANT_POPULATION_RATE
        or abs(migration_delta) >= SIGNIFICANT_MIGRATION_DELTA
    )


def _event_reason(
    region: RegionState,
    population: RegionalPopulationState,
    outcome: DemographicOutcome,
) -> str:
    if outcome.net_change > 0:
        direction = f"grew by {outcome.net_change}"
    elif outcome.net_change < 0:
        direction = f"declined by {abs(outcome.net_change)}"
    else:
        direction = "was stable"
    return (
        f"Population in {region.key} {direction}: births={outcome.births}, "
        f"deaths={outcome.deaths}, migration_pressure={outcome.migration_pressure:.3f}; "
        f"food_security={population.needs.food_security:.3f}, "
        f"material_security={population.needs.material_security:.3f}, "
        f"health={population.needs.health:.3f}."
    )
