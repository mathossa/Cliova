from __future__ import annotations

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from math import isclose, isfinite

from simulation_quality import (
    HeadlessTrace,
    SimulationQualityError,
    assert_core_invariants,
)

from cliova.simulation.domains.economy import LABOUR_SHARE
from cliova.simulation.domains.knowledge import KnowledgeDomain
from cliova.simulation.domains.politics import execution_strength
from cliova.simulation.domains.population.seasonal_access import SEASONAL_PASTORAL_ACCESS_SHARE
from cliova.simulation.types import EntityId, WorldState


@dataclass(frozen=True, slots=True)
class DomainIdentitySnapshot:
    geography_regions: tuple[EntityId, ...]
    population_regions: tuple[EntityId, ...]
    economy_regions: tuple[EntityId, ...]
    governance_bindings: tuple[tuple[EntityId, EntityId], ...]
    knowledge_bindings: tuple[tuple[EntityId, tuple[EntityId, ...]], ...]
    society_cores: tuple[tuple[EntityId, EntityId], ...]


def assert_domain_stack_invariants(
    trace: HeadlessTrace,
    *,
    knowledge_domain: KnowledgeDomain,
) -> None:
    """Check invariants valid for the currently merged living domain stack."""
    assert_core_invariants(trace)
    expected_identity = _identity_snapshot(trace.initial_world)
    worlds = (trace.initial_world, *(tick.world for tick in trace.run.ticks))

    for world in worlds:
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

    previous = trace.initial_world
    for result in trace.run.ticks:
        world = result.world
        try:
            if world.population and previous.population:
                for population in world.population.regions:
                    delta = sum(
                        change.delta
                        for change in result.changes
                        if change.target == population.region_id
                        and change.key == "population.total"
                    )
                    assert (
                        population.total
                        == previous.population.region(population.region_id).total + delta
                    ), (
                        f"region={population.region_id} population.total={population.total} "
                        f"delta={delta}"
                    )
            if world.economy and previous.economy:
                for regional in world.economy.regions:
                    for resource in regional.resources:
                        before = previous.economy.region(regional.region_id).resource(
                            resource.resource
                        )
                        loss = (
                            resource.food_reserves.spoilage_loss if resource.food_reserves else 0.0
                        )
                        assert isclose(
                            before.stockpile + resource.production,
                            resource.consumed + loss + resource.stockpile,
                            rel_tol=0.0,
                            abs_tol=3e-6,
                        ), (
                            f"region={regional.region_id} resource={resource.resource} "
                            f"previous={before.stockpile} production={resource.production} "
                            f"consumed={resource.consumed} loss={loss} "
                            f"stockpile={resource.stockpile}"
                        )
            for old in previous.directives:
                current = next(item for item in world.directives if item.id == old.id)
                assert current.model_dump(exclude={"status", "progress"}) == old.model_dump(
                    exclude={"status", "progress"}
                ), f"directive={old.id} identity changed"
                assert current.progress >= old.progress, f"directive={old.id} progress decreased"
                if old.status in {"completed", "failed"}:
                    assert current == old, f"directive={old.id} terminal state changed"
        except (AssertionError, KeyError, StopIteration) as exc:
            _fail("domain-accounting", seed=trace.seed, tick=world.time.tick, detail=str(exc))
        previous = world


def assert_world_domain_invariants(
    world: WorldState,
    *,
    seed: int,
    tick: int,
    knowledge_domain: KnowledgeDomain,
) -> None:
    """Validate merged domain bounds, references and domain-owned uniqueness."""
    geography_ids = (
        tuple(region.id for region in world.geography.regions) if world.geography else ()
    )
    geography_set = set(geography_ids)
    _assert_unique(
        geography_ids,
        invariant="unique-domain-entities",
        label="geography.region_id",
        seed=seed,
        tick=tick,
    )
    if world.geography:
        _assert_unique(
            (region.key for region in world.geography.regions),
            invariant="unique-domain-entities",
            label="geography.region_key",
            seed=seed,
            tick=tick,
        )

    population_ids: tuple[EntityId, ...] = ()
    if world.population:
        population_ids = tuple(item.region_id for item in world.population.regions)
        _assert_unique(
            population_ids,
            invariant="unique-domain-entities",
            label="population.region_id",
            seed=seed,
            tick=tick,
        )
        for item in world.population.regions:
            entity = _entity_label(item.region_id)
            _assert_reference(
                item.region_id,
                geography_set,
                field="population.region_id",
                seed=seed,
                tick=tick,
            )
            _assert_range(
                item.total,
                lower=0.0,
                upper=None,
                invariant="population-bounds",
                field="population.total",
                entity=entity,
                seed=seed,
                tick=tick,
            )
            _assert_fields(
                item.needs,
                (
                    "food_security",
                    "material_security",
                    "safety",
                    "social_confidence",
                    "health",
                ),
                lower=0.0,
                upper=1.0,
                invariant="population-bounds",
                prefix="population.needs",
                entity=entity,
                seed=seed,
                tick=tick,
            )
            _assert_range(
                item.migration_pressure,
                lower=0.0,
                upper=1.0,
                invariant="population-bounds",
                field="population.migration_pressure",
                entity=entity,
                seed=seed,
                tick=tick,
            )

    economy_ids: tuple[EntityId, ...] = ()
    if world.economy:
        economy_ids = tuple(item.region_id for item in world.economy.regions)
        _assert_unique(
            economy_ids,
            invariant="unique-domain-entities",
            label="economy.region_id",
            seed=seed,
            tick=tick,
        )
        population_set = set(population_ids)
        for economy_region in world.economy.regions:
            entity = _entity_label(economy_region.region_id)
            _assert_reference(
                economy_region.region_id,
                geography_set,
                field="economy.region_id",
                seed=seed,
                tick=tick,
            )
            _assert_reference(
                economy_region.region_id,
                population_set,
                field="economy.inhabited_region_id",
                seed=seed,
                tick=tick,
            )
            _assert_unique(
                (resource.resource for resource in economy_region.resources),
                invariant="unique-domain-entities",
                label=f"economy.resources[{entity}]",
                seed=seed,
                tick=tick,
            )
            for resource in economy_region.resources:
                _assert_fields(
                    resource,
                    (
                        "production_capacity",
                        "production",
                        "demand",
                        "consumed",
                        "stockpile",
                        "surplus",
                        "deficit",
                    ),
                    lower=0.0,
                    upper=None,
                    invariant="economy-bounds",
                    prefix=f"economy.{resource.resource}",
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
                modifier = knowledge_domain.capability_modifier(
                    world,
                    economy_region.region_id,
                    resource.resource,
                )
                _assert_range(
                    modifier,
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
        for field, known in (
            ("geography", geography_set),
            ("population", population_set),
            ("economy", economy_set),
        ):
            _assert_reference(
                state.region_id,
                known,
                field=f"governance.{field}_region[{entity}]",
                seed=seed,
                tick=tick,
            )
        _assert_fields(
            state,
            ("legitimacy", "execution_capacity", "internal_resistance"),
            lower=0.0,
            upper=1.0,
            invariant="governance-bounds",
            prefix="governance",
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

    if world.knowledge:
        society_ids = tuple(item.society_id for item in world.knowledge.societies)
        _assert_unique(
            society_ids,
            invariant="unique-domain-entities",
            label="knowledge.society_id",
            seed=seed,
            tick=tick,
        )
        _assert_unique(
            (
                region_id
                for society in world.knowledge.societies
                for region_id in society.region_ids
            ),
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
                    field=f"knowledge.region_id[{entity}]",
                    seed=seed,
                    tick=tick,
                )
            _assert_unique(
                (item.capability_key for item in society.capabilities),
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
                (item.key for item in society.experience),
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

    # Reuse authoritative Pydantic bounds/food-limit/reserve/reference validators via
    # assert_core_invariants; only cross-record relationships missing there live here.
    try:
        if world.economy and world.population and world.geography:
            for regional in world.economy.regions:
                food = regional.resource("food")
                if food.food_production:
                    assert sum(method.allocated_labour for method in food.food_production) <= (
                        world.population.region(regional.region_id).total * LABOUR_SHARE + 3e-6
                    ), f"region={regional.region_id} allocated food labour exceeds pool"
                    assert isclose(
                        food.production,
                        sum(m.output for m in food.food_production),
                        rel_tol=0.0,
                        abs_tol=3e-6,
                    ), f"region={regional.region_id} food production sum"
                for resource in regional.resources:
                    assert resource.consumed <= resource.demand + 1e-6, (
                        f"region={regional.region_id} resource={resource.resource} "
                        "consumed > demand"
                    )
                    assert isclose(
                        resource.demand,
                        resource.consumed + resource.deficit,
                        rel_tol=0.0,
                        abs_tol=3e-6,
                    ), f"region={regional.region_id} demand accounting"
            # Global conservation detects duplicated local/external grazing opportunity.
            pastoral = [
                method
                for regional in world.economy.regions
                for method in regional.resource("food").food_production
                if method.method == "pastoralism"
            ]
            assert sum(m.regional_potential + m.external_potential for m in pastoral) <= (
                sum(r.resource_potential("grazing") for r in world.geography.regions) + 1e-5
            ), "pastoralism local + external potential exceeds world opportunity"
        shares: dict[EntityId, float] = {}
        for relationship in world.society_regions:
            assert world.geography is not None
            neighbors = {
                connection.b if connection.a == relationship.core_region_id else connection.a
                for connection in world.geography.connections
                if relationship.core_region_id in (connection.a, connection.b)
            }
            for access in relationship.temporary_access:
                assert access.region_id in neighbors, (
                    f"society={relationship.society_id} access not adjacent"
                )
                assert access.production_method == "pastoralism", (
                    f"society={relationship.society_id} access method"
                )
                assert access.access_share <= SEASONAL_PASTORAL_ACCESS_SHARE, (
                    f"society={relationship.society_id} access share={access.access_share}"
                )
                shares[access.region_id] = shares.get(access.region_id, 0.0) + access.access_share
        for region_id, share in shares.items():
            assert share <= 1.0 + 1e-6, f"region={region_id} allocated access share={share}"
        for directive in world.directives:
            assert directive.submitted_tick <= tick, f"directive={directive.id} future submission"
            if directive.status != "failed":
                assert directive.target_subject in governance_subjects, (
                    f"directive={directive.id} target"
                )
            if directive.status == "completed":
                assert directive.progress == 1.0, f"directive={directive.id} incomplete completion"
        for pressure in world.pressures:
            if pressure.subject_id is not None:
                assert pressure.subject_id in governance_subjects, f"pressure={pressure.id} subject"
            if pressure.milestone == "resolved":
                assert pressure.intensity == 0.0, f"pressure={pressure.id} resolved intensity"
    except (AssertionError, KeyError) as exc:
        _fail("living-stack-integrity", seed=seed, tick=tick, detail=str(exc))


def _identity_snapshot(world: WorldState) -> DomainIdentitySnapshot:
    geography = (
        _sorted_ids(region.id for region in world.geography.regions) if world.geography else ()
    )
    population = (
        _sorted_ids(item.region_id for item in world.population.regions) if world.population else ()
    )
    economy = _sorted_ids(item.region_id for item in world.economy.regions) if world.economy else ()
    governance = tuple(
        sorted(
            ((state.subject_id, state.region_id) for state in world.governance),
            key=lambda item: _entity_sort_key(item[0]),
        )
    )
    knowledge = (
        tuple(
            sorted(
                (
                    (society.society_id, _sorted_ids(society.region_ids))
                    for society in world.knowledge.societies
                ),
                key=lambda item: _entity_sort_key(item[0]),
            )
        )
        if world.knowledge
        else ()
    )
    cores = tuple(
        sorted(
            ((r.society_id, r.core_region_id) for r in world.society_regions),
            key=lambda item: _entity_sort_key(item[0]),
        )
    )
    return DomainIdentitySnapshot(geography, population, economy, governance, knowledge, cores)


def _assert_fields(
    value: object,
    fields: tuple[str, ...],
    *,
    lower: float,
    upper: float | None,
    invariant: str,
    prefix: str,
    entity: str,
    seed: int,
    tick: int,
) -> None:
    for field in fields:
        _assert_range(
            getattr(value, field),
            lower=lower,
            upper=upper,
            invariant=invariant,
            field=f"{prefix}.{field}",
            entity=entity,
            seed=seed,
            tick=tick,
        )


def _sorted_ids(values: Iterable[EntityId]) -> tuple[EntityId, ...]:
    return tuple(sorted(values, key=_entity_sort_key))


def _entity_sort_key(value: EntityId) -> tuple[str, str]:
    return value.kind, value.value.hex


def _entity_label(value: EntityId) -> str:
    return f"{value.kind}:{value.value}"


def _assert_unique(
    values: Iterable[Hashable],
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
    field: str,
    seed: int,
    tick: int,
) -> None:
    if value not in known:
        _fail(
            "valid-domain-reference",
            seed=seed,
            tick=tick,
            detail=(f"field={field} entity={_entity_label(value)} is not in the referenced domain"),
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
            detail=(f"entity={entity} field={field} value={value!r} expected={expected}"),
        )


def _fail(invariant: str, *, seed: int, tick: int, detail: str) -> None:
    raise SimulationQualityError(f"{invariant} failed: seed={seed} tick={tick}; {detail}")
