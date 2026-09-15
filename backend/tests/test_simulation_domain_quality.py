from __future__ import annotations

import pytest
from simulation_domain_quality import (
    assert_domain_stack_invariants,
    assert_world_domain_invariants,
)
from simulation_quality import SimulationQualityError, assert_replay_equivalent

from cliova.simulation.domains.economy import (
    EconomyDomain,
    initialize_economy,
    population_food_pressure_inputs,
)
from cliova.simulation.domains.knowledge import KnowledgeDomain, initialize_knowledge
from cliova.simulation.domains.politics import GovernanceDomain, initialize_governance
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.types import (
    ExperienceTrack,
    GovernanceState,
    InstitutionProfile,
    SimulationInput,
    SocietyKnowledgeState,
    WorldState,
    entity_id,
)

SEED = 118


def _living_world() -> WorldState:
    world = initialize_economy(initialize_population(create_starter_world(seed=SEED)))
    assert world.geography is not None
    society_id = entity_id(world.id, "society", "quality-travellers")
    region_id = world.geography.region("fertile-lowlands").id
    world = initialize_knowledge(
        world,
        (
            SocietyKnowledgeState(
                society_id=society_id,
                region_ids=(region_id,),
                experience=(
                    ExperienceTrack(key="cultivation", amount=1.0),
                    ExperienceTrack(key="extraction", amount=1.0),
                ),
            ),
        ),
    )
    return initialize_governance(
        world,
        states=(
            GovernanceState(
                subject_id=society_id,
                region_id=region_id,
                institution=InstitutionProfile(
                    key="quality-coordination",
                    coordination_efficiency=0.75,
                    stress_resilience=0.35,
                    adaptation_rate=0.4,
                ),
                legitimacy=0.85,
                execution_capacity=0.7,
                internal_resistance=0.1,
            ),
        ),
    )


def _living_engine() -> SimulationEngine:
    knowledge = KnowledgeDomain()
    return SimulationEngine(
        (
            PopulationDomain(),
            EconomyDomain(knowledge.capability_modifier),
            GovernanceDomain(),
            knowledge,
        )
    )


def _living_inputs(years: int) -> tuple[tuple[SimulationInput, ...], ...]:
    """Build the existing economy -> population next-tick boundary deterministically."""
    world = _living_world()
    engine = _living_engine()
    next_inputs: tuple[SimulationInput, ...] = ()
    batches: list[tuple[SimulationInput, ...]] = []
    for _ in range(years):
        batches.append(next_inputs)
        tick = engine.step(world, inputs=next_inputs)
        next_inputs = population_food_pressure_inputs(tick.world, events=tick.events)
        world = tick.world
    return tuple(batches)


def test_current_living_domain_stack_replays_and_holds_invariants() -> None:
    years = 12
    first, second = assert_replay_equivalent(
        _living_world,
        _living_engine,
        years=years,
        inputs=_living_inputs(years),
    )

    assert_domain_stack_invariants(first, knowledge_domain=KnowledgeDomain())
    assert_domain_stack_invariants(second, knowledge_domain=KnowledgeDomain())
    assert first.run.world == second.run.world


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
