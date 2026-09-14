"""Explicit cross-domain boundary for population need/pressure inputs."""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from cliova.simulation.domains.population.domain import (
    FOOD_SECURITY,
    HEALTH,
    MATERIAL_SECURITY,
    SAFETY,
    SOCIAL_CONFIDENCE,
)
from cliova.simulation.types import EntityId, SimulationChange, SimulationInput, WorldState

_NEED_FIELDS = {
    FOOD_SECURITY: "food_security",
    MATERIAL_SECURITY: "material_security",
    SAFETY: "safety",
    SOCIAL_CONFIDENCE: "social_confidence",
    HEALTH: "health",
}


@dataclass(frozen=True, slots=True)
class PopulationNeedTarget:
    """Desired regional population condition supplied by another simulation concern."""

    region_id: EntityId
    key: str
    value: float
    reason: str
    cause_event_ids: tuple[UUID, ...] = ()


def population_need_input(
    world: WorldState,
    *,
    source: str,
    kind: str,
    reason: str,
    targets: Iterable[PopulationNeedTarget],
) -> SimulationInput | None:
    """Translate desired need values into population-owned next-tick changes.

    Calling domains provide measured/derived target conditions, but do not need to
    inspect population internals or mutate population state. Population remains the
    authoritative owner of the resulting changes when the engine ingests the input.
    """
    if world.population is None:
        raise ValueError("population pressure input requires initialized population state")

    changes: list[SimulationChange] = []
    subjects: list[EntityId] = []
    for target in targets:
        if target.region_id.kind != "region":
            raise ValueError("population need targets require region IDs")
        field = _NEED_FIELDS.get(target.key)
        if field is None:
            raise ValueError(f"unsupported population need key {target.key!r}")
        if not 0.0 <= target.value <= 1.0:
            raise ValueError(f"{target.key} target must be between 0 and 1")
        try:
            population = world.population.region(target.region_id)
        except KeyError as exc:
            raise ValueError("population need target is not an inhabited region") from exc

        current = float(getattr(population.needs, field))
        delta = round(float(target.value) - current, 6)
        if not delta:
            continue
        changes.append(
            SimulationChange(
                source="population",
                key=target.key,
                delta=delta,
                reason=target.reason,
                target=target.region_id,
                cause_event_ids=target.cause_event_ids,
            )
        )
        if target.region_id not in subjects:
            subjects.append(target.region_id)

    if not changes:
        return None
    return SimulationInput(
        source=source,
        kind=kind,
        reason=reason,
        subjects=tuple(subjects),
        changes=tuple(changes),
    )
