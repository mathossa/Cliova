"""Deterministic regional production, consumption, reserves and shortages."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import UUID

from cliova.simulation.domains.population import (
    FOOD_SECURITY,
    PopulationNeedTarget,
    population_need_input,
)
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EconomyDomainState,
    EntityId,
    EventProposal,
    RegionalPopulationState,
    RegionState,
    ResourceEconomyState,
    ResourceKind,
    SimulationChange,
    SimulationDiagnostic,
    SimulationEvent,
    SimulationExplanation,
    SimulationInput,
    WorldState,
)

RESOURCE_KINDS: tuple[ResourceKind, ...] = ("food", "timber", "stone", "metal_ore")
LABOUR_SHARE = 0.45
SIGNIFICANT_SHORTAGE_SEVERITY = 0.10
SIGNIFICANT_SURPLUS_RATIO = 0.10
SIGNIFICANT_SEVERITY_CHANGE = 0.25


@dataclass(frozen=True, slots=True)
class ResourceRule:
    potential_key: str
    demand_per_capita: float
    output_per_worker: float


RESOURCE_RULES: dict[ResourceKind, ResourceRule] = {
    "food": ResourceRule("arable_land", demand_per_capita=1.0, output_per_worker=2.8),
    "timber": ResourceRule("timber", demand_per_capita=0.08, output_per_worker=0.50),
    "stone": ResourceRule("stone", demand_per_capita=0.05, output_per_worker=0.40),
    "metal_ore": ResourceRule("metal_ores", demand_per_capita=0.03, output_per_worker=0.25),
}

RESOURCE_FIELDS = frozenset(
    {
        "production_capacity",
        "production",
        "demand",
        "consumed",
        "stockpile",
        "surplus",
        "deficit",
        "shortage_severity",
    }
)

CapabilityModifier = Callable[[WorldState, EntityId, ResourceKind], float]


@dataclass(frozen=True, slots=True)
class ResourceOutcome:
    production_capacity: float
    production: float
    demand: float
    consumed: float
    stockpile: float
    surplus: float
    deficit: float
    shortage_severity: float


class EconomyDomain:
    """Aggregate regional economy; production is constrained by people and geography."""

    name = "economy"
    phase = TickPhase.ECONOMY

    def __init__(self, capability_modifier: CapabilityModifier | None = None) -> None:
        # Issue #11 can supply a deterministic capability multiplier later without
        # changing this issue's production/stockpile model.
        self._capability_modifier = capability_modifier or _neutral_capability_modifier

    def step(
        self,
        world: WorldState,
        context: TickContext,
        rng: RandomSource,
    ) -> DomainResult:
        del rng  # The first economy rules are deterministic without stochastic sampling.

        if world.economy is None or not world.economy.regions:
            return DomainResult(
                diagnostics=(
                    SimulationDiagnostic(
                        phase=context.phase.value,
                        source=self.name,
                        message="completed economy_regions=0 changes=0 events=0",
                    ),
                )
            )
        if world.population is None:
            raise ValueError("economy simulation requires population")
        if world.geography is None:
            raise ValueError("economy simulation requires geography")

        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []

        for regional_economy in world.economy.regions:
            population = world.population.region(regional_economy.region_id)
            region = _region_by_id(world, regional_economy.region_id)
            causes = _region_causes(context, regional_economy.region_id)

            for current in regional_economy.resources:
                capability_modifier = self._capability_modifier(
                    world, regional_economy.region_id, current.resource
                )
                if capability_modifier <= 0.0:
                    raise ValueError("capability modifier must be positive")
                outcome = _calculate_outcome(
                    current,
                    population,
                    region,
                    capability_modifier=capability_modifier,
                )
                resource_changes = _outcome_changes(
                    region_id=regional_economy.region_id,
                    current=current,
                    outcome=outcome,
                    causes=causes,
                )
                changes.extend(resource_changes)

                event_kind = _significant_event_kind(current, outcome)
                if event_kind is not None:
                    reason = _event_reason(region, current, outcome, event_kind)
                    events.append(
                        EventProposal(
                            kind=event_kind,
                            reason=reason,
                            subjects=(regional_economy.region_id,),
                            cause_event_ids=causes,
                            changes=resource_changes,
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
                        f"completed economy_regions={len(world.economy.regions)} "
                        f"changes={len(changes)} events={len(events)}"
                    ),
                ),
            ),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name:
            raise ValueError("economy reducer only accepts economy-owned changes")
        if world.economy is None:
            raise ValueError("economy change requires initialized economy state")
        if change.target is None or change.target.kind != "region":
            raise ValueError("economy changes require a region target")

        resource_kind, field = _parse_change_key(change.key)
        regions = list(world.economy.regions)
        region_index = next(
            (
                index
                for index, regional_economy in enumerate(regions)
                if regional_economy.region_id == change.target
            ),
            None,
        )
        if region_index is None:
            raise ValueError("economy change target is not an initialized economy region")

        regional_economy = regions[region_index]
        resources = list(regional_economy.resources)
        resource_index = next(
            (
                index
                for index, resource in enumerate(resources)
                if resource.resource == resource_kind
            ),
            None,
        )
        if resource_index is None:
            raise ValueError(f"resource {resource_kind!r} is not initialized for target region")

        current = resources[resource_index]
        value = round(float(getattr(current, field)) + change.delta, 6)
        if field == "shortage_severity":
            if not 0.0 <= value <= 1.0:
                raise ValueError("economy shortage severity must remain between 0 and 1")
        elif value < 0.0:
            raise ValueError(f"economy {field} cannot become negative")

        resources[resource_index] = current.model_copy(update={field: value})
        regions[region_index] = regional_economy.model_copy(update={"resources": tuple(resources)})
        economy = EconomyDomainState(regions=tuple(regions))
        return world.model_copy(update={"economy": economy})


def population_food_pressure_inputs(
    world: WorldState,
    *,
    events: Iterable[SimulationEvent] = (),
) -> tuple[SimulationInput, ...]:
    """Translate food shortage into region-scoped population-owned next-tick inputs.

    One input is produced per changed region so the materialized pressure event retains
    only that region's shortage or recovery causes. Economy supplies desired conditions
    through the population boundary and never reads or mutates population need internals.
    """
    if world.economy is None or world.population is None:
        return ()

    event_batch = tuple(events)
    inputs: list[SimulationInput] = []
    for regional_economy in world.economy.regions:
        try:
            food = regional_economy.resource("food")
        except KeyError:
            continue

        pressure = population_need_input(
            world,
            source="economy",
            kind="food-security-pressure",
            reason="Regional food availability changed population food security",
            targets=(
                PopulationNeedTarget(
                    region_id=regional_economy.region_id,
                    key=FOOD_SECURITY,
                    value=round(1.0 - food.shortage_severity, 6),
                    reason=(
                        f"food shortage severity {food.shortage_severity:.3f} "
                        "changed regional food security"
                    ),
                    cause_event_ids=_food_pressure_causes(event_batch, regional_economy.region_id),
                ),
            ),
        )
        if pressure is not None:
            inputs.append(pressure)

    return tuple(inputs)


def resource_change_key(resource: ResourceKind, field: str) -> str:
    if field not in RESOURCE_FIELDS:
        raise ValueError(f"unsupported economy resource field {field!r}")
    return f"economy.{resource}.{field}"


def _parse_change_key(key: str) -> tuple[ResourceKind, str]:
    parts = key.split(".")
    if len(parts) != 3 or parts[0] != "economy":
        raise ValueError(f"unsupported economy change key {key!r}")
    resource = parts[1]
    field = parts[2]
    if resource not in RESOURCE_KINDS or field not in RESOURCE_FIELDS:
        raise ValueError(f"unsupported economy change key {key!r}")
    return resource, field


def _neutral_capability_modifier(
    world: WorldState, region_id: EntityId, resource: ResourceKind
) -> float:
    del world, region_id, resource
    return 1.0


def _region_by_id(world: WorldState, region_id: EntityId) -> RegionState:
    assert world.geography is not None
    for region in world.geography.regions:
        if region.id == region_id:
            return region
    raise ValueError("economy region does not exist in geography")


def _calculate_outcome(
    current: ResourceEconomyState,
    population: RegionalPopulationState,
    region: RegionState,
    *,
    capability_modifier: float = 1.0,
    circumstance_modifier: float = 1.0,
) -> ResourceOutcome:
    if capability_modifier <= 0.0 or circumstance_modifier <= 0.0:
        raise ValueError("production modifiers must be positive")

    rule = RESOURCE_RULES[current.resource]
    labour = population.total * LABOUR_SHARE
    potential = region.resource_potential(rule.potential_key)
    capacity = _quantity(
        labour * rule.output_per_worker * potential * capability_modifier * circumstance_modifier
    )
    production = capacity
    demand = _quantity(population.total * rule.demand_per_capita)
    available = _quantity(current.stockpile + production)
    consumed = _quantity(min(available, demand))
    ending_stockpile = _quantity(max(0.0, available - consumed))
    surplus = _quantity(max(0.0, production - demand))
    deficit = _quantity(max(0.0, demand - consumed))
    shortage_severity = _quantity(deficit / demand) if demand > 0.0 else 0.0

    return ResourceOutcome(
        production_capacity=capacity,
        production=production,
        demand=demand,
        consumed=consumed,
        stockpile=ending_stockpile,
        surplus=surplus,
        deficit=deficit,
        shortage_severity=min(1.0, shortage_severity),
    )


def _outcome_changes(
    *,
    region_id: EntityId,
    current: ResourceEconomyState,
    outcome: ResourceOutcome,
    causes: tuple[UUID, ...],
) -> tuple[SimulationChange, ...]:
    changes: list[SimulationChange] = []
    for field in (
        "production_capacity",
        "production",
        "demand",
        "consumed",
        "stockpile",
        "surplus",
        "deficit",
        "shortage_severity",
    ):
        desired = float(getattr(outcome, field))
        existing = float(getattr(current, field))
        delta = round(desired - existing, 6)
        if not delta:
            continue
        changes.append(
            SimulationChange(
                source="economy",
                key=resource_change_key(current.resource, field),
                delta=delta,
                reason=f"recalculated {current.resource} {field}",
                target=region_id,
                cause_event_ids=causes,
            )
        )
    return tuple(changes)


def _region_causes(context: TickContext, region_id: EntityId) -> tuple[UUID, ...]:
    return tuple(
        event.id
        for event in context.prior_events
        if region_id in event.subjects
        or any(change.target == region_id for change in event.changes)
    )


def _food_pressure_causes(
    events: Iterable[SimulationEvent], region_id: EntityId
) -> tuple[UUID, ...]:
    shortage_key = resource_change_key("food", "shortage_severity")
    return tuple(
        event.id
        for event in events
        if event.source == "economy"
        and event.kind in {"resource-shortage", "resource-recovery"}
        and region_id in event.subjects
        and any(
            change.target == region_id and change.key == shortage_key for change in event.changes
        )
    )


def _significant_event_kind(current: ResourceEconomyState, outcome: ResourceOutcome) -> str | None:
    was_shortage = current.shortage_severity >= SIGNIFICANT_SHORTAGE_SEVERITY
    is_shortage = outcome.shortage_severity >= SIGNIFICANT_SHORTAGE_SEVERITY

    if is_shortage and (
        not was_shortage
        or abs(outcome.shortage_severity - current.shortage_severity) >= SIGNIFICANT_SEVERITY_CHANGE
    ):
        return "resource-shortage"
    if was_shortage and not is_shortage:
        return "resource-recovery"

    surplus_ratio = outcome.surplus / outcome.demand if outcome.demand > 0.0 else 0.0
    previous_surplus_ratio = current.surplus / current.demand if current.demand > 0.0 else 0.0
    if (
        surplus_ratio >= SIGNIFICANT_SURPLUS_RATIO
        and previous_surplus_ratio < SIGNIFICANT_SURPLUS_RATIO
    ):
        return "resource-surplus"
    return None


def _event_reason(
    region: RegionState,
    current: ResourceEconomyState,
    outcome: ResourceOutcome,
    event_kind: str,
) -> str:
    if event_kind == "resource-shortage":
        state = f"entered shortage severity={outcome.shortage_severity:.3f}"
    elif event_kind == "resource-recovery":
        state = "recovered from shortage"
    else:
        state = f"produced surplus={outcome.surplus:.3f}"
    return (
        f"{current.resource} in {region.key} {state}: production={outcome.production:.3f}, "
        f"demand={outcome.demand:.3f}, stockpile={outcome.stockpile:.3f}, "
        f"deficit={outcome.deficit:.3f}."
    )


def _quantity(value: float) -> float:
    return round(max(0.0, value), 6)
