from uuid import UUID

import pytest
from pydantic import ValidationError

from cliova.simulation.domains.economy import (
    EconomyDomain,
    initialize_economy,
    population_food_pressure_inputs,
)
from cliova.simulation.domains.politics import (
    GovernanceDomain,
    GovernancePressure,
    advance_governance,
    execution_strength,
    governance_pressure,
    initialize_governance,
)
from cliova.simulation.domains.population import PopulationDomain, initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine, TickContext, TickExecutionError, TickPhase
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    EntityId,
    GovernanceState,
    InstitutionProfile,
    SimulationChange,
    SimulationInput,
    WorldState,
    entity_id,
)


def fixture() -> tuple[WorldState, GovernanceState]:
    world = initialize_economy(initialize_population(create_starter_world(seed=81)))
    assert world.geography is not None
    state = GovernanceState(
        subject_id=entity_id(world.id, "society", "travellers"),
        region_id=world.geography.region("dry-basin").id,
        institution=InstitutionProfile(
            key="test-a",
            coordination_efficiency=0.8,
            stress_resilience=0.2,
            adaptation_rate=0.5,
        ),
        legitimacy=1,
        execution_capacity=0.8,
        internal_resistance=0,
    )
    return initialize_governance(world, states=(state,)), state


def pressure(stress: float = 0) -> GovernancePressure:
    return GovernancePressure(
        social_confidence=1 - stress,
        migration_pressure=stress,
        food_shortage_severity=stress,
    )


def test_stable_and_legacy_worlds() -> None:
    world, state = fixture()
    result = SimulationEngine((GovernanceDomain(),)).step(world)
    assert result.world.governance == (state,)
    assert not result.changes and not result.events
    legacy = world.model_dump()
    del legacy["governance"]
    assert WorldState.model_validate(legacy).governance == ()
    assert WorldState.model_validate_json(world.model_dump_json()) == world
    assert SimulationEngine((GovernanceDomain(),)).step(WorldState.create(seed=1)).changes == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("social_confidence", 0),
        ("migration_pressure", 1),
        ("food_shortage_severity", 1),
    ],
)
def test_each_pressure_causes_stress(field: str, value: float) -> None:
    _, state = fixture()
    observed = pressure().model_copy(update={field: value})
    next_state = advance_governance(state, observed)
    assert next_state.legitimacy < state.legitimacy
    assert next_state.execution_capacity < state.execution_capacity
    assert next_state.internal_resistance > state.internal_resistance
    assert execution_strength(next_state) < execution_strength(state)


def test_no_double_counting_and_exact_rules() -> None:
    _, state = fixture()
    result = advance_governance(state, pressure(1))
    assert result.internal_resistance == 0.4
    assert result.legitimacy == 0.6
    assert result.execution_capacity == 0.544
    assert result == advance_governance(
        state,
        pressure().model_copy(
            update={"food_shortage_severity": 1},
        ),
    )


def test_recovery_and_profile_parameters() -> None:
    _, state = fixture()
    resilient = state.model_copy(
        update={
            "institution": state.institution.model_copy(
                update={"key": "test-b", "stress_resilience": 0.7},
            )
        }
    )
    stressed = advance_governance(state, pressure(1))
    assert advance_governance(resilient, pressure(1)).legitimacy > stressed.legitimacy
    recovered = stressed
    for _ in range(12):
        recovered = advance_governance(recovered, pressure())
    assert recovered.legitimacy > stressed.legitimacy
    assert recovered.execution_capacity > stressed.execution_capacity
    assert recovered.internal_resistance < stressed.internal_resistance
    assert recovered.subject_id == state.subject_id
    renamed = state.model_copy(
        update={
            "institution": state.institution.model_copy(
                update={"key": "arbitrary-label"},
            )
        }
    )
    assert advance_governance(renamed, pressure(1)).legitimacy == stressed.legitimacy


@pytest.mark.parametrize(
    "field,value",
    [
        ("legitimacy", 0.1),
        ("execution_capacity", 0.1),
        ("internal_resistance", 0.9),
    ],
)
def test_execution_is_weakest_constraint(field: str, value: float) -> None:
    _, state = fixture()
    assert execution_strength(state.model_copy(update={field: value})) == pytest.approx(0.1)


def test_same_tick_integration_replay_and_causal_history() -> None:
    world, state = fixture()
    engine = SimulationEngine((GovernanceDomain(), EconomyDomain(), PopulationDomain()))
    first = engine.step(world)
    assert first == engine.step(WorldState.model_validate_json(world.model_dump_json()))
    context = TickContext(
        time=first.world.time,
        phase=TickPhase.GOVERNANCE,
        prior_events=tuple(e for e in first.events if e.source != "governance"),
        queued_inputs=(),
    )
    observed = governance_pressure(first.world, state, context)
    assert observed.food_shortage_severity > 0
    assert first.world.governance[0] == advance_governance(state, observed)
    event = next(e for e in first.events if e.source == "governance")
    assert event.cause_event_ids
    history = EventHistory(first.events)
    assert history.why(event.id)[-1].event_id == event.id
    assert any(e.source == "economy" for e in history.causal_chain(event.id)[:-1])
    for cause in history.causal_chain(event.id)[:-1]:
        assert any(c.target == state.region_id for c in cause.changes)
    assert all(c in first.changes for c in event.changes)
    inputs = population_food_pressure_inputs(first.world, events=first.events)
    second = engine.step(first.world, inputs=inputs)
    assert second == engine.step(first.world, inputs=inputs)
    assert second.world.governance[0].subject_id == state.subject_id
    # Existing region-scoped economy -> population boundary remains composable.
    for event in second.events:
        if event.source == "governance":
            EventHistory((*first.events, *second.events)).why(event.id)


def test_region_and_field_scoped_causes_and_no_cross_domain_mutation() -> None:
    world, state = fixture()
    assert world.geography is not None
    other = world.geography.region("fertile-lowlands").id
    inputs = tuple(
        SimulationInput(
            source="test",
            kind=label,
            reason=label,
            subjects=(target,),
            changes=(
                SimulationChange(
                    source="population",
                    key=key,
                    delta=-0.8,
                    reason=label,
                    target=target,
                ),
            ),
        )
        for target, key, label in (
            (state.region_id, "population.social_confidence", "relevant"),
            (other, "population.social_confidence", "other-region"),
            (state.region_id, "population.health", "other-field"),
        )
    )
    result = SimulationEngine((PopulationDomain(), GovernanceDomain())).step(world, inputs=inputs)
    event = next(e for e in result.events if e.source == "governance")
    relevant = next(e for e in result.events if e.kind == "relevant")
    unrelated = {e.id for e in result.events if e.kind in {"other-region", "other-field"}}
    assert relevant.id in event.cause_event_ids
    assert not unrelated.intersection(event.cause_event_ids)
    for change in event.changes:
        reduced = GovernanceDomain().apply_change(world, change)
        assert reduced.population is world.population and reduced.economy is world.economy
        assert reduced.geography is world.geography


@pytest.mark.parametrize(
    "updates",
    [
        {"source": "economy"},
        {"key": "population.total"},
        {"target": None},
        {"target": EntityId(kind="society", value=UUID(int=0))},
        {"delta": 2},
    ],
)
def test_reducer_rejects_invalid_changes(updates: dict[str, object]) -> None:
    world, state = fixture()
    change = SimulationChange.model_validate(
        {
            "source": "governance",
            "key": "governance.legitimacy",
            "delta": -0.1,
            "target": state.subject_id,
            "reason": "test",
            **updates,
        }
    )
    with pytest.raises(ValueError):
        GovernanceDomain().apply_change(world, change)


def test_validation_and_atomic_failure() -> None:
    world, state = fixture()
    for value in (float("nan"), float("inf"), -0.1, 1.1):
        with pytest.raises(ValidationError):
            GovernanceState.model_validate({**state.model_dump(), "legitimacy": value})
    with pytest.raises(ValueError, match="unique"):
        WorldState.model_validate({**world.model_dump(), "governance": (state, state)})
    with pytest.raises(ValueError, match="already"):
        initialize_governance(world, states=(state,))
    with pytest.raises(ValueError):
        WorldState.model_validate({**world.model_dump(), "economy": None})
    bad = SimulationInput(
        source="test",
        kind="test",
        reason="test",
        changes=(
            SimulationChange(
                source="governance",
                key="governance.legitimacy",
                target=state.subject_id,
                delta=-0.1,
                reason="valid",
            ),
            SimulationChange(
                source="governance",
                key="invalid",
                target=state.subject_id,
                delta=-0.1,
                reason="invalid",
            ),
        ),
    )
    with pytest.raises(TickExecutionError):
        SimulationEngine((GovernanceDomain(),)).step(world, inputs=(bad,))
    assert world.governance == (state,)


@pytest.mark.parametrize("rate", [0, 1])
def test_adaptation_endpoints_and_bounds(rate: float) -> None:
    _, state = fixture()
    initial = state.model_copy(
        update={
            "institution": state.institution.model_copy(
                update={"adaptation_rate": rate},
            )
        }
    )
    current = initial
    for level in (1, 1, 0, 0):
        current = advance_governance(current, pressure(level))
        assert all(
            0 <= getattr(current, f) <= 1
            for f in (
                "legitimacy",
                "execution_capacity",
                "internal_resistance",
            )
        )
    if rate == 0:
        assert current == initial
