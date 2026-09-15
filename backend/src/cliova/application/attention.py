"""Application contracts for non-blocking player attention and future decision opportunities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from cliova.application.persistence import QueuedSimulationInput
from cliova.simulation.types import (
    EntityId,
    SimulationEvent,
    SimulationInput,
    TickResult,
    WorldState,
)


class AttentionPriority(StrEnum):
    INFORMATIONAL = "informational"
    IMPORTANT = "important"
    URGENT = "urgent"


class DecisionOpportunityStatus(StrEnum):
    OPEN = "open"
    RESPONDED = "responded"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class AttentionItem:
    """Player-facing relevance derived from authoritative facts, never new simulation truth."""

    id: UUID
    world_id: UUID
    target_subject: EntityId | None
    created_tick: int
    created_year: int
    category: str
    priority: AttentionPriority
    context: str
    related_event_ids: tuple[UUID, ...]
    related_subjects: tuple[EntityId, ...]


@dataclass(frozen=True, slots=True)
class DecisionOpportunity:
    """Invitation to submit future intent; it is never an approval gate for world progress."""

    id: UUID
    world_id: UUID
    target_subject: EntityId
    created_tick: int
    created_year: int
    category: str
    context: str
    related_event_ids: tuple[UUID, ...]
    related_subjects: tuple[EntityId, ...]
    earliest_effect_tick: int
    expires_at_tick: int | None
    default_behavior: str
    response_intent: str
    status: DecisionOpportunityStatus
    response_queue_id: int | None = None
    response_submitted_tick: int | None = None
    response_directive_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AttentionProjection:
    attention_items: tuple[AttentionItem, ...] = ()
    decision_opportunities: tuple[DecisionOpportunity, ...] = ()


class DecisionResponseError(ValueError):
    """Stable application validation failure for a decision-opportunity response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AttentionProducer(Protocol):
    """Translate authoritative tick facts into player-facing relevance without UI knowledge."""

    def produce(self, before: WorldState, result: TickResult) -> AttentionProjection: ...


class AttentionRepository(Protocol):
    """Persistence boundary for queryable attention and future-input responses."""

    def list_attention_items(self, world_id: UUID) -> tuple[AttentionItem, ...]: ...

    def list_decision_opportunities(self, world_id: UUID) -> tuple[DecisionOpportunity, ...]: ...

    def queue_decision_response(
        self,
        world_id: UUID,
        *,
        opportunity_id: UUID,
        value: SimulationInput,
    ) -> QueuedSimulationInput: ...


class FoodShortageAttentionProducer:
    """Small #64 integration example using existing economy history facts only."""

    def produce(self, before: WorldState, result: TickResult) -> AttentionProjection:
        del before
        attention: list[AttentionItem] = []
        decisions: list[DecisionOpportunity] = []
        world = result.world

        governance_by_region: dict[EntityId, list[EntityId]] = {}
        for state in sorted(world.governance, key=lambda item: item.subject_id.value.hex):
            governance_by_region.setdefault(state.region_id, []).append(state.subject_id)

        for event in result.events:
            if not _is_food_availability_event(event):
                continue
            region = next(
                (subject for subject in event.subjects if subject.kind == "region"),
                None,
            )
            if region is None:
                continue
            targets: tuple[EntityId | None, ...] = tuple(governance_by_region.get(region, ())) or (
                None,
            )
            category = "food-shortage" if event.kind == "resource-shortage" else "food-recovery"
            for target in targets:
                attention.append(
                    AttentionItem(
                        id=_attention_id(world.id.value, event.id, category, target),
                        world_id=world.id.value,
                        target_subject=target,
                        created_tick=event.time.tick,
                        created_year=event.time.year,
                        category=category,
                        priority=(
                            AttentionPriority.IMPORTANT
                            if event.kind == "resource-shortage"
                            else AttentionPriority.INFORMATIONAL
                        ),
                        context=event.reason,
                        related_event_ids=(event.id,),
                        related_subjects=event.subjects,
                    )
                )
                if event.kind != "resource-shortage" or target is None:
                    continue
                decisions.append(
                    DecisionOpportunity(
                        id=_decision_id(
                            world.id.value,
                            event.id,
                            "food-shortage-priority",
                            target,
                        ),
                        world_id=world.id.value,
                        target_subject=target,
                        created_tick=event.time.tick,
                        created_year=event.time.year,
                        category="food-shortage-priority",
                        context=event.reason,
                        related_event_ids=(event.id,),
                        related_subjects=event.subjects,
                        earliest_effect_tick=event.time.tick + 1,
                        expires_at_tick=None,
                        default_behavior=(
                            "No new directive is submitted; existing directives and "
                            "standing policy continue unchanged."
                        ),
                        response_intent="strengthen_food_reserves",
                        status=DecisionOpportunityStatus.OPEN,
                    )
                )

        return AttentionProjection(
            attention_items=tuple(attention),
            decision_opportunities=tuple(decisions),
        )


def _is_food_availability_event(event: SimulationEvent) -> bool:
    if event.source != "economy" or event.kind not in {
        "resource-shortage",
        "resource-recovery",
    }:
        return False
    return any(change.key == "economy.food.shortage_severity" for change in event.changes)


def _attention_id(
    world_id: UUID,
    event_id: UUID,
    category: str,
    target: EntityId | None,
) -> UUID:
    return uuid5(world_id, _identity_material("attention", event_id, category, target))


def _decision_id(
    world_id: UUID,
    event_id: UUID,
    category: str,
    target: EntityId,
) -> UUID:
    return uuid5(world_id, _identity_material("decision", event_id, category, target))


def _identity_material(
    kind: str,
    event_id: UUID,
    category: str,
    target: EntityId | None,
) -> str:
    target_value = None if target is None else [target.kind, str(target.value)]
    return json.dumps(
        [f"cliova.{kind}.v1", str(event_id), category, target_value],
        ensure_ascii=True,
        separators=(",", ":"),
    )
