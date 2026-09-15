"""Projection-only mapping from authoritative models to stable HTTP DTOs."""

from typing import Literal, cast

from cliova.api.v1.models import (
    AuthoritativeDirective,
    DirectiveTarget,
    EntityRef,
    FoodStatus,
    GovernanceCondition,
    HistoryEvent,
    PressureStatus,
    QueuedDirective,
    RegionStatus,
    SocietySummary,
    VersionMetadata,
    WorldListItem,
    WorldSummary,
)
from cliova.application.persistence import QueuedSimulationInput
from cliova.simulation.types import EntityId, SimulationEvent, WorldState


def entity_ref(value: EntityId) -> EntityRef:
    return EntityRef(kind=value.kind, id=value.value)


def _food_status(world: WorldState, region_id: EntityId) -> FoodStatus:
    food_security: float | None = None
    production: float | None = None
    demand: float | None = None
    stockpile: float | None = None
    deficit: float | None = None
    shortage: float | None = None

    if world.population is not None:
        try:
            food_security = world.population.region(region_id).needs.food_security
        except KeyError:
            pass
    if world.economy is not None:
        try:
            food = world.economy.region(region_id).resource("food")
            production = food.production
            demand = food.demand
            stockpile = food.stockpile
            deficit = food.deficit
            shortage = food.shortage_severity
        except KeyError:
            pass

    return FoodStatus(
        food_security=food_security,
        production=production,
        demand=demand,
        stockpile=stockpile,
        deficit=deficit,
        shortage_severity=shortage,
    )


def pressure_statuses(world: WorldState) -> tuple[PressureStatus, ...]:
    return tuple(
        PressureStatus(
            id=pressure.id,
            key=pressure.key,
            region_id=pressure.region_id.value,
            subject=(
                entity_ref(pressure.subject_id) if pressure.subject_id is not None else None
            ),
            intensity=pressure.intensity,
            milestone=pressure.milestone,
            age_ticks=pressure.age_ticks,
            cause_event_ids=pressure.cause_event_ids,
        )
        for pressure in world.pressures
        if pressure.milestone != "resolved"
    )


def society_summaries(world: WorldState) -> tuple[SocietySummary, ...]:
    summaries: list[SocietySummary] = []
    for state in sorted(world.governance, key=lambda item: item.subject_id.value.hex):
        population: int | None = None
        if world.population is not None:
            try:
                population = world.population.region(state.region_id).total
            except KeyError:
                pass
        summaries.append(
            SocietySummary(
                subject=entity_ref(state.subject_id),
                region_id=state.region_id.value,
                population=population,
                food=_food_status(world, state.region_id),
                governance=GovernanceCondition(
                    legitimacy=state.legitimacy,
                    execution_capacity=state.execution_capacity,
                    internal_resistance=state.internal_resistance,
                ),
            )
        )
    return tuple(summaries)


def region_statuses(world: WorldState) -> tuple[RegionStatus, ...]:
    if world.geography is None:
        return ()
    active_pressures = pressure_statuses(world)
    statuses: list[RegionStatus] = []
    for region in world.geography.regions:
        population: int | None = None
        if world.population is not None:
            try:
                population = world.population.region(region.id).total
            except KeyError:
                pass
        statuses.append(
            RegionStatus(
                id=region.id.value,
                key=region.key,
                terrain=region.terrain,
                biome=region.biome,
                habitability=region.habitability,
                water_access=region.water_access,
                climate_pressure=region.climate_pressure,
                population=population,
                food=_food_status(world, region.id),
                pressures=tuple(
                    pressure
                    for pressure in active_pressures
                    if pressure.region_id == region.id.value
                ),
            )
        )
    return tuple(statuses)


def world_list_item(world: WorldState) -> WorldListItem:
    population_total = (
        sum(region.total for region in world.population.regions)
        if world.population is not None
        else None
    )
    return WorldListItem(
        id=world.id.value,
        tick=world.time.tick,
        year=world.time.year,
        region_count=len(world.geography.regions) if world.geography is not None else 0,
        society_count=len(world.governance),
        population_total=population_total,
    )


def world_summary(world: WorldState) -> WorldSummary:
    population_total = (
        sum(region.total for region in world.population.regions)
        if world.population is not None
        else None
    )
    shortages: list[float] = []
    if world.economy is not None:
        for region in world.economy.regions:
            try:
                shortages.append(region.resource("food").shortage_severity)
            except KeyError:
                continue

    return WorldSummary(
        id=world.id.value,
        tick=world.time.tick,
        year=world.time.year,
        versions=VersionMetadata(
            world_schema_version=world.metadata.schema_version,
            simulation_version=world.metadata.simulation_version,
            rng_algorithm=world.metadata.rng_algorithm,
        ),
        region_count=len(world.geography.regions) if world.geography is not None else 0,
        population_total=population_total,
        food_shortage_severity=max(shortages) if shortages else None,
        societies=society_summaries(world),
        pressures=pressure_statuses(world),
    )


def history_event(event: SimulationEvent) -> HistoryEvent:
    return HistoryEvent(
        id=event.id,
        tick=event.time.tick,
        year=event.time.year,
        source=event.source,
        kind=event.kind,
        reason=event.reason,
        subjects=tuple(entity_ref(subject) for subject in event.subjects),
        cause_event_ids=event.cause_event_ids,
    )


def queued_directive(item: QueuedSimulationInput) -> QueuedDirective | None:
    submission = item.value.directive
    if submission is None or len(item.value.subjects) != 1:
        return None
    target = item.value.subjects[0]
    if target.kind not in {"society", "polity"}:
        return None
    return QueuedDirective(
        queue_id=item.queue_id,
        submitted_tick=item.submitted_tick,
        author=item.value.source,
        target=DirectiveTarget(
            kind=cast(Literal["society", "polity"], target.kind),
            id=target.value,
        ),
        intent=submission.intent,
        priority=submission.priority,
    )


def authoritative_directives(world: WorldState) -> tuple[AuthoritativeDirective, ...]:
    return tuple(
        AuthoritativeDirective(
            id=directive.id,
            author=directive.author,
            target=DirectiveTarget(
                kind=cast(Literal["society", "polity"], directive.target_subject.kind),
                id=directive.target_subject.value,
            ),
            intent=directive.intent,
            priority=directive.priority,
            submitted_tick=directive.submitted_tick,
            submission_event_id=directive.submission_event_id,
            status=directive.status,
            progress=directive.progress,
        )
        for directive in sorted(world.directives, key=lambda item: item.id.hex)
    )
