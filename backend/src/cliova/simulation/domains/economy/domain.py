"""Deterministic regional production, consumption, reserves and shortages."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import UUID

from cliova.simulation.domains.economy.storage import (
    DEFAULT_FOOD_STORAGE_CONFIG,
    FoodStorageConfig,
    adjust_aggregate_food_reserves,
    balance_food_storage,
)
from cliova.simulation.domains.population import (
    FOOD_SECURITY,
    PopulationNeedTarget,
    population_need_input,
)
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    ChangeAttribute,
    DomainResult,
    EconomyDomainState,
    EntityId,
    EventProposal,
    FoodProductionMethod,
    FoodProductionMethodState,
    FoodReserveState,
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
FOOD_DEMAND_PER_CAPITA = 1.0
SIGNIFICANT_SHORTAGE_SEVERITY = 0.10
SIGNIFICANT_SURPLUS_RATIO = 0.10
SIGNIFICANT_SEVERITY_CHANGE = 0.25


@dataclass(frozen=True, slots=True)
class ResourceRule:
    potential_key: str
    demand_per_capita: float
    output_per_worker: float


@dataclass(frozen=True, slots=True)
class FoodProductionRule:
    method: FoodProductionMethod
    potential_key: str
    output_per_worker: float
    sustainable_yield_scale: float
    allocation_weight: float = 1.0


RESOURCE_RULES: dict[ResourceKind, ResourceRule] = {
    "timber": ResourceRule("timber", demand_per_capita=0.08, output_per_worker=0.50),
    "stone": ResourceRule("stone", demand_per_capita=0.05, output_per_worker=0.40),
    "metal_ore": ResourceRule("metal_ores", demand_per_capita=0.03, output_per_worker=0.25),
}

FOOD_PRODUCTION_RULES: tuple[FoodProductionRule, ...] = (
    FoodProductionRule(
        method="cultivation",
        potential_key="arable_land",
        output_per_worker=2.8,
        sustainable_yield_scale=900.0,
    ),
    FoodProductionRule(
        method="pastoralism",
        potential_key="grazing",
        output_per_worker=2.4,
        sustainable_yield_scale=500.0,
    ),
    FoodProductionRule(
        method="foraging",
        potential_key="wild_food",
        output_per_worker=1.8,
        sustainable_yield_scale=350.0,
    ),
    FoodProductionRule(
        method="fishing",
        potential_key="aquatic_food",
        output_per_worker=2.2,
        sustainable_yield_scale=450.0,
    ),
)
FOOD_PRODUCTION_METHODS: tuple[FoodProductionMethod, ...] = tuple(
    rule.method for rule in FOOD_PRODUCTION_RULES
)

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

CapabilityModifier = Callable[[WorldState, EntityId, ResourceKind, str | None], float]


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
    food_production: tuple[FoodProductionMethodState, ...] = ()
    food_reserves: FoodReserveState | None = None


class EconomyDomain:
    """Aggregate regional economy; production is constrained by people and geography."""

    name = "economy"
    phase = TickPhase.ECONOMY

    def __init__(
        self,
        capability_modifier: CapabilityModifier | None = None,
        *,
        food_storage_config: FoodStorageConfig = DEFAULT_FOOD_STORAGE_CONFIG,
    ) -> None:
        self._capability_modifier = capability_modifier or _neutral_capability_modifier
        self._food_storage_config = food_storage_config

    def step(
        self,
        world: WorldState,
        context: TickContext,
        rng: RandomSource,
    ) -> DomainResult:
        del rng  # The economy rules are deterministic without stochastic sampling.

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
                if current.resource == "food":
                    outcome = _calculate_food_outcome(
                        current,
                        population,
                        region,
                        world=world,
                        region_id=regional_economy.region_id,
                        capability_modifier=self._capability_modifier,
                        storage_config=self._food_storage_config,
                    )
                else:
                    capability_modifier = self._capability_modifier(
                        world, regional_economy.region_id, current.resource, None
                    )
                    if capability_modifier <= 0.0:
                        raise ValueError("capability modifier must be positive")
                    outcome = _calculate_resource_outcome(
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

                storage_event = _significant_storage_event(
                    current, outcome, self._food_storage_config
                )
                if storage_event:
                    stockpile_change = next(
                        (
                            change
                            for change in resource_changes
                            if change.key == resource_change_key("food", "stockpile")
                        ),
                        None,
                    )
                    if stockpile_change is not None:
                        reason = _storage_event_reason(region, outcome)
                        events.append(
                            EventProposal(
                                kind="food-storage-change",
                                reason=reason,
                                subjects=(regional_economy.region_id,),
                                cause_event_ids=causes,
                                changes=(stockpile_change,),
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

        update: dict[str, object] = {field: value}
        if resource_kind == "food" and field == "production" and change.attributes:
            update["food_production"] = _food_production_from_attributes(change.attributes)
        if resource_kind == "food" and field == "stockpile":
            reserves = (
                _food_reserves_from_attributes(change.attributes)
                if change.attributes
                else adjust_aggregate_food_reserves(current, new_stockpile=value)
            )
            if abs(reserves.total - value) > 1e-6:
                raise ValueError("food reserve classes must sum to aggregate stockpile")
            update["food_reserves"] = reserves
        resources[resource_index] = current.model_copy(update=update)
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
    world: WorldState,
    region_id: EntityId,
    resource: ResourceKind,
    production_method: str | None,
) -> float:
    del world, region_id, resource, production_method
    return 1.0


def _region_by_id(world: WorldState, region_id: EntityId) -> RegionState:
    assert world.geography is not None
    for region in world.geography.regions:
        if region.id == region_id:
            return region
    raise ValueError("economy region does not exist in geography")


def _calculate_food_outcome(
    current: ResourceEconomyState,
    population: RegionalPopulationState,
    region: RegionState,
    *,
    world: WorldState,
    region_id: EntityId,
    capability_modifier: CapabilityModifier,
    storage_config: FoodStorageConfig,
) -> ResourceOutcome:
    available_labour = _quantity(population.total * LABOUR_SHARE)
    allocations = _allocate_food_labour(region, available_labour)
    method_states: list[FoodProductionMethodState] = []

    for rule, allocated_labour in zip(FOOD_PRODUCTION_RULES, allocations, strict=True):
        modifier = capability_modifier(world, region_id, "food", rule.method)
        if modifier <= 0.0:
            raise ValueError("capability modifier must be positive")
        potential = region.resource_potential(rule.potential_key)
        labour_limited = _quantity(allocated_labour * rule.output_per_worker * modifier)
        sustainable_limit = _quantity(potential * rule.sustainable_yield_scale)
        output = _quantity(min(labour_limited, sustainable_limit))
        method_states.append(
            FoodProductionMethodState(
                method=rule.method,
                regional_potential=potential,
                allocated_labour=allocated_labour,
                capability_modifier=modifier,
                labour_limited_output=labour_limited,
                sustainable_limit=sustainable_limit,
                output=output,
            )
        )

    production_capacity = _quantity(sum(state.labour_limited_output for state in method_states))
    production = _quantity(sum(state.output for state in method_states))
    demand = _quantity(population.total * FOOD_DEMAND_PER_CAPITA)
    preservation_modifier = capability_modifier(world, region_id, "food", "preservation")
    if preservation_modifier <= 0.0:
        raise ValueError("preservation capability modifier must be positive")
    storage = balance_food_storage(
        current,
        production=production,
        demand=demand,
        preservation_modifier=preservation_modifier,
        config=storage_config,
    )
    return ResourceOutcome(
        production_capacity=production_capacity,
        production=production,
        demand=demand,
        consumed=storage.consumed,
        stockpile=storage.stockpile,
        surplus=_quantity(max(0.0, production - demand)),
        deficit=storage.deficit,
        shortage_severity=storage.shortage_severity,
        food_production=tuple(method_states),
        food_reserves=storage.reserves,
    )


def _allocate_food_labour(region: RegionState, available_labour: float) -> tuple[float, ...]:
    weights = tuple(
        region.resource_potential(rule.potential_key) * rule.allocation_weight
        for rule in FOOD_PRODUCTION_RULES
    )
    total_weight = sum(weights)
    if available_labour <= 0.0 or total_weight <= 0.0:
        return tuple(0.0 for _ in FOOD_PRODUCTION_RULES)

    allocations = [
        _quantity(available_labour * weight / total_weight) if weight > 0.0 else 0.0
        for weight in weights
    ]
    difference = round(available_labour - sum(allocations), 6)
    if difference:
        adjustable = max(index for index, weight in enumerate(weights) if weight > 0.0)
        allocations[adjustable] = _quantity(allocations[adjustable] + difference)
    if sum(allocations) > available_labour + 1e-6:
        raise RuntimeError("food labour allocation exceeded available labour")
    return tuple(allocations)


def _calculate_resource_outcome(
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
    demand = _quantity(population.total * rule.demand_per_capita)
    return _balance_resource(
        current,
        production_capacity=capacity,
        production=capacity,
        demand=demand,
    )


def _balance_resource(
    current: ResourceEconomyState,
    *,
    production_capacity: float,
    production: float,
    demand: float,
) -> ResourceOutcome:
    available = _quantity(current.stockpile + production)
    consumed = _quantity(min(available, demand))
    ending_stockpile = _quantity(max(0.0, available - consumed))
    surplus = _quantity(max(0.0, production - demand))
    deficit = _quantity(max(0.0, demand - consumed))
    shortage_severity = _quantity(deficit / demand) if demand > 0.0 else 0.0

    return ResourceOutcome(
        production_capacity=production_capacity,
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
        method_state_changed = (
            current.resource == "food"
            and field == "production"
            and current.food_production != outcome.food_production
        )
        reserve_state_changed = (
            current.resource == "food"
            and field == "stockpile"
            and current.food_reserves != outcome.food_reserves
        )
        if not delta and not method_state_changed and not reserve_state_changed:
            continue
        if current.resource == "food" and field == "production":
            attributes = _food_production_attributes(outcome.food_production)
        elif current.resource == "food" and field == "stockpile":
            if outcome.food_reserves is None:
                raise ValueError("food outcome requires explicit reserve state")
            attributes = _food_reserve_attributes(outcome.food_reserves)
        else:
            attributes = ()
        changes.append(
            SimulationChange(
                source="economy",
                key=resource_change_key(current.resource, field),
                delta=delta,
                reason=(
                    "recalculated food production and method constraints"
                    if method_state_changed and field == "production"
                    else "recalculated food reserve classes and storage losses"
                    if reserve_state_changed and field == "stockpile"
                    else f"recalculated {current.resource} {field}"
                ),
                target=region_id,
                cause_event_ids=causes,
                attributes=attributes,
            )
        )
    return tuple(changes)


def _food_production_attributes(
    states: tuple[FoodProductionMethodState, ...],
) -> tuple[ChangeAttribute, ...]:
    attributes: list[ChangeAttribute] = []
    for state in states:
        prefix = f"food_method.{state.method}"
        for field in (
            "regional_potential",
            "allocated_labour",
            "capability_modifier",
            "labour_limited_output",
            "sustainable_limit",
            "output",
        ):
            attributes.append(
                ChangeAttribute(key=f"{prefix}.{field}", value=float(getattr(state, field)))
            )
    return tuple(attributes)


def _food_production_from_attributes(
    attributes: tuple[ChangeAttribute, ...],
) -> tuple[FoodProductionMethodState, ...]:
    values = {attribute.key: attribute.value for attribute in attributes}
    states: list[FoodProductionMethodState] = []
    fields = (
        "regional_potential",
        "allocated_labour",
        "capability_modifier",
        "labour_limited_output",
        "sustainable_limit",
        "output",
    )
    for method in FOOD_PRODUCTION_METHODS:
        prefix = f"food_method.{method}"
        missing = [field for field in fields if f"{prefix}.{field}" not in values]
        if missing:
            raise ValueError(f"food production change missing {method} fields: {missing}")
        states.append(
            FoodProductionMethodState(
                method=method,
                regional_potential=float(values[f"{prefix}.regional_potential"]),
                allocated_labour=float(values[f"{prefix}.allocated_labour"]),
                capability_modifier=float(values[f"{prefix}.capability_modifier"]),
                labour_limited_output=float(values[f"{prefix}.labour_limited_output"]),
                sustainable_limit=float(values[f"{prefix}.sustainable_limit"]),
                output=float(values[f"{prefix}.output"]),
            )
        )
    return tuple(states)


def _food_reserve_attributes(state: FoodReserveState) -> tuple[ChangeAttribute, ...]:
    return tuple(
        ChangeAttribute(key=f"food_reserve.{field}", value=float(getattr(state, field)))
        for field in (
            "perishable",
            "durable",
            "consumed_from_production",
            "consumed_from_perishable",
            "consumed_from_durable",
            "preserved",
            "perishable_spoilage",
            "durable_spoilage",
            "preservation_modifier",
        )
    )


def _food_reserves_from_attributes(
    attributes: tuple[ChangeAttribute, ...],
) -> FoodReserveState:
    values = {attribute.key: attribute.value for attribute in attributes}
    fields = (
        "perishable",
        "durable",
        "consumed_from_production",
        "consumed_from_perishable",
        "consumed_from_durable",
        "preserved",
        "perishable_spoilage",
        "durable_spoilage",
        "preservation_modifier",
    )
    missing = [field for field in fields if f"food_reserve.{field}" not in values]
    if missing:
        raise ValueError(f"food reserve change missing fields: {missing}")
    return FoodReserveState(**{field: float(values[f"food_reserve.{field}"]) for field in fields})


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


def _significant_storage_event(
    current: ResourceEconomyState,
    outcome: ResourceOutcome,
    config: FoodStorageConfig,
) -> bool:
    if current.resource != "food" or outcome.food_reserves is None or outcome.demand <= 0.0:
        return False
    previous = current.food_reserves or FoodReserveState()
    current_loss = outcome.food_reserves.spoilage_loss / outcome.demand
    previous_loss = previous.spoilage_loss / current.demand if current.demand > 0.0 else 0.0
    current_preserved = outcome.food_reserves.preserved / outcome.demand
    previous_preserved = previous.preserved / current.demand if current.demand > 0.0 else 0.0

    def changed(now: float, before: float) -> bool:
        return now >= config.significant_flow_ratio and (
            before < config.significant_flow_ratio
            or abs(now - before) >= config.significant_flow_change_ratio
        )

    return changed(current_loss, previous_loss) or changed(current_preserved, previous_preserved)


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
    reason = (
        f"{current.resource} in {region.key} {state}: production={outcome.production:.3f}, "
        f"demand={outcome.demand:.3f}, stockpile={outcome.stockpile:.3f}, "
        f"deficit={outcome.deficit:.3f}."
    )
    if current.resource == "food" and outcome.food_production:
        methods = "; ".join(
            (
                f"{method.method} labour={method.allocated_labour:.3f} "
                f"labour_limit={method.labour_limited_output:.3f} "
                f"sustainable_limit={method.sustainable_limit:.3f} "
                f"output={method.output:.3f}"
            )
            for method in outcome.food_production
        )
        reason = f"{reason} Methods: {methods}."
    if outcome.food_reserves is not None:
        reason = (
            f"{reason} Reserves: perishable={outcome.food_reserves.perishable:.3f}, "
            f"durable={outcome.food_reserves.durable:.3f}, "
            f"preserved={outcome.food_reserves.preserved:.3f}, "
            f"spoilage={outcome.food_reserves.spoilage_loss:.3f}."
        )
    return reason


def _storage_event_reason(region: RegionState, outcome: ResourceOutcome) -> str:
    assert outcome.food_reserves is not None
    reserves = outcome.food_reserves
    return (
        f"Food storage changed materially in {region.key}: preserved={reserves.preserved:.3f}, "
        f"perishable_spoilage={reserves.perishable_spoilage:.3f}, "
        f"durable_spoilage={reserves.durable_spoilage:.3f}, "
        f"perishable_reserve={reserves.perishable:.3f}, durable_reserve={reserves.durable:.3f}, "
        f"preservation_modifier={reserves.preservation_modifier:.3f}."
    )


def _quantity(value: float) -> float:
    return round(max(0.0, value), 6)
