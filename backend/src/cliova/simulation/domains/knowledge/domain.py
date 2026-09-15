"""Deterministic practical learning; all writes use knowledge-owned changes."""

from collections.abc import Callable, Iterable
from uuid import UUID

from cliova.simulation.domains.knowledge.catalog import (
    CAPABILITIES,
    DEMAND_PRESSURE,
    LEARNING_RATE,
    PRACTICE_SATURATION,
)
from cliova.simulation.domains.knowledge.graph import validate_catalog
from cliova.simulation.domains.knowledge.types import (
    CapabilityDefinition,
    CapabilityRequirement,
    ExperienceGain,
    ExperienceRequirement,
    InnovationPressureSignal,
    RegionalLearningInput,
    ResourcePotentialRequirement,
)
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    CapabilityProgress,
    DomainResult,
    EntityId,
    EventProposal,
    ExperienceTrack,
    KnowledgeDomainState,
    ResourceKind,
    SimulationChange,
    SocietyKnowledgeState,
    WorldState,
)

LearningAdapter = Callable[[WorldState, TickContext], tuple[RegionalLearningInput, ...]]


def economy_learning_inputs(
    world: WorldState, context: TickContext
) -> tuple[RegionalLearningInput, ...]:
    """Read current-tick economy outputs. Schedule EconomyDomain before KnowledgeDomain."""
    if world.knowledge is None or world.economy is None:
        return ()
    inputs = []
    for society in world.knowledge.societies:
        for region_id in society.region_ids:
            try:
                economy = world.economy.region(region_id)
            except KeyError:
                continue
            pressures = []
            experience = []
            for resource, track in (("food", "cultivation"), ("metal_ore", "extraction")):
                outcome = next((r for r in economy.resources if r.resource == resource), None)
                if outcome is None:
                    continue
                causes = tuple(
                    event.id
                    for event in context.prior_events
                    if event.source == "economy"
                    and region_id in event.subjects
                    and any(c.key.startswith(f"economy.{resource}.") for c in event.changes)
                )
                magnitude = (
                    DEMAND_PRESSURE + (1 - DEMAND_PRESSURE) * outcome.shortage_severity
                    if outcome.demand > 0
                    else 0.0
                )
                pressures.append(
                    InnovationPressureSignal(
                        key=resource,
                        magnitude=round(magnitude, 6),
                        reason=(
                            f"{resource} demand={outcome.demand}, "
                            f"shortage={outcome.shortage_severity}"
                        ),
                        cause_event_ids=causes,
                    )
                )
                activity = outcome.production
                if resource == "food" and outcome.food_production:
                    cultivation = next(
                        (
                            method
                            for method in outcome.food_production
                            if method.method == "cultivation"
                        ),
                        None,
                    )
                    activity = cultivation.output if cultivation is not None else 0.0
                denominator = max(outcome.production, outcome.demand)
                experience.append(
                    ExperienceGain(
                        track=track,
                        amount=round(activity / denominator, 6) if denominator > 0 else 0,
                        cause_event_ids=causes,
                    )
                )
            inputs.append(
                RegionalLearningInput(
                    society_id=society.society_id,
                    region_id=region_id,
                    pressures=tuple(pressures),
                    experience=tuple(experience),
                )
            )
    return tuple(inputs)


def initialize_knowledge(
    world: WorldState,
    societies: Iterable[SocietyKnowledgeState],
) -> WorldState:
    """Explicit participation supplied by callers; never infer ownership from geography."""
    if world.knowledge is not None:
        raise ValueError("knowledge is already initialized")
    knowledge = KnowledgeDomainState(
        societies=tuple(
            sorted(
                societies,
                key=lambda s: s.society_id.value.hex,
            )
        )
    )
    return WorldState.model_validate({**world.model_dump(), "knowledge": knowledge})


class KnowledgeDomain:
    name = "knowledge"
    phase = TickPhase.KNOWLEDGE_SCENARIOS

    def __init__(
        self,
        definitions: Iterable[CapabilityDefinition] = CAPABILITIES,
        *,
        learning_adapter: LearningAdapter = economy_learning_inputs,
    ) -> None:
        self.catalog = validate_catalog(definitions)
        self.learning_adapter = learning_adapter

    def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
        del rng  # No random breakthrough roll in this first model.
        if world.knowledge is None:
            return DomainResult()
        inputs = self.learning_adapter(world, context)
        societies = {s.society_id: s for s in world.knowledge.societies}
        seen = set()
        for item in inputs:
            society = societies.get(item.society_id)
            if society is None or item.region_id not in society.region_ids:
                raise ValueError("learning input requires explicit society participation")
            identity = (item.society_id, item.region_id)
            if identity in seen:
                raise ValueError("duplicate regional learning input")
            seen.add(identity)
            for keys in (
                [signal.key for signal in item.pressures],
                [gain.track for gain in item.experience],
            ):
                if len(keys) != len(set(keys)):
                    raise ValueError("duplicate regional learning signal")
        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        for society in sorted(societies.values(), key=lambda s: s.society_id.value.hex):
            regional = sorted(
                (i for i in inputs if i.society_id == society.society_id),
                key=lambda i: i.region_id.value.hex,
            )
            tracks = sorted({gain.track for item in regional for gain in item.experience})
            for track in tracks:
                gains = [g for item in regional for g in item.experience if g.track == track]
                amount = round(sum(g.amount for g in gains), 6)
                if amount > 0:
                    changes.append(
                        SimulationChange(
                            source=self.name,
                            key=f"knowledge.experience.{track}",
                            delta=amount,
                            target=society.society_id,
                            reason=f"Practical activity accumulated in {track}",
                            cause_event_ids=_causes(c for g in gains for c in g.cause_event_ids),
                        )
                    )
            for definition in self.catalog:
                candidates = []
                for item in regional:
                    if not _eligible(world, society, definition, item.region_id):
                        continue
                    signal = next(
                        (p for p in item.pressures if p.key == definition.pressure_key), None
                    )
                    if signal is None or signal.magnitude == 0:
                        continue
                    practice = min(
                        1.0, society.practice(definition.practice_track) / PRACTICE_SATURATION
                    )
                    delta = round(LEARNING_RATE * signal.magnitude * practice, 6)
                    candidates.append((delta, item, signal))
                if not candidates:
                    continue
                # One improvement per society/capability/tick; use the strongest valid
                # local opportunity, never combine separate regions' prerequisites.
                delta, item, signal = max(candidates, key=lambda candidate: candidate[0])
                before = society.proficiency(definition.key)
                after = round(min(1.0, before + delta), 6)
                if after == before:
                    continue
                causes = _causes(
                    (
                        *signal.cause_event_ids,
                        *(
                            c
                            for gain in item.experience
                            if gain.track == definition.practice_track
                            for c in gain.cause_event_ids
                        ),
                    )
                )
                reason = (
                    f"{definition.key} proficiency {before:.6f} -> {after:.6f}; "
                    f"practice={society.practice(definition.practice_track):.6f}; "
                    f"region={item.region_id.value}; {signal.reason}; prerequisites satisfied"
                )
                change = SimulationChange(
                    source=self.name,
                    key=f"knowledge.proficiency.{definition.key}",
                    target=society.society_id,
                    delta=round(after - before, 6),
                    reason=reason,
                    cause_event_ids=causes,
                )
                changes.append(change)
                if before < definition.activation_threshold <= after:
                    events.append(
                        EventProposal(
                            kind="knowledge.capability_discovered",
                            reason=reason,
                            subjects=(society.society_id, item.region_id),
                            changes=(change,),
                            cause_event_ids=causes,
                        )
                    )
        return DomainResult(changes=tuple(changes), events=tuple(events))

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name or world.knowledge is None:
            raise ValueError("knowledge reducer requires initialized knowledge and owned changes")
        parts = change.key.split(".")
        if len(parts) != 3 or parts[0] != "knowledge":
            raise ValueError("unsupported knowledge change key")
        _, field, key = parts
        allowed = (
            {d.key for d in self.catalog}
            if field == "proficiency"
            else {d.practice_track for d in self.catalog}
            if field == "experience"
            else set()
        )
        if key not in allowed:
            raise ValueError("unsupported knowledge field or key")
        societies = list(world.knowledge.societies)
        index = next((i for i, s in enumerate(societies) if s.society_id == change.target), None)
        if index is None:
            raise ValueError("knowledge change requires an initialized society target")
        society = societies[index]
        update: dict[str, object]
        if field == "proficiency":
            values = {c.capability_key: c.proficiency for c in society.capabilities}
            values[key] = round(values.get(key, 0.0) + change.delta, 6)
            update = {
                "capabilities": tuple(
                    CapabilityProgress(capability_key=k, proficiency=v)
                    for k, v in sorted(values.items())
                )
            }
        else:
            values = {e.key: e.amount for e in society.experience}
            values[key] = round(values.get(key, 0.0) + change.delta, 6)
            update = {
                "experience": tuple(
                    ExperienceTrack(key=k, amount=v) for k, v in sorted(values.items())
                )
            }
        societies[index] = society.model_copy(update=update)
        return world.model_copy(
            update={"knowledge": KnowledgeDomainState(societies=tuple(societies))}
        )

    def capability_modifier(
        self,
        world: WorldState,
        region_id: EntityId,
        resource: ResourceKind,
        production_method: str | None = None,
    ) -> float:
        """Return a pure resource/method modifier for participating society knowledge."""
        if world.knowledge is None:
            return 1.0
        society = next((s for s in world.knowledge.societies if region_id in s.region_ids), None)
        if society is None:
            return 1.0
        bonus = sum(
            definition.effect.max_bonus * society.proficiency(definition.key)
            for definition in self.catalog
            if definition.effect.resource == resource
            and (
                definition.effect.production_method is None
                or definition.effect.production_method == production_method
            )
            and society.proficiency(definition.key) >= definition.activation_threshold
        )
        return round(1.0 + bonus, 6)


def _eligible(
    world: WorldState,
    society: SocietyKnowledgeState,
    definition: CapabilityDefinition,
    region_id: EntityId,
) -> bool:
    if world.geography is None:
        return False
    region = next((r for r in world.geography.regions if r.id == region_id), None)
    if region is None:
        raise ValueError("learning region does not exist")
    for requirement in definition.requirements:
        if isinstance(requirement, CapabilityRequirement):
            if society.proficiency(requirement.capability_key) < requirement.min_proficiency:
                return False
        elif isinstance(requirement, ExperienceRequirement):
            if society.practice(requirement.track) < requirement.minimum:
                return False
        elif isinstance(requirement, ResourcePotentialRequirement):
            if region.resource_potential(requirement.resource) < requirement.min_potential:
                return False
    return True


def _causes(ids: Iterable[UUID]) -> tuple[UUID, ...]:
    return tuple(sorted(set(ids), key=lambda value: value.hex))
