from __future__ import annotations

import pytest
from simulation_domain_quality import (
    assert_domain_stack_invariants,
    assert_world_domain_invariants,
)
from simulation_quality import (
    SimulationQualityError,
    assert_replay_equivalent,
    measure_tick_runtime,
    run_headless,
)
from test_scenarios import one_region_world, pressure_for

from cliova.application.development import create_development_world, create_simulation_engine
from cliova.simulation.domains.directives import directive_input
from cliova.simulation.domains.economy import population_food_pressure_inputs
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.population import initialize_society_region_relationships
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    SeasonalSubsistenceAccessState,
    SimulationInput,
    SocietyKnowledgeState,
    SocietyRegionRelationshipState,
    TickResult,
    WorldState,
)

SEED = 118


def _living_world() -> WorldState:
    return create_development_world(seed=SEED, world_key="quality-final")


def _food_boundary(tick: TickResult) -> tuple[SimulationInput, ...]:
    return population_food_pressure_inputs(tick.world, events=tick.events)


def test_complete_living_stack_replays_100_years_with_ordered_directive_input() -> None:
    initial = _living_world()
    ordered = ((),) * 5 + (
        (
            directive_input(
                author="quality-player",
                target_subject=initial.governance[0].subject_id,
            ),
        ),
    )
    first, second = assert_replay_equivalent(
        _living_world,
        create_simulation_engine,
        years=100,
        inputs=ordered,
        next_inputs=_food_boundary,
    )
    for trace in (first, second):
        assert_domain_stack_invariants(trace, knowledge_domain=KnowledgeDomain())
    assert first.run.world.year - initial.year == 100
    assert first.run.world.directives[0].progress > 0.0
    assert any(r.temporary_access for tick in first.run.ticks for r in tick.world.society_regions)
    assert any(
        resource.food_reserves and resource.food_reserves.preserved > 0.0
        for tick in first.run.ticks
        if tick.world.economy is not None
        for region in tick.world.economy.regions
        for resource in region.resources
    )
    history = EventHistory.from_run(first.run)
    resolved = history.query(event_type="food-insecurity-resolved")
    assert resolved
    for event in resolved:
        assert any(
            cause.source in {"economy", "population"}
            for cause in history.causal_chain(event.id, include_target=False)
        )
    timing = measure_tick_runtime(_living_world, create_simulation_engine, repeats=5)
    print(f"complete-stack tick median={timing.median_ms:.3f} ms samples={timing.durations_ns}")


def _constrained_world() -> WorldState:
    # Reuse #12's starting geography/governance, adding the real #11/#50 initializers.
    world, region, society = one_region_world(seed=SEED, world_key="quality-yield-cap")
    world = initialize_knowledge(
        world,
        societies=(
            SocietyKnowledgeState(
                society_id=society,
                region_ids=(region,),
            ),
        ),
    )
    return initialize_society_region_relationships(
        world,
        relationships=(SocietyRegionRelationshipState(society_id=society, core_region_id=region),),
    )


def test_complete_stack_tension_directive_cannot_overcome_sustainable_limit() -> None:
    initial = _constrained_world()
    subject = initial.governance[0].subject_id
    region = initial.governance[0].region_id
    ordered = ((),) * 5 + ((directive_input(author="quality-player", target_subject=subject),),)
    treatment = run_headless(
        _constrained_world,
        create_simulation_engine,
        years=20,
        inputs=ordered,
        next_inputs=_food_boundary,
    )
    control = run_headless(
        _constrained_world, create_simulation_engine, years=20, next_inputs=_food_boundary
    )
    for trace in (treatment, control):
        assert_domain_stack_invariants(trace, knowledge_domain=KnowledgeDomain())
    before = treatment.run.ticks[4].world
    assert pressure_for(before, region).milestone == "crisis"
    assert (
        pressure_for(before, region).intensity
        > pressure_for(treatment.run.ticks[0].world, region).intensity
    )
    assert treatment.run.world.directives[0].status == "completed"
    assert treatment.run.world.economy and control.run.world.economy
    food = treatment.run.world.economy.region(region).resource("food")
    baseline = control.run.world.economy.region(region).resource("food")
    assert food.production_capacity > baseline.production_capacity
    assert food.production == baseline.production
    assert food.shortage_severity == baseline.shortage_severity > 0.0
    assert pressure_for(treatment.run.world, region).milestone == "crisis"
    assert any(
        m.output == m.sustainable_limit < m.labour_limited_output
        for m in food.food_production
        if m.output > 0.0
    )
    history = EventHistory.from_run(treatment.run)
    crisis = history.query(event_type="food-insecurity-crisis", subject=region)[0]
    assert any(event.kind == "resource-shortage" for event in history.causal_chain(crisis.id))
    completed = history.query(event_type="directive-completed", subject=subject)[0]
    chain = history.causal_chain(completed.id)
    assert any(event.kind == "directive-submitted" for event in chain)
    assert any(
        event.kind in {"directive-accepted", "directive-partial"}
        for event in history.query(subject=subject)
    )
    assert treatment.run.world.population is not None
    assert treatment.run.world.population.region(region).needs.food_security < 1.0
    assert any(
        change.key == "economy.food.production_capacity" and change.delta > 0.0
        for tick in treatment.run.ticks[6:]
        for change in tick.changes
    )
    # The current economy adapter carries progress through state, not a cross-tick
    # directive event link. Verify actual causal edges without inventing such an event.
    for event in history.events:
        history.causal_chain(event.id)


def test_domain_bound_failure_reports_seed_tick_and_entity() -> None:
    world = _living_world()
    assert world.population is not None
    population = world.population.regions[0]
    broken_needs = population.needs.model_copy(update={"food_security": 1.25})
    broken_population = population.model_copy(update={"needs": broken_needs})
    broken_state = world.population.model_copy(
        update={"regions": (broken_population, *world.population.regions[1:])}
    )
    broken_world = world.model_copy(update={"population": broken_state})

    with pytest.raises(
        SimulationQualityError,
        match=(
            r"population-bounds failed: seed=118 tick=0; "
            r"entity=region:.*field=population.needs.food_security value=1.25"
        ),
    ):
        assert_world_domain_invariants(
            broken_world,
            seed=SEED,
            tick=0,
            knowledge_domain=KnowledgeDomain(),
        )


def test_duplicate_domain_entity_failure_reports_seed_tick_and_field() -> None:
    world = _living_world()
    assert world.population is not None
    first = world.population.regions[0]
    broken_state = world.population.model_copy(
        update={"regions": (first, first, *world.population.regions[1:])}
    )
    broken_world = world.model_copy(update={"population": broken_state})

    with pytest.raises(
        SimulationQualityError,
        match=(
            r"unique-domain-entities failed: seed=118 tick=0; "
            r"field=population.region_id duplicate=.*first_index=0 duplicate_index=1"
        ),
    ):
        assert_world_domain_invariants(
            broken_world,
            seed=SEED,
            tick=0,
            knowledge_domain=KnowledgeDomain(),
        )


@pytest.mark.parametrize("corruption", ("reserves", "conservation", "labour", "access", "method"))
def test_complete_stack_corruption_retains_seed_tick_and_field(corruption: str) -> None:
    trace = run_headless(_living_world, create_simulation_engine, years=1)
    result = trace.run.ticks[0]
    world = result.world
    assert world.economy is not None
    regional = world.economy.regions[0]
    food = regional.resource("food")
    if corruption == "access":
        assert world.geography is not None
        relationship = world.society_regions[0]
        connection = next(
            c for c in world.geography.connections if relationship.core_region_id in (c.a, c.b)
        )
        neighbor = connection.b if connection.a == relationship.core_region_id else connection.a
        relationship = relationship.model_copy(
            update={
                "temporary_access": (
                    SeasonalSubsistenceAccessState(
                        region_id=neighbor, production_method="pastoralism", access_share=0.7
                    ),
                )
            }
        )
        world = world.model_copy(update={"society_regions": (relationship,)})
        diagnostic = "access share"
    else:
        if corruption == "reserves":
            food = food.model_copy(update={"stockpile": food.stockpile + 1.0})
            diagnostic = "stockpile"
        elif corruption == "conservation":
            assert food.food_reserves is not None
            reserves = food.food_reserves.model_copy(
                update={
                    "durable": food.food_reserves.durable + 1.0,
                }
            )
            food = food.model_copy(
                update={"stockpile": food.stockpile + 1.0, "food_reserves": reserves}
            )
            diagnostic = "resource=food"
        else:
            method = food.food_production[0]
            field = "allocated_labour" if corruption == "labour" else "output"
            method = method.model_copy(update={field: 1e9})
            food = food.model_copy(update={"food_production": (method, *food.food_production[1:])})
            diagnostic = "labour" if corruption == "labour" else "limit"
        assert world.economy is not None
        regional = regional.model_copy(
            update={
                "resources": tuple(food if r.resource == "food" else r for r in regional.resources)
            }
        )
        world = world.model_copy(
            update={
                "economy": world.economy.model_copy(
                    update={
                        "regions": (regional, *world.economy.regions[1:]),
                    }
                )
            }
        )
    broken = trace.__class__(
        initial_world=trace.initial_world,
        run=trace.run.model_copy(
            update={
                "world": world,
                "ticks": (result.model_copy(update={"world": world}),),
            }
        ),
    )
    with pytest.raises(SimulationQualityError, match=rf"seed=118 tick=1;[\s\S]*{diagnostic}"):
        assert_domain_stack_invariants(broken, knowledge_domain=KnowledgeDomain())
