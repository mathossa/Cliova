from uuid import UUID

from cliova.simulation.domains.directives import (
    DirectiveAwareEconomyDomain,
    DirectiveDomain,
    directive_input,
)
from cliova.simulation.domains.economy import (
    initialize_economy,
    population_food_pressure_inputs,
    resource_change_key,
)
from cliova.simulation.domains.politics import GovernanceDomain, initialize_governance
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.scenarios import ScenarioDomain
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine, TickContext, TickPhase
from cliova.simulation.history import EventHistory
from cliova.simulation.randomness import random_for
from cliova.simulation.types import (
    ChangeAttribute,
    EntityId,
    GeographyState,
    GovernanceState,
    InstitutionProfile,
    RegionState,
    ResourcePotential,
    SimulationChange,
    SimulationEvent,
    SimulationInput,
    TickResult,
    WorldState,
    entity_id,
)


def one_region_world(
    *,
    arable_land: float = 0.65,
    execution_capacity: float = 0.9,
    legitimacy: float = 0.9,
    resistance: float = 0.1,
    seed: int = 121,
    world_key: str = "scenario-test",
) -> tuple[WorldState, EntityId, EntityId]:
    world = WorldState.create(seed=seed, world_key=world_key)
    region_id = entity_id(world.id, "region", "scenario:grain-valley")
    region = RegionState(
        id=region_id,
        key="grain-valley",
        terrain="plain",
        biome="temperate",
        habitability=0.9,
        water_access=0.9,
        climate_pressure=0.1,
        resources=(
            ResourcePotential(resource="arable_land", potential=arable_land),
            ResourcePotential(resource="metal_ores", potential=0.2),
            ResourcePotential(resource="stone", potential=0.4),
            ResourcePotential(resource="timber", potential=0.5),
        ),
    )
    world = world.model_copy(
        update={"geography": GeographyState(regions=(region,), connections=())}
    )
    world = initialize_economy(initialize_population(world))

    subject = entity_id(world.id, "society", "grain-council")
    governance = GovernanceState(
        subject_id=subject,
        region_id=region_id,
        institution=InstitutionProfile(
            key="fixed-test-institution",
            coordination_efficiency=1.0,
            stress_resilience=1.0,
            adaptation_rate=0.0,
        ),
        legitimacy=legitimacy,
        execution_capacity=execution_capacity,
        internal_resistance=resistance,
    )
    return initialize_governance(world, states=(governance,)), region_id, subject


def set_food_conditions(
    world: WorldState,
    region_id: EntityId,
    *,
    shortage_severity: float,
    food_security: float,
) -> WorldState:
    assert world.economy is not None and world.population is not None

    economy_regions = list(world.economy.regions)
    economy_index = next(
        index for index, state in enumerate(economy_regions) if state.region_id == region_id
    )
    regional_economy = economy_regions[economy_index]
    resources = list(regional_economy.resources)
    food_index = next(index for index, state in enumerate(resources) if state.resource == "food")
    resources[food_index] = resources[food_index].model_copy(
        update={"shortage_severity": shortage_severity}
    )
    economy_regions[economy_index] = regional_economy.model_copy(
        update={"resources": tuple(resources)}
    )

    population_regions = list(world.population.regions)
    population_index = next(
        index for index, state in enumerate(population_regions) if state.region_id == region_id
    )
    population = population_regions[population_index]
    needs = population.needs.model_copy(update={"food_security": food_security})
    population_regions[population_index] = population.model_copy(update={"needs": needs})

    return world.model_copy(
        update={
            "economy": world.economy.model_copy(update={"regions": tuple(economy_regions)}),
            "population": world.population.model_copy(
                update={"regions": tuple(population_regions)}
            ),
        }
    )


def pressure_for(world: WorldState, region_id: EntityId):
    return next(
        pressure
        for pressure in world.pressures
        if pressure.key == "food_insecurity" and pressure.region_id == region_id
    )


def scenario_engine() -> SimulationEngine:
    return SimulationEngine((ScenarioDomain(),))


def integrated_engine() -> SimulationEngine:
    return SimulationEngine(
        (
            PopulationDomain(),
            DirectiveAwareEconomyDomain(),
            GovernanceDomain(),
            DirectiveDomain(),
            ScenarioDomain(),
        )
    )


def advance_with_food_boundary(
    engine: SimulationEngine,
    world: WorldState,
    pending: tuple[SimulationInput, ...],
    *,
    years: int,
    first_inputs: tuple[SimulationInput, ...] = (),
) -> tuple[WorldState, tuple[SimulationInput, ...], tuple[TickResult, ...]]:
    ticks: list[TickResult] = []
    for index in range(years):
        extra = first_inputs if index == 0 else ()
        tick = engine.step(world, inputs=(*pending, *extra))
        ticks.append(tick)
        world = tick.world
        pending = population_food_pressure_inputs(world, events=tick.events)
    return world, pending, tuple(ticks)


def run_until_crisis(
    world: WorldState, region_id: EntityId
) -> tuple[WorldState, tuple[SimulationInput, ...], tuple[TickResult, ...]]:
    engine = integrated_engine()
    pending: tuple[SimulationInput, ...] = ()
    ticks: list[TickResult] = []
    for _ in range(20):
        tick = engine.step(world, inputs=pending)
        ticks.append(tick)
        world = tick.world
        pending = population_food_pressure_inputs(world, events=tick.events)
        if world.pressures and pressure_for(world, region_id).milestone == "crisis":
            return world, pending, tuple(ticks)
    raise AssertionError("food insecurity did not reach crisis within the focused test window")


def test_healthy_conditions_do_not_create_food_insecurity_pressure() -> None:
    world, region_id, _ = one_region_world(arable_land=0.95)
    world = set_food_conditions(world, region_id, shortage_severity=0.0, food_security=1.0)

    tick = scenario_engine().step(world)

    assert tick.world.pressures == ()
    assert not any(event.source == "scenarios" for event in tick.events)


def test_sustained_food_insecurity_accumulates_escalates_and_does_not_spam_crisis() -> None:
    world, region_id, _ = one_region_world()
    world = set_food_conditions(world, region_id, shortage_severity=0.8, food_security=0.2)

    run = scenario_engine().run(world, years=5)
    states = [pressure_for(tick.world, region_id) for tick in run.ticks]

    assert [state.id for state in states] == [states[0].id] * 5
    assert [state.age_ticks for state in states] == [1, 2, 3, 4, 5]
    assert [state.intensity for state in states] == sorted(state.intensity for state in states)
    assert [state.milestone for state in states[:3]] == ["emerging", "elevated", "crisis"]
    crisis_events = [
        event
        for tick in run.ticks
        for event in tick.events
        if event.kind == "food-insecurity-crisis"
    ]
    assert len(crisis_events) == 1
    assert states[-1].milestone == "crisis"


def test_food_insecurity_deescalates_and_resolves_after_conditions_improve() -> None:
    world, region_id, _ = one_region_world()
    world = set_food_conditions(world, region_id, shortage_severity=0.8, food_security=0.2)
    crisis = scenario_engine().run(world, years=3).world
    assert pressure_for(crisis, region_id).milestone == "crisis"

    recovered_conditions = set_food_conditions(
        crisis, region_id, shortage_severity=0.0, food_security=1.0
    )
    recovery = scenario_engine().run(recovered_conditions, years=6)
    states = [pressure_for(tick.world, region_id) for tick in recovery.ticks]

    assert states[0].milestone == "recovering"
    assert states[0].intensity < pressure_for(crisis, region_id).intensity
    assert states[-1].milestone == "resolved"
    assert states[-1].intensity == 0.0
    assert (
        sum(
            event.kind == "food-insecurity-recovering"
            for tick in recovery.ticks
            for event in tick.events
        )
        == 1
    )
    assert (
        sum(
            event.kind == "food-insecurity-resolved"
            for tick in recovery.ticks
            for event in tick.events
        )
        == 1
    )


def test_food_insecurity_milestone_preserves_exact_scoped_causes() -> None:
    world = initialize_economy(initialize_population(create_starter_world(seed=131)))
    assert world.geography is not None
    fertile = world.geography.region("fertile-lowlands").id
    dry = world.geography.region("dry-basin").id
    fertile_subject = entity_id(world.id, "society", "fertile-council")
    dry_subject = entity_id(world.id, "society", "dry-council")
    institution = InstitutionProfile(
        key="fixed",
        coordination_efficiency=0.8,
        stress_resilience=0.5,
        adaptation_rate=0.1,
    )
    world = initialize_governance(
        world,
        states=(
            GovernanceState(
                subject_id=fertile_subject,
                region_id=fertile,
                institution=institution,
                legitimacy=0.7,
                execution_capacity=0.7,
                internal_resistance=0.2,
            ),
            GovernanceState(
                subject_id=dry_subject,
                region_id=dry,
                institution=institution,
                legitimacy=0.7,
                execution_capacity=0.7,
                internal_resistance=0.2,
            ),
        ),
    )
    world = set_food_conditions(world, fertile, shortage_severity=0.8, food_security=0.2)
    time = world.time.next_year()

    economy_cause = SimulationEvent(
        id=UUID(int=1),
        time=time,
        source="economy",
        kind="resource-shortage",
        reason="fertile shortage",
        subjects=(fertile,),
        changes=(
            SimulationChange(
                source="economy",
                key=resource_change_key("food", "shortage_severity"),
                delta=0.8,
                reason="shortage",
                target=fertile,
            ),
        ),
    )
    population_cause = SimulationEvent(
        id=UUID(int=2),
        time=time,
        source="population",
        kind="population-decline",
        reason="fertile decline",
        subjects=(fertile,),
        changes=(
            SimulationChange(
                source="population",
                key="population.total",
                delta=-10.0,
                reason="decline",
                target=fertile,
            ),
        ),
    )
    governance_cause = SimulationEvent(
        id=UUID(int=3),
        time=time,
        source="governance",
        kind="governance-condition-changed",
        reason="fertile governance stress",
        subjects=(fertile_subject, fertile),
    )
    directive_cause = SimulationEvent(
        id=UUID(int=4),
        time=time,
        source="directives",
        kind="directive-resisted",
        reason="food reserves resisted",
        subjects=(fertile_subject,),
        changes=(
            SimulationChange(
                source="directives",
                key="directives.state",
                delta=0.0,
                reason="resisted",
                target=fertile_subject,
                attributes=(ChangeAttribute(key="intent", value="strengthen_food_reserves"),),
            ),
        ),
    )
    unrelated_region = SimulationEvent(
        id=UUID(int=5),
        time=time,
        source="economy",
        kind="resource-shortage",
        reason="dry shortage",
        subjects=(dry,),
        changes=(
            SimulationChange(
                source="economy",
                key=resource_change_key("food", "shortage_severity"),
                delta=0.8,
                reason="shortage",
                target=dry,
            ),
        ),
    )
    unrelated_subject = SimulationEvent(
        id=UUID(int=6),
        time=time,
        source="directives",
        kind="directive-resisted",
        reason="dry directive",
        subjects=(dry_subject,),
        changes=(
            SimulationChange(
                source="directives",
                key="directives.state",
                delta=0.0,
                reason="resisted",
                target=dry_subject,
                attributes=(ChangeAttribute(key="intent", value="strengthen_food_reserves"),),
            ),
        ),
    )
    context = TickContext(
        time=time,
        phase=TickPhase.KNOWLEDGE_SCENARIOS,
        prior_events=(
            economy_cause,
            population_cause,
            governance_cause,
            directive_cause,
            unrelated_region,
            unrelated_subject,
        ),
        queued_inputs=(),
    )

    result = ScenarioDomain().step(world, context, random_for(world.seed, time.tick, "scenarios"))
    event = next(event for event in result.events if fertile in event.subjects)

    assert event.cause_event_ids == (
        economy_cause.id,
        population_cause.id,
        governance_cause.id,
        directive_cause.id,
    )
    assert dry not in event.subjects
    assert dry_subject not in event.subjects


def test_strengthen_food_reserves_helps_recovery_only_through_normal_economy_path() -> None:
    initial, region_id, subject = one_region_world(arable_land=0.65, world_key="directive-recovery")
    crisis, pending, crisis_ticks = run_until_crisis(initial, region_id)
    baseline_intensity = pressure_for(crisis, region_id).intensity

    treatment_start = WorldState.model_validate_json(crisis.model_dump_json())
    control_start = WorldState.model_validate_json(crisis.model_dump_json())
    treatment, _, treatment_ticks = advance_with_food_boundary(
        integrated_engine(),
        treatment_start,
        pending,
        years=12,
        first_inputs=(directive_input(author="player:one", target_subject=subject),),
    )
    control, _, _ = advance_with_food_boundary(
        integrated_engine(), control_start, pending, years=12
    )

    assert treatment.directives[0].status == "completed"
    assert treatment.economy is not None and control.economy is not None
    assert treatment.economy.region(region_id).resource("food").shortage_severity == 0.0
    assert control.economy.region(region_id).resource("food").shortage_severity > 0.0
    assert pressure_for(treatment, region_id).milestone == "resolved"
    assert pressure_for(control, region_id).milestone == "crisis"
    assert pressure_for(control, region_id).intensity >= baseline_intensity
    assert all(
        change.source == "scenarios" and change.key == "scenarios.pressure"
        for tick in treatment_ticks
        for change in tick.changes
        if change.source == "scenarios"
    )
    assert any(
        change.source == "economy"
        and change.target == region_id
        and change.key == "economy.food.production_capacity"
        for tick in treatment_ticks
        for change in tick.changes
    )

    history = EventHistory.from_ticks((*crisis_ticks, *treatment_ticks))
    resolved = next(
        event
        for event in history.events
        if event.source == "scenarios" and event.kind == "food-insecurity-resolved"
    )
    chain = history.causal_chain(resolved.id)
    assert chain[-1] == resolved
    assert any(event.kind == "resource-recovery" for event in chain)
    assert any(event.source == "directives" for event in chain)


def test_weak_governance_resists_directive_and_crisis_persists() -> None:
    initial, region_id, subject = one_region_world(arable_land=0.65, world_key="resisted-crisis")
    crisis, pending, _ = run_until_crisis(initial, region_id)
    before = pressure_for(crisis, region_id).intensity
    governance = crisis.governance[0].model_copy(
        update={"execution_capacity": 0.9, "legitimacy": 0.9, "internal_resistance": 0.8}
    )
    weak = crisis.model_copy(update={"governance": (governance,)})

    after, _, ticks = advance_with_food_boundary(
        integrated_engine(),
        weak,
        pending,
        years=5,
        first_inputs=(directive_input(author="player:one", target_subject=subject),),
    )

    directive = after.directives[0]
    assert directive.status == "resisted"
    assert directive.progress == 0.0
    assert pressure_for(after, region_id).milestone == "crisis"
    assert pressure_for(after, region_id).intensity >= before
    assert any(event.kind == "directive-resisted" for tick in ticks for event in tick.events)


def test_scenario_replay_is_deterministic() -> None:
    world, region_id, _ = one_region_world(seed=137, world_key="scenario-replay")
    world = set_food_conditions(world, region_id, shortage_severity=0.8, food_security=0.2)

    first = scenario_engine().run(world, years=5)
    second = scenario_engine().run(WorldState.model_validate_json(world.model_dump_json()), years=5)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
