from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from math import isfinite

from simulation_quality import HeadlessTrace, SimulationQualityError, assert_core_invariants

from cliova.simulation.domains.knowledge import KnowledgeDomain
from cliova.simulation.domains.politics import execution_strength
from cliova.simulation.types import EntityId, WorldState


@dataclass(frozen=True, slots=True)
class DomainIdentitySnapshot:
    geography_regions: tuple[EntityId, ...]
    population_regions: tuple[EntityId, ...]
    economy_regions: tuple[EntityId, ...]
    governance_bindings: tuple[tuple[EntityId, EntityId], ...]
    knowledge_bindings: tuple[tuple[EntityId, tuple[EntityId, ...]], ...]


def assert_domain_stack_invariants(
    trace: HeadlessTrace,
    *,
    knowledge_domain: KnowledgeDomain,
) -> None:
    """Check invariants valid for the currently merged living domain stack."""
    assert_core_invariants(trace)
    expected_identity = _identity_snapshot(trace.initial_world)

    assert_world_domain_invariants(
        trace.initial_world,
        seed=trace.seed,
        tick=trace.initial_world.time.tick,
        knowledge_domain=knowledge_domain,
    )
    for tick_result in trace.run.ticks:
        world = tick_result.world
        assert_world_domain_invariants(
            world,
            seed=trace.seed,
            tick=world.time.tick,
            knowledge_domain=knowledge_domain,
        )
        identity = _identity_snapshot(world)
        if identity != expected_identity:
            _fail(
                "stable-domain-references",
                seed=trace.seed,
                tick=world.time.tick,
                detail=f"expected={expected_identity!r} actual={identity!r}",
            )


def assert_world_domain_invariants(
    world: WorldState,
    *,
    seed: int,
    tick: int,
    knowledge_domain: KnowledgeDomain,
) -> None:
    """Validate bounded domain values, references and domain-owned uniqueness."""
    geography_ids = tuple(region.id for region in world.geography.regions) if world.geography else ()
    geography_set = set(geography_ids)
    _assert_unique(
        geography_ids,
        invariant="unique-domain-entities",
        label="geography.region_id",
        seed=seed,
        tick=tick,
    )
    if world.geography is not None:
        _assert_unique(
            tuple(region.key for region in world.geography.regions),
            invariant="unique-domain-entities",
            label="geography.region_key",
            seed=seed,
            tick=tick,
        )

    population_ids: tuple[EntityId, ...] = ()
    if world.population is not None:
        population_ids = tuple(population.region_id for population in world.population.regions)
        _assert_unique(
            population_ids,
            invariant="unique-domain-entities",
            label="population.region_id",
            seed=seed,
            tick=tick,
        )
        for population in world.population.regions:
            entity = _entity_label(population.region_id)
            _assert_reference(
                population.region_id,
                geography_set,
                invariant="valid-domain-reference",
                field="population.region_id",
                seed=seed,
                tick=tick,
            )
            _assert_range(
                population.total,
                lower=0.0,
                upper=None,
                invariant="population-bounds",
                field="population.total",
                entity=entity,
                seed=seed,
                tick=tick,
            )
            for field in (
                "food_security",
                "material_security",
                "safety",
                "social_confidence",
                "health",
            ):
                _assert_range(
                    getattr(population.needs, field),
                    lower=0.0,
                    upper=1.0,
                    invariant="population-bounds",
                    field=f"population.needs.{field}",
                    entity=entity,
                    seed=seed,
                    tick=tick,
                )
            _assert_range(
                population.migration_pressure,
                lower=0.0,
                upper=1.0,
                invariant="population-bounds",
                field="population.migration_pressure",
                entity=entity,
                seed=seed,
                tick=tick,
            )

    economy_ids: tuple[EntityId, ...] = ()
    if world.economy is not None:
        economy_ids = tuple(economy.region_id for economy in world.economy.regions)
        _assert_unique(
            economy_ids,
            invariant="unique-domain-entities",
            label="economy.region_id",
            seed=seed,
            tick=tick,
        )
        population_set = set(population_ids)
        for economy in world.economy.regions:
            entity = _entity_label(economy.region_id)
            _assert_reference(
                economy.region_id,
                geography_set,
                invariant="valid-domain-reference",
                field="economy.region_id",
                seed=seed,
                tick=tick,
            )
            _assert_reference(
                economy.region_id,
                population_set,
                invariant="valid-domain-reference",
                field="economy.inhabited_region_id",
                seed=seed,
                tick=tick,
            )
            _assert_unique(
                tuple(resource.resource for resource in economy.resources),
                invariant="unique-domain-entities",
                label=f"economy.resources[{entity}]",
                seed=seed,
                tick=tick,
            )
            for resource in economy.resources:
                for field in (
                    "production_capacity",
                    "production",
                    "demand",
                    "consumed",
                    "stockpile",
                    "surplus",
                    "deficit",
                ):
                    _assert_range(
                        getattr(resource, field),
                        lower=0.0,
                        upper=None,
                        invariant="economy-bounds",
                        field=f"economy.{resource.resource}.{field}",
                        entity=entity,
                        seed=seed,
                        tick=tick,
                    )
                _assert_range(
                    resource.shortage_severity,
                    lower=0.0,
                    upper=1.0,
                    invariant="economy-bounds",
                    field=f"economy.{resource.resource}.shortage_severity",
                    entity=entity,
                    seed=seed,
                    tick=tick,
                )

                max_modifier = 1.0 + sum(
                    definition.effect.max_bonus
                    for definition in knowledge_domain.catalog
                    if definition.effect.resource == resource.resource
                )
                _assert_range(
                    knowledge_domain.capability_modifier(
                        world,
                        economy.region_id,
                        resource.resource,
                    ),
                    lower=1.0,
                    upper=max_modifier,
                    invariant="knowledge-modifier-bounds",
                    field=f"knowledge.capability_modifier.{resource.resource}",
                    entity=entity,
                    seed=seed,
                    tick=tick,
                )

    governance_subjects = tuple(state.subject_id for state in world.governance)
    _assert_unique(
        governance_subjects,
        invariant="unique-domain-entities",
        label="governance.subject_id",
        seed=seed,
        tick=tick,
    )
    population_set = set(population_ids)
    economy_set = set(economy_ids)
    for state in world.governance:
        entity = _entity_label(state.subject_id)
        _assert_reference(
            state.region_id,
            geography_set,
            invariant="valid-domain-reference",
            field=f"governance.region_id[{entity}]",
            seed=seed,
            tick=tick,
        )
        _assert_reference(
            state.region_id,
            population_set,
            invariant="valid-domain-reference",
            field=f"governance.population_region[{entity}]",
            seed=seed,
            tick=tick,
        )
        _assert_reference(
            state.region_id,
            economy_set,
            invariant="valid-domain-reference",
            field=f"governance.economy_region[{entity}]",
            seed=seed,
            tick=tick,
        )
        for field in ("legitimacy", "execution_capacity", "internal_resistance"):
            _assert_range(
                getattr(state, field),
                lower=0.0,
                upper=1.0,
                invariant="governance-bounds",
                field=f"governance.{field}",
                entity=entity,
                seed=seed,
                tick=tick,
            )
        for field in ("coordination_efficiency", "stress_resilience", "adaptation_rate"):
            _assert_range(
                getattr(state.institution, field),
                lower=0.0,
                upper=1.0,
                invariant="governance-bounds",
                field=f"governance.institution.{field}",
                entity=entity,
                seed=seed,
                tick=tick,
            )
        _assert_range(
            execution_strength(state),
            lower=0.0,
            upper=1.0,
            invariant="governance-bounds",
            field="governance.execution_strength",
            entity=entity,
            seed=seed,
            tick=tick,
        )

    if world.knowledge is not None:
        society_ids = tuple(society.society_id for society in world.knowledge.societies)
        _assert_unique(
            society_ids,
            invariant="unique-domain-entities",
            label="knowledge.society_id",
            seed=seed,
            tick=tick,
        )
        participation = tuple(
            region_id
            for society in world.knowledge.societies
            for region_id in society.region_ids
        )
        _assert_unique(
            participation,
            invariant="unique-domain-entities",
            label="knowledge.participation_region",
            seed=seed,
            tick=tick,
        )
        for society in world.knowledge.societies:
            entity = _entity_label(society.society_id)
            _assert_unique(
                society.region_ids,
                invariant="unique-domain-entities",
                label=f"knowledge.region_ids[{entity}]",
                seed=seed,
                tick=tick,
            )
            for region_id in society.region_ids:
                _assert_reference(
                    region_id,
                    geography_set,
                    invariant="valid-domain-reference",
                    field=f"knowledge.region_id[{entity}]",
                    seed=seed,
                    tick=tick,
                )
            _assert_unique(
                tuple(capability.capability_key for capability in society.capabilities),
                invariant="unique-domain-entities",
                label=f"knowledge.capabilities[{entity}]",
                seed=seed,
                tick=tick,
            )
            for capability in society.capabilities:
                _assert_range(
                    capability.proficiency,
                    lower=0.0,
                    upper=1.0,
                    invariant="knowledge-bounds",
                    field=f"knowledge.proficiency.{capability.capability_key}",
                    entity=entity,
                    seed=seed,
                    tick=tick,
                )
            _assert_unique(
                tuple(experience.key for experience in society.experience),
                invariant="unique-domain-entities",
                label=f"knowledge.experience[{entity}]",
                seed=seed,
                tick=tick,
            )
            for experience in society.experience:
                _assert_range(
                    experience.amount,
                    lower=0.0,
                    upper=None,
                    invariant="knowledge-bounds",
                    field=f"knowledge.experience.{experience.key}",
                    entity=entity,
                    seed=seed,
                    tick=tick,
                )


def _identity_snapshot(world: WorldState) -> DomainIdentitySnapshot:
    geography_regions = _sorted_ids(
        region.id for region in world.geography.regions
    ) if world.geography else ()
    population_regions = _sorted_ids(
        population.region_id for population in world.population.regions
    ) if world.population else ()
    economy_regions = _sorted_ids(
        economy.region_id for economy in world.economy.regions
    ) if world.economy else ()
    governance_bindings = tuple(
        sorted(
            ((state.subject_id, state.region_id) for state in world.governance),
            key=lambda item: _entity_sort_key(item[0]),
        )
    )
    knowledge_bindings = tuple(
        sorted(
            (
                (society.society_id, _sorted_ids(society.region_ids))
                for society in world.knowledge.societies
            ),
            key=lambda item: _entity_sort_key(item[0]),
        )
    ) if world.knowledge else ()
    return DomainIdentitySnapshot(
        geography_regions=geography_regions,
        population_regions=population_regions,
        economy_regions=economy_regions,
        governance_bindings=governance_bindings,
        knowledge_bindings=knowledge_bindings,
    )


def _sorted_ids(values: Sequence[EntityId] | object) -> tuple[EntityId, ...]:
    return tuple(sorted(values, key=_entity_sort_key))  # type: ignore[arg-type]


def _entity_sort_key(value: EntityId) -> tuple[str, str]:
    return value.kind, value.value.hex


def _entity_label(value: EntityId) -> str:
    return f"{value.kind}:{value.value}"


def _assert_unique(
    values: Sequence[Hashable],
    *,
    invariant: str,
    label: str,
    seed: int,
    tick: int,
) -> None:
    seen: dict[Hashable, int] = {}
    for index, value in enumerate(values):
        first_index = seen.get(value)
        if first_index is not None:
            _fail(
                invariant,
                seed=seed,
                tick=tick,
                detail=(
                    f"field={label} duplicate={value!r} "
                    f"first_index={first_index} duplicate_index={index}"
                ),
            )
        seen[value] = index


def _assert_reference(
    value: EntityId,
    known: set[EntityId],
    *,
    invariant: str,
    field: str,
    seed: int,
    tick: int,
) -> None:
    if value not in known:
        _fail(
            invariant,
            seed=seed,
            tick=tick,
            detail=f"field={field} entity={_entity_label(value)} is not in the referenced domain",
        )


def _assert_range(
    value: float | int,
    *,
    lower: float,
    upper: float | None,
    invariant: str,
    field: str,
    entity: str,
    seed: int,
    tick: int,
) -> None:
    numeric = float(value)
    out_of_range = numeric < lower or (upper is not None and numeric > upper)
    if not isfinite(numeric) or out_of_range:
        expected = f">={lower}" if upper is None else f"[{lower}, {upper}]"
        _fail(
            invariant,
            seed=seed,
            tick=tick,
            detail=f"entity={entity} field={field} value={value!r} expected={expected}",
        )


def _fail(invariant: str, *, seed: int, tick: int, detail: str) -> None:
    raise SimulationQualityError(f"{invariant} failed: seed={seed} tick={tick}; {detail}")
