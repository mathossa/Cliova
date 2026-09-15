"""Deterministic society access to temporary regional subsistence opportunity."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from cliova.simulation.domains.knowledge.catalog import (
    MOBILE_PASTORALISM_ACTIVATION_THRESHOLD,
    MOBILE_PASTORALISM_KEY,
)
from cliova.simulation.engine import TickContext, TickPhase
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    ChangeAttribute,
    DomainResult,
    EntityId,
    EventProposal,
    FoodProductionMethod,
    SeasonalSubsistenceAccessState,
    SimulationChange,
    SimulationDiagnostic,
    SimulationExplanation,
    SocietyRegionRelationshipState,
    WorldState,
)

SEASONAL_PASTORAL_ACCESS_SHARE = 0.35
_ACCESS_CHANGE_KEY = "society_regions.temporary_access"


@dataclass(frozen=True, slots=True)
class _AccessCandidate:
    region_id: EntityId
    grazing_potential: float
    travel_cost: float
    access_share: float

    @property
    def score(self) -> float:
        return self.grazing_potential * self.access_share / self.travel_cost


def initialize_society_region_relationships(
    world: WorldState,
    relationships: Iterable[SocietyRegionRelationshipState],
) -> WorldState:
    """Initialize explicit permanent society cores without inferring ownership or migration."""
    if world.society_regions:
        raise ValueError("society-region relationships are already initialized")
    states = tuple(sorted(relationships, key=lambda state: state.society_id.value.hex))
    return WorldState.model_validate({**world.model_dump(), "society_regions": states})


class SeasonalSubsistenceAccessDomain:
    """Allocate bounded direct-adjacent temporary access before economy production."""

    name = "seasonal_access"
    phase = TickPhase.POPULATION

    def step(
        self,
        world: WorldState,
        context: TickContext,
        rng: RandomSource,
    ) -> DomainResult:
        del rng
        if not world.society_regions:
            return DomainResult()
        if world.geography is None:
            raise ValueError("seasonal access requires geography")

        remaining_share = {region.id: 1.0 for region in world.geography.regions}
        changes: list[SimulationChange] = []
        events: list[EventProposal] = []
        explanations: list[SimulationExplanation] = []

        for relationship in sorted(
            world.society_regions, key=lambda state: state.society_id.value.hex
        ):
            desired = _desired_access(world, relationship, remaining_share)
            _reserve(desired, remaining_share)
            if desired == relationship.temporary_access:
                continue

            causes = _relevant_causes(context, relationship.society_id)
            reason = _access_reason(world, relationship, desired)
            change = _access_change(relationship, desired, reason=reason, causes=causes)
            changes.append(change)

            subjects = (
                relationship.society_id,
                relationship.core_region_id,
                *tuple(access.region_id for access in (desired or relationship.temporary_access)),
            )
            event_kind = (
                "seasonal-subsistence-access"
                if desired
                else "seasonal-subsistence-access-ended"
            )
            events.append(
                EventProposal(
                    kind=event_kind,
                    reason=reason,
                    subjects=subjects,
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
                        f"completed societies={len(world.society_regions)} "
                        f"access_changes={len(changes)}"
                    ),
                ),
            ),
        )

    def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
        if change.source != self.name or change.key != _ACCESS_CHANGE_KEY:
            raise ValueError("seasonal access reducer accepts only temporary-access changes")
        if change.target is None or change.target.kind != "society":
            raise ValueError("seasonal access change requires a society target")
        if world.geography is None:
            raise ValueError("seasonal access change requires geography")

        relationships = list(world.society_regions)
        index = next(
            (
                index
                for index, relationship in enumerate(relationships)
                if relationship.society_id == change.target
            ),
            None,
        )
        if index is None:
            raise ValueError("seasonal access target is not an initialized society relationship")

        relationship = relationships[index]
        desired = _access_from_attributes(change.attributes)
        _validate_access(world, relationship, desired)
        expected_delta = round(
            sum(access.access_share for access in desired)
            - sum(access.access_share for access in relationship.temporary_access),
            6,
        )
        if round(change.delta, 6) != expected_delta:
            raise ValueError("seasonal access delta does not match replacement access state")

        relationships[index] = relationship.model_copy(update={"temporary_access": desired})
        return world.model_copy(update={"society_regions": tuple(relationships)})


def _desired_access(
    world: WorldState,
    relationship: SocietyRegionRelationshipState,
    remaining_share: dict[EntityId, float],
) -> tuple[SeasonalSubsistenceAccessState, ...]:
    if world.geography is None or world.knowledge is None:
        return ()
    society = next(
        (
            state
            for state in world.knowledge.societies
            if state.society_id == relationship.society_id
        ),
        None,
    )
    if society is None:
        return ()
    if society.proficiency(MOBILE_PASTORALISM_KEY) < MOBILE_PASTORALISM_ACTIVATION_THRESHOLD:
        return ()

    region_by_id = {region.id: region for region in world.geography.regions}
    candidates: list[_AccessCandidate] = []
    for region_id, travel_cost in _direct_neighbors(world, relationship.core_region_id):
        grazing = region_by_id[region_id].resource_potential("grazing")
        share = min(SEASONAL_PASTORAL_ACCESS_SHARE, remaining_share.get(region_id, 0.0))
        if grazing <= 0.0 or share <= 0.0:
            continue
        candidates.append(
            _AccessCandidate(
                region_id=region_id,
                grazing_potential=grazing,
                travel_cost=travel_cost,
                access_share=round(share, 6),
            )
        )
    if not candidates:
        return ()

    selected = min(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.travel_cost,
            candidate.region_id.value.hex,
        ),
    )
    return (
        SeasonalSubsistenceAccessState(
            region_id=selected.region_id,
            production_method="pastoralism",
            access_share=selected.access_share,
        ),
    )


def _direct_neighbors(world: WorldState, core_region_id: EntityId) -> tuple[tuple[EntityId, float], ...]:
    assert world.geography is not None
    neighbors: list[tuple[EntityId, float]] = []
    for connection in world.geography.connections:
        if connection.a == core_region_id:
            neighbors.append((connection.b, connection.travel_cost))
        elif connection.b == core_region_id:
            neighbors.append((connection.a, connection.travel_cost))
    return tuple(sorted(neighbors, key=lambda item: item[0].value.hex))


def _reserve(
    access: tuple[SeasonalSubsistenceAccessState, ...],
    remaining_share: dict[EntityId, float],
) -> None:
    for item in access:
        remaining = remaining_share[item.region_id] - item.access_share
        if remaining < -1e-6:
            raise RuntimeError("seasonal access allocation exceeded regional opportunity")
        remaining_share[item.region_id] = round(max(0.0, remaining), 6)


def _access_change(
    relationship: SocietyRegionRelationshipState,
    desired: tuple[SeasonalSubsistenceAccessState, ...],
    *,
    reason: str,
    causes: tuple[UUID, ...],
) -> SimulationChange:
    delta = round(
        sum(access.access_share for access in desired)
        - sum(access.access_share for access in relationship.temporary_access),
        6,
    )
    attributes: list[ChangeAttribute] = [
        ChangeAttribute(key="access.count", value=len(desired))
    ]
    for index, access in enumerate(desired):
        prefix = f"access.{index}"
        attributes.extend(
            (
                ChangeAttribute(key=f"{prefix}.region_id", value=str(access.region_id.value)),
                ChangeAttribute(key=f"{prefix}.production_method", value=access.production_method),
                ChangeAttribute(key=f"{prefix}.access_share", value=access.access_share),
            )
        )
    return SimulationChange(
        source="seasonal_access",
        key=_ACCESS_CHANGE_KEY,
        delta=delta,
        reason=reason,
        target=relationship.society_id,
        cause_event_ids=causes,
        attributes=tuple(attributes),
    )


def _access_from_attributes(
    attributes: tuple[ChangeAttribute, ...],
) -> tuple[SeasonalSubsistenceAccessState, ...]:
    values = {attribute.key: attribute.value for attribute in attributes}
    count = values.get("access.count")
    if type(count) is not int or count < 0:
        raise ValueError("seasonal access change requires a non-negative access count")

    access: list[SeasonalSubsistenceAccessState] = []
    for index in range(count):
        prefix = f"access.{index}"
        region_value = values.get(f"{prefix}.region_id")
        method_value = values.get(f"{prefix}.production_method")
        share_value = values.get(f"{prefix}.access_share")
        if not isinstance(region_value, str) or not isinstance(method_value, str):
            raise ValueError("seasonal access change has invalid region or method metadata")
        if not isinstance(share_value, (int, float)) or isinstance(share_value, bool):
            raise ValueError("seasonal access change has invalid share metadata")
        access.append(
            SeasonalSubsistenceAccessState(
                region_id=EntityId(kind="region", value=UUID(region_value)),
                production_method=cast(FoodProductionMethod, method_value),
                access_share=float(share_value),
            )
        )
    return tuple(access)


def _validate_access(
    world: WorldState,
    relationship: SocietyRegionRelationshipState,
    desired: tuple[SeasonalSubsistenceAccessState, ...],
) -> None:
    if len(desired) > 1:
        raise ValueError("initial seasonal access model allows one external region per society")
    neighbor_ids = {region_id for region_id, _ in _direct_neighbors(world, relationship.core_region_id)}
    for access in desired:
        if access.production_method != "pastoralism":
            raise ValueError("initial seasonal access supports pastoralism only")
        if access.region_id not in neighbor_ids:
            raise ValueError("temporary subsistence access must use a directly adjacent region")
        if access.access_share > SEASONAL_PASTORAL_ACCESS_SHARE + 1e-6:
            raise ValueError("temporary subsistence access exceeds the allocation limit")


def _access_reason(
    world: WorldState,
    relationship: SocietyRegionRelationshipState,
    desired: tuple[SeasonalSubsistenceAccessState, ...],
) -> str:
    assert world.geography is not None
    core = next(region for region in world.geography.regions if region.id == relationship.core_region_id)
    if not desired:
        return f"{relationship.society_id.value} ended temporary pastoral access from {core.key}."
    access = desired[0]
    target = next(region for region in world.geography.regions if region.id == access.region_id)
    travel_cost = next(
        cost
        for region_id, cost in _direct_neighbors(world, relationship.core_region_id)
        if region_id == access.region_id
    )
    return (
        f"{relationship.society_id.value} retained {core.key} as its core region and used "
        f"{access.access_share:.3f} of adjacent {target.key} pastoral opportunity; "
        f"grazing={target.resource_potential('grazing'):.3f}, travel_cost={travel_cost:.3f}."
    )


def _relevant_causes(context: TickContext, society_id: EntityId) -> tuple[UUID, ...]:
    return tuple(
        event.id
        for event in context.prior_events
        if society_id in event.subjects
    )
