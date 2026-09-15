"""Authoritative settlement, seasonal-camp, and strategic-structure lifecycle."""

from collections.abc import Iterable
from typing import cast
from uuid import UUID

from cliova.simulation.domains.settlements.catalog import structure_definition
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    ChangeAttribute,
    DomainResult,
    EntityId,
    EntityKind,
    EventProposal,
    SettlementArchetype,
    SettlementDomainState,
    SettlementState,
    SettlementStatus,
    SimulationChange,
    SimulationDiagnostic,
    SimulationExplanation,
    SimulationInput,
    StructureState,
    StructureStatus,
    WorldState,
    entity_id,
)

_ESTABLISH_SETTLEMENT_KEY = "settlements.establish"
_SETTLEMENT_STATUS_KEY = "settlements.status"
_ESTABLISH_STRUCTURE_KEY = "structures.establish"
_STRUCTURE_STATUS_KEY = "structures.status"

_SETTLEMENT_TRANSITIONS: dict[SettlementStatus, frozenset[SettlementStatus]] = {
    "active": frozenset(("dormant", "abandoned", "destroyed")),
    "dormant": frozenset(("active", "abandoned", "destroyed")),
    "abandoned": frozenset(("active", "destroyed")),
    "destroyed": frozenset(),
}
_STRUCTURE_TRANSITIONS: dict[StructureStatus, frozenset[StructureStatus]] = {
    "active": frozenset(("damaged", "destroyed")),
    "damaged": frozenset(("active", "destroyed")),
    "destroyed": frozenset(),
}


class SettlementDomain:
    """Own existence and lifecycle state, but no economy/logistics/warfare formulas."""

    name = "settlements"
    phase = TickPhase.POPULATION

    def step(
        self,
        world: WorldState,
        context: TickContext,
        rng: RandomSource,
    ) -> DomainResult:
        del rng
        if not world.settlements.settlements:
            return DomainResult()

        relationships = {state.society_id: state for state in world.society_regions}
        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []

        for settlement in sorted(
            world.settlements.settlements, key=lambda state: state.id.value.hex
        ):
            if settlement.archetype not in {"seasonal_camp", "temporary_camp"}:
                continue
            subject = settlement.associated_subject
            if subject is None or subject.kind != "society":
                continue
            relationship = relationships.get(subject)
            if relationship is None or settlement.region_id == relationship.core_region_id:
                continue

            present = any(
                access.region_id == settlement.region_id for access in relationship.temporary_access
            )
            desired: SettlementStatus | None = None
            if present and settlement.status == "dormant":
                desired = "active"
            elif not present and settlement.status == "active":
                desired = "dormant"
            if desired is None:
                continue

            causes = _relevant_access_causes(context, subject, settlement.region_id)
            reason = (
                f"{settlement.name} returned to active use because temporary regional presence "
                f"exists in {settlement.region_id.value}."
                if desired == "active"
                else (
                    f"{settlement.name} became dormant because temporary regional presence "
                    f"ended in {settlement.region_id.value}."
                )
            )
            change = _settlement_status_change(
                settlement,
                desired,
                reason=reason,
                cause_event_ids=causes,
            )
            changes.append(change)
            events.append(
                EventProposal(
                    kind="camp-returned" if desired == "active" else "camp-dormant",
                    reason=reason,
                    subjects=(subject, settlement.region_id),
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
                        f"completed settlements={len(world.settlements.settlements)} "
                        f"camp_lifecycle_changes={len(changes)}"
                    ),
                ),
            ),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name:
            raise ValueError("settlement reducer accepts only settlement-owned changes")
        if change.key == _ESTABLISH_SETTLEMENT_KEY:
            return _apply_establish_settlement(world, change)
        if change.key == _SETTLEMENT_STATUS_KEY:
            return _apply_settlement_status(world, change)
        if change.key == _ESTABLISH_STRUCTURE_KEY:
            return _apply_establish_structure(world, change)
        if change.key == _STRUCTURE_STATUS_KEY:
            return _apply_structure_status(world, change)
        raise ValueError(f"unsupported settlement change key: {change.key}")


def initialize_settlements(
    world: WorldState,
    settlements: Iterable[SettlementState] = (),
    structures: Iterable[StructureState] = (),
) -> WorldState:
    """Initialize explicit authoritative settlement state without inventing history."""

    if world.settlements.settlements or world.settlements.structures:
        raise ValueError("settlement state is already initialized")
    state = SettlementDomainState(
        settlements=tuple(sorted(settlements, key=lambda item: item.id.value.hex)),
        structures=tuple(sorted(structures, key=lambda item: item.id.value.hex)),
    )
    return WorldState.model_validate({**world.model_dump(), "settlements": state.model_dump()})


def establish_settlement_input(
    world: WorldState,
    *,
    key: str,
    name: str,
    region_id: EntityId,
    archetype: SettlementArchetype,
    associated_subject: EntityId | None = None,
    population_estimate: int = 0,
    status: SettlementStatus = "active",
    established_year: int | None = None,
    reason: str | None = None,
) -> SimulationInput:
    """Create a deterministic authoritative settlement through the existing input boundary."""

    settlement_id = entity_id(world.id, "settlement", key)
    year = world.time.next_year().year if established_year is None else established_year
    message = reason or f"{name} was established as a {archetype.replace('_', ' ')}."
    attrs = [
        ChangeAttribute(key="settlement.key", value=key),
        ChangeAttribute(key="settlement.name", value=name),
        ChangeAttribute(key="settlement.region_id", value=str(region_id.value)),
        ChangeAttribute(key="settlement.established_year", value=year),
        ChangeAttribute(key="settlement.population_estimate", value=population_estimate),
        ChangeAttribute(key="settlement.archetype", value=archetype),
        ChangeAttribute(key="settlement.status", value=status),
    ]
    if associated_subject is not None:
        attrs.extend(
            (
                ChangeAttribute(key="settlement.subject_kind", value=associated_subject.kind),
                ChangeAttribute(key="settlement.subject_id", value=str(associated_subject.value)),
            )
        )
    change = SimulationChange(
        source="settlements",
        key=_ESTABLISH_SETTLEMENT_KEY,
        delta=1.0,
        reason=message,
        target=settlement_id,
        attributes=tuple(attrs),
    )
    subjects: tuple[EntityId, ...] = (region_id,)
    if associated_subject is not None:
        subjects = (*subjects, associated_subject)
    return SimulationInput(
        source="settlements",
        kind="camp-established" if archetype != "permanent" else "settlement-established",
        reason=message,
        subjects=subjects,
        changes=(change,),
    )


def establish_structure_input(
    world: WorldState,
    *,
    key: str,
    definition_id: str,
    settlement_id: EntityId,
    established_year: int | None = None,
    status: StructureStatus = "active",
    reason: str | None = None,
) -> SimulationInput:
    """Create one strategic structure instance; the catalog owns no numerical effects."""

    definition = structure_definition(definition_id)
    if settlement_id.kind != "settlement":
        raise ValueError("structure settlement_id must identify a settlement")
    structure_id = entity_id(world.id, "structure", key)
    year = world.time.next_year().year if established_year is None else established_year
    message = reason or f"{definition.display_name} was completed."
    change = SimulationChange(
        source="settlements",
        key=_ESTABLISH_STRUCTURE_KEY,
        delta=1.0,
        reason=message,
        target=structure_id,
        attributes=(
            ChangeAttribute(key="structure.key", value=key),
            ChangeAttribute(key="structure.definition_id", value=definition_id),
            ChangeAttribute(key="structure.settlement_id", value=str(settlement_id.value)),
            ChangeAttribute(key="structure.established_year", value=year),
            ChangeAttribute(key="structure.status", value=status),
        ),
    )
    return SimulationInput(
        source="settlements",
        kind="structure-completed",
        reason=message,
        subjects=(),
        changes=(change,),
    )


def settlement_status_input(
    settlement: SettlementState,
    status: SettlementStatus,
    *,
    reason: str,
    cause_event_ids: tuple[UUID, ...] = (),
) -> SimulationInput:
    """Request an explicit settlement lifecycle transition through SimulationInput."""

    change = _settlement_status_change(
        settlement, status, reason=reason, cause_event_ids=cause_event_ids
    )
    kind = {
        "active": "settlement-reactivated",
        "dormant": "camp-dormant",
        "abandoned": "settlement-abandoned",
        "destroyed": "settlement-destroyed",
    }[status]
    return SimulationInput(
        source="settlements",
        kind=kind,
        reason=reason,
        subjects=(
            (settlement.region_id, settlement.associated_subject)
            if settlement.associated_subject is not None
            else (settlement.region_id,)
        ),
        changes=(change,),
    )


def structure_status_input(
    structure: StructureState,
    status: StructureStatus,
    *,
    reason: str,
    cause_event_ids: tuple[UUID, ...] = (),
) -> SimulationInput:
    """Request an explicit strategic-structure lifecycle transition."""

    change = _structure_status_change(
        structure, status, reason=reason, cause_event_ids=cause_event_ids
    )
    kind = {
        "active": "structure-restored",
        "damaged": "structure-damaged",
        "destroyed": "structure-destroyed",
    }[status]
    return SimulationInput(
        source="settlements",
        kind=kind,
        reason=reason,
        subjects=(),
        changes=(change,),
    )


def _apply_establish_settlement(world: WorldState, change: SimulationChange) -> WorldState:
    if change.target is None or change.target.kind != "settlement":
        raise ValueError("settlement establishment requires a settlement target")
    values = _attributes(change)
    key = _string(values, "settlement.key")
    expected_id = entity_id(world.id, "settlement", key)
    if change.target != expected_id:
        raise ValueError("settlement target does not match deterministic settlement key")
    if any(state.id == change.target for state in world.settlements.settlements):
        raise ValueError("settlement already exists")

    region_id = EntityId(kind="region", value=UUID(_string(values, "settlement.region_id")))
    subject = _optional_subject(values)
    settlement = SettlementState(
        id=change.target,
        key=key,
        name=_string(values, "settlement.name"),
        region_id=region_id,
        associated_subject=subject,
        established_year=_integer(values, "settlement.established_year"),
        population_estimate=_integer(values, "settlement.population_estimate"),
        archetype=cast(SettlementArchetype, _string(values, "settlement.archetype")),
        status=cast(SettlementStatus, _string(values, "settlement.status")),
        cause_event_ids=change.cause_event_ids,
    )
    state = world.settlements.model_copy(
        update={
            "settlements": tuple(
                sorted(
                    (*world.settlements.settlements, settlement),
                    key=lambda item: item.id.value.hex,
                )
            )
        }
    )
    return _replace_state(world, state)


def _apply_settlement_status(world: WorldState, change: SimulationChange) -> WorldState:
    if change.target is None or change.target.kind != "settlement":
        raise ValueError("settlement lifecycle change requires a settlement target")
    settlements = list(world.settlements.settlements)
    index = _index_by_id(settlements, change.target)
    current = settlements[index]
    desired = cast(SettlementStatus, _string(_attributes(change), "settlement.status"))
    if desired == current.status:
        raise ValueError("settlement lifecycle transition must change status")
    if desired not in _SETTLEMENT_TRANSITIONS[current.status]:
        raise ValueError(f"invalid settlement transition: {current.status} -> {desired}")
    settlements[index] = current.model_copy(
        update={
            "status": desired,
            "cause_event_ids": tuple(
                dict.fromkeys((*current.cause_event_ids, *change.cause_event_ids))
            ),
        }
    )
    state = world.settlements.model_copy(update={"settlements": tuple(settlements)})
    return _replace_state(world, state)


def _apply_establish_structure(world: WorldState, change: SimulationChange) -> WorldState:
    if change.target is None or change.target.kind != "structure":
        raise ValueError("structure establishment requires a structure target")
    values = _attributes(change)
    key = _string(values, "structure.key")
    if change.target != entity_id(world.id, "structure", key):
        raise ValueError("structure target does not match deterministic structure key")
    if any(state.id == change.target for state in world.settlements.structures):
        raise ValueError("structure already exists")
    definition_id = _string(values, "structure.definition_id")
    structure_definition(definition_id)
    settlement_id = EntityId(
        kind="settlement", value=UUID(_string(values, "structure.settlement_id"))
    )
    if not any(state.id == settlement_id for state in world.settlements.settlements):
        raise ValueError("structure must reference an existing authoritative settlement")
    structure = StructureState(
        id=change.target,
        key=key,
        definition_id=definition_id,
        settlement_id=settlement_id,
        established_year=_integer(values, "structure.established_year"),
        status=cast(StructureStatus, _string(values, "structure.status")),
        cause_event_ids=change.cause_event_ids,
    )
    state = world.settlements.model_copy(
        update={
            "structures": tuple(
                sorted(
                    (*world.settlements.structures, structure),
                    key=lambda item: item.id.value.hex,
                )
            )
        }
    )
    return _replace_state(world, state)


def _apply_structure_status(world: WorldState, change: SimulationChange) -> WorldState:
    if change.target is None or change.target.kind != "structure":
        raise ValueError("structure lifecycle change requires a structure target")
    structures = list(world.settlements.structures)
    index = _index_by_id(structures, change.target)
    current = structures[index]
    desired = cast(StructureStatus, _string(_attributes(change), "structure.status"))
    if desired == current.status:
        raise ValueError("structure lifecycle transition must change status")
    if desired not in _STRUCTURE_TRANSITIONS[current.status]:
        raise ValueError(f"invalid structure transition: {current.status} -> {desired}")
    structures[index] = current.model_copy(
        update={
            "status": desired,
            "cause_event_ids": tuple(
                dict.fromkeys((*current.cause_event_ids, *change.cause_event_ids))
            ),
        }
    )
    state = world.settlements.model_copy(update={"structures": tuple(structures)})
    return _replace_state(world, state)


def _settlement_status_change(
    settlement: SettlementState,
    status: SettlementStatus,
    *,
    reason: str,
    cause_event_ids: tuple[UUID, ...],
) -> SimulationChange:
    return SimulationChange(
        source="settlements",
        key=_SETTLEMENT_STATUS_KEY,
        delta=0.0,
        reason=reason,
        target=settlement.id,
        cause_event_ids=cause_event_ids,
        attributes=(ChangeAttribute(key="settlement.status", value=status),),
    )


def _structure_status_change(
    structure: StructureState,
    status: StructureStatus,
    *,
    reason: str,
    cause_event_ids: tuple[UUID, ...],
) -> SimulationChange:
    return SimulationChange(
        source="settlements",
        key=_STRUCTURE_STATUS_KEY,
        delta=0.0,
        reason=reason,
        target=structure.id,
        cause_event_ids=cause_event_ids,
        attributes=(ChangeAttribute(key="structure.status", value=status),),
    )


def _replace_state(world: WorldState, state: SettlementDomainState) -> WorldState:
    return WorldState.model_validate({**world.model_dump(), "settlements": state.model_dump()})


def _attributes(change: SimulationChange) -> dict[str, str | int | float | bool]:
    return {attribute.key: attribute.value for attribute in change.attributes}


def _string(values: dict[str, str | int | float | bool], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"settlement change requires string attribute {key}")
    return value


def _integer(values: dict[str, str | int | float | bool], key: str) -> int:
    value = values.get(key)
    if type(value) is not int:
        raise ValueError(f"settlement change requires integer attribute {key}")
    return value


def _optional_subject(values: dict[str, str | int | float | bool]) -> EntityId | None:
    subject_id = values.get("settlement.subject_id")
    subject_kind = values.get("settlement.subject_kind")
    if subject_id is None and subject_kind is None:
        return None
    if not isinstance(subject_id, str) or subject_kind not in {"society", "polity"}:
        raise ValueError("settlement subject attributes must identify a society or polity")
    return EntityId(kind=cast(EntityKind, subject_kind), value=UUID(subject_id))


def _index_by_id(
    states: Iterable[SettlementState | StructureState], target: EntityId
) -> int:
    for index, state in enumerate(states):
        if state.id == target:
            return index
    raise ValueError(f"unknown settlement-domain target: {target.value}")


def _relevant_access_causes(
    context: TickContext,
    society_id: EntityId,
    region_id: EntityId,
) -> tuple[UUID, ...]:
    return tuple(
        event.id
        for event in context.prior_events
        if event.source == "seasonal_access"
        and society_id in event.subjects
        and region_id in event.subjects
    )
