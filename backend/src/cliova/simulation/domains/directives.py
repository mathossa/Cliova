"""Deterministic player directives resolved through governance and domain-owned effects."""

from collections.abc import Callable
from uuid import UUID

from cliova.simulation.domains.economy import EconomyDomain
from cliova.simulation.domains.politics import execution_strength
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    ChangeAttribute,
    DirectiveIntent,
    DirectivePriority,
    DirectiveState,
    DirectiveSubmission,
    DomainResult,
    EntityId,
    EventProposal,
    ResourceKind,
    SimulationChange,
    SimulationExplanation,
    SimulationInput,
    WorldState,
)

BASE_PROGRESS_PER_TICK = 0.4
MIN_EXECUTION_STRENGTH = 0.2
ACCEPTED_EXECUTION_STRENGTH = 0.75
ACCEPTED_ECONOMIC_FEASIBILITY = 0.75
RESISTANCE_THRESHOLD = 0.65
MAX_FOOD_PRODUCTION_BOOST = 0.25
_PRIORITY_ORDER: dict[DirectivePriority, int] = {"low": 0, "normal": 1, "high": 2}
_TERMINAL_STATUSES = {"failed", "completed"}
_DIRECTIVE_CHANGE_KEY = "directives.state"

CapabilityModifier = Callable[[WorldState, EntityId, ResourceKind, str | None], float]


def directive_input(
    *,
    author: str,
    target_subject: EntityId,
    intent: DirectiveIntent = "strengthen_food_reserves",
    priority: DirectivePriority = "normal",
) -> SimulationInput:
    """Create queued player intent without directly changing authoritative state."""
    if target_subject.kind not in {"society", "polity"}:
        raise ValueError("directive target must identify a society or polity")
    return SimulationInput(
        source=author,
        kind="directive-submitted",
        reason=f"Requested {intent} with {priority} priority",
        subjects=(target_subject,),
        directive=DirectiveSubmission(intent=intent, priority=priority),
    )


def directive_economy_modifier(
    world: WorldState,
    region_id: EntityId,
    resource: ResourceKind,
    production_method: str | None = None,
) -> float:
    """Return the implemented food-priority effect; economy still owns all food changes."""
    del production_method  # This directive intentionally applies across food-production methods.
    if resource != "food":
        return 1.0

    implemented = 0.0
    governance_by_subject = {state.subject_id: state for state in world.governance}
    for directive in world.directives:
        if directive.intent != "strengthen_food_reserves" or directive.status == "failed":
            continue
        governance = governance_by_subject.get(directive.target_subject)
        if governance is None or governance.region_id != region_id:
            continue
        implemented = max(implemented, directive.progress)
    return round(1.0 + MAX_FOOD_PRODUCTION_BOOST * implemented, 6)


class DirectiveAwareEconomyDomain(EconomyDomain):
    """Thin adapter composing #9 circumstance effects with #7/#11 production modifiers."""

    def __init__(self, capability_modifier: CapabilityModifier | None = None) -> None:
        def combined(
            world: WorldState,
            region_id: EntityId,
            resource: ResourceKind,
            production_method: str | None,
        ) -> float:
            capability = (
                capability_modifier(world, region_id, resource, production_method)
                if capability_modifier is not None
                else 1.0
            )
            return capability * directive_economy_modifier(
                world, region_id, resource, production_method
            )

        super().__init__(capability_modifier=combined)


class DirectiveDomain:
    """Persist and advance indirect directives during the governance phase."""

    name = "directives"
    phase = TickPhase.GOVERNANCE

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
        del rng
        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []
        new_ids: set[UUID] = set()

        input_events = context.prior_events[: len(context.queued_inputs)]
        if len(input_events) != len(context.queued_inputs):
            raise ValueError("queued inputs must have materialized ingest events")

        for queued, input_event in zip(context.queued_inputs, input_events, strict=True):
            if queued.directive is None:
                continue
            if len(queued.subjects) != 1:
                raise ValueError("directive input requires exactly one target subject")
            target = queued.subjects[0]
            if target.kind not in {"society", "polity"}:
                raise ValueError("directive input target must identify a society or polity")
            if (
                input_event.source != queued.source
                or input_event.kind != queued.kind
                or input_event.subjects != queued.subjects
            ):
                raise ValueError("directive input does not match its ingest event")

            state = DirectiveState(
                id=input_event.id,
                author=queued.source,
                target_subject=target,
                intent=queued.directive.intent,
                priority=queued.directive.priority,
                submitted_tick=context.time.tick,
                submission_event_id=input_event.id,
                status="queued",
                progress=0.0,
            )
            reason = (
                f"Directive queued: {state.intent} for {state.target_subject.kind} "
                f"{state.target_subject.value}."
            )
            change = _state_change(state, previous=None, reason=reason, causes=(input_event.id,))
            changes.append(change)
            events.append(
                EventProposal(
                    kind="directive-queued",
                    reason=reason,
                    subjects=(state.target_subject,),
                    cause_event_ids=(input_event.id,),
                    changes=(change,),
                )
            )
            explanations.append(
                SimulationExplanation(
                    source=self.name,
                    message=reason,
                    cause_event_ids=(input_event.id,),
                )
            )
            new_ids.add(state.id)

        active = sorted(
            (
                directive
                for directive in world.directives
                if directive.id not in new_ids and directive.status not in _TERMINAL_STATUSES
            ),
            key=lambda directive: (
                -_PRIORITY_ORDER[directive.priority],
                directive.submitted_tick,
                directive.id.hex,
            ),
        )
        for directive in active:
            updated, reason, event_kind, causes = _advance_directive(world, directive, context)
            change = _state_change(updated, previous=directive, reason=reason, causes=causes)
            changes.append(change)
            events.append(
                EventProposal(
                    kind=event_kind,
                    reason=reason,
                    subjects=(directive.target_subject,),
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
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name or change.key != _DIRECTIVE_CHANGE_KEY:
            raise ValueError("directive reducer only accepts directive state changes")
        if change.target is None or change.target.kind not in {"society", "polity"}:
            raise ValueError("directive state change requires a society/polity target")

        state = _state_from_change(change)
        if state.target_subject != change.target:
            raise ValueError("directive change target does not match directive state")

        directives = list(world.directives)
        index = next(
            (index for index, directive in enumerate(directives) if directive.id == state.id),
            None,
        )
        if index is None:
            if state.status != "queued" or state.progress != 0.0 or change.delta != 0.0:
                raise ValueError("new directives must enter in queued state with zero progress")
            directives.append(state)
        else:
            current = directives[index]
            if current.status in _TERMINAL_STATUSES and state != current:
                raise ValueError("terminal directives cannot transition")
            if (
                state.author != current.author
                or state.target_subject != current.target_subject
                or state.intent != current.intent
                or state.priority != current.priority
                or state.submitted_tick != current.submitted_tick
                or state.submission_event_id != current.submission_event_id
            ):
                raise ValueError("directive identity fields are immutable")
            if state.progress < current.progress:
                raise ValueError("directive progress cannot decrease")
            expected_delta = round(state.progress - current.progress, 6)
            if round(change.delta, 6) != expected_delta:
                raise ValueError("directive progress delta does not match replacement state")
            directives[index] = state

        return world.model_copy(update={"directives": tuple(directives)})


def _advance_directive(
    world: WorldState, directive: DirectiveState, context: TickContext
) -> tuple[DirectiveState, str, str, tuple[UUID, ...]]:
    governance = next(
        (state for state in world.governance if state.subject_id == directive.target_subject),
        None,
    )
    if governance is None:
        reason = "Directive failed: the target has no authoritative governance state."
        updated = directive.model_copy(update={"status": "failed"})
        return updated, reason, "directive-failed", (directive.submission_event_id,)

    causes = _relevant_causes(context, directive, governance.region_id)
    strength = execution_strength(governance)
    feasibility = _food_economic_feasibility(world, governance.region_id)

    if governance.internal_resistance >= RESISTANCE_THRESHOLD:
        reason = (
            "Directive resisted: internal resistance "
            f"{governance.internal_resistance:.3f} limits execution strength to {strength:.3f}."
        )
        return (
            directive.model_copy(update={"status": "resisted"}),
            reason,
            "directive-resisted",
            causes,
        )

    if strength < MIN_EXECUTION_STRENGTH:
        reason = (
            f"Directive delayed: execution strength {strength:.3f} is below the "
            f"minimum {MIN_EXECUTION_STRENGTH:.3f}."
        )
        return (
            directive.model_copy(update={"status": "delayed"}),
            reason,
            "directive-delayed",
            causes,
        )

    if feasibility <= 0.0:
        reason = "Directive delayed: no current food-production capacity is available."
        return (
            directive.model_copy(update={"status": "delayed"}),
            reason,
            "directive-delayed",
            causes,
        )

    gain = round(BASE_PROGRESS_PER_TICK * strength * feasibility, 6)
    progress = round(min(1.0, directive.progress + gain), 6)
    if progress >= 1.0:
        status = "completed"
        event_kind = "directive-completed"
        reason = (
            f"Directive completed: execution strength {strength:.3f} and economic feasibility "
            f"{feasibility:.3f} advanced implementation to 1.000."
        )
    elif strength >= ACCEPTED_EXECUTION_STRENGTH and feasibility >= ACCEPTED_ECONOMIC_FEASIBILITY:
        status = "accepted"
        event_kind = "directive-accepted"
        reason = (
            f"Directive accepted and in progress: execution strength {strength:.3f} and economic "
            f"feasibility {feasibility:.3f} advanced implementation from "
            f"{directive.progress:.3f} to {progress:.3f}."
        )
    else:
        status = "partial"
        event_kind = "directive-partial"
        reason = (
            f"Directive partially executed: execution strength {strength:.3f} and economic "
            f"feasibility {feasibility:.3f} advanced implementation from "
            f"{directive.progress:.3f} to {progress:.3f}."
        )

    return (
        directive.model_copy(update={"status": status, "progress": progress}),
        reason,
        event_kind,
        causes,
    )


def _food_economic_feasibility(world: WorldState, region_id: EntityId) -> float:
    if world.economy is None:
        return 0.0
    try:
        food = world.economy.region(region_id).resource("food")
    except KeyError:
        return 0.0
    if food.demand <= 0.0:
        return 1.0
    if food.production_capacity <= 0.0:
        return 0.0
    return round(min(1.0, food.production_capacity / food.demand), 6)


def _relevant_causes(
    context: TickContext, directive: DirectiveState, region_id: EntityId
) -> tuple[UUID, ...]:
    cause_ids = [directive.submission_event_id]
    for event in context.prior_events:
        if event.source not in {"economy", "governance"}:
            continue
        if (
            directive.target_subject in event.subjects
            or region_id in event.subjects
            or any(
                change.target in {directive.target_subject, region_id} for change in event.changes
            )
        ):
            cause_ids.append(event.id)
    return tuple(dict.fromkeys(cause_ids))


def _state_change(
    state: DirectiveState,
    *,
    previous: DirectiveState | None,
    reason: str,
    causes: tuple[UUID, ...],
) -> SimulationChange:
    delta = 0.0 if previous is None else round(state.progress - previous.progress, 6)
    return SimulationChange(
        source="directives",
        key=_DIRECTIVE_CHANGE_KEY,
        delta=delta,
        reason=reason,
        target=state.target_subject,
        cause_event_ids=causes,
        attributes=(
            ChangeAttribute(key="id", value=str(state.id)),
            ChangeAttribute(key="author", value=state.author),
            ChangeAttribute(key="intent", value=state.intent),
            ChangeAttribute(key="priority", value=state.priority),
            ChangeAttribute(key="submitted_tick", value=state.submitted_tick),
            ChangeAttribute(key="submission_event_id", value=str(state.submission_event_id)),
            ChangeAttribute(key="status", value=state.status),
            ChangeAttribute(key="progress", value=state.progress),
        ),
    )


def _state_from_change(change: SimulationChange) -> DirectiveState:
    attributes = {attribute.key: attribute.value for attribute in change.attributes}
    required = {
        "id",
        "author",
        "intent",
        "priority",
        "submitted_tick",
        "submission_event_id",
        "status",
        "progress",
    }
    if set(attributes) != required:
        raise ValueError("directive state change requires the complete directive attribute set")
    assert change.target is not None
    return DirectiveState.model_validate(
        {
            "id": UUID(str(attributes["id"])),
            "author": str(attributes["author"]),
            "target_subject": change.target,
            "intent": str(attributes["intent"]),
            "priority": str(attributes["priority"]),
            "submitted_tick": int(attributes["submitted_tick"]),
            "submission_event_id": UUID(str(attributes["submission_event_id"])),
            "status": str(attributes["status"]),
            "progress": float(attributes["progress"]),
        }
    )
