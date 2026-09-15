import pytest

from cliova.simulation.domains.directives import (
    DirectiveAwareEconomyDomain,
    DirectiveDomain,
    directive_input,
)
from cliova.simulation.domains.economy import initialize_economy
from cliova.simulation.domains.politics import GovernanceDomain, initialize_governance
from cliova.simulation.domains.population import initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine
from cliova.simulation.history import EventHistory
from cliova.simulation.types import (
    EntityId,
    GovernanceState,
    InstitutionProfile,
    SimulationInput,
    WorldState,
    entity_id,
)


def configured_world(
    *,
    execution_capacity: float = 0.9,
    legitimacy: float = 0.9,
    resistance: float = 0.1,
    seed: int = 91,
    world_key: str = "directive-test",
) -> tuple[WorldState, EntityId]:
    world = initialize_economy(
        initialize_population(create_starter_world(seed=seed, world_key=world_key))
    )
    assert world.geography is not None
    subject = entity_id(world.id, "society", "river-council")
    governance = GovernanceState(
        subject_id=subject,
        region_id=world.geography.region("fertile-lowlands").id,
        institution=InstitutionProfile(
            key="neutral-coordination",
            coordination_efficiency=1.0,
            stress_resilience=1.0,
            adaptation_rate=0.0,
        ),
        legitimacy=legitimacy,
        execution_capacity=execution_capacity,
        internal_resistance=resistance,
    )
    return initialize_governance(world, states=(governance,)), subject


def directive_engine() -> SimulationEngine:
    return SimulationEngine(
        (
            DirectiveAwareEconomyDomain(),
            GovernanceDomain(),
            DirectiveDomain(),
        )
    )


def submit(target: EntityId, *, author: str = "player:one") -> SimulationInput:
    return directive_input(
        author=author,
        target_subject=target,
        intent="strengthen_food_reserves",
        priority="normal",
    )


def test_submission_is_queued_without_direct_state_replacement() -> None:
    world, subject = configured_world()
    queued = submit(subject)
    assert queued.changes == ()

    tick = directive_engine().step(world, inputs=(queued,))

    assert len(tick.world.directives) == 1
    directive = tick.world.directives[0]
    assert directive.author == "player:one"
    assert directive.target_subject == subject
    assert directive.status == "queued"
    assert directive.progress == 0.0

    submitted = next(event for event in tick.events if event.source == "player:one")
    queued_event = next(event for event in tick.events if event.kind == "directive-queued")
    assert queued_event.cause_event_ids == (submitted.id,)
    assert directive.id == submitted.id == directive.submission_event_id


def test_same_queued_directive_transitions_deterministically() -> None:
    world, subject = configured_world()
    first = directive_engine().step(world, inputs=(submit(subject),))

    left = directive_engine().step(first.world)
    right = directive_engine().step(WorldState.model_validate_json(first.world.model_dump_json()))

    assert left == right
    assert left.world.directives[0].status == "accepted"
    assert left.world.directives[0].progress == pytest.approx(0.36)


def test_strong_governance_executes_faster_than_weak_governance() -> None:
    strong, strong_subject = configured_world(
        execution_capacity=0.9, legitimacy=0.9, resistance=0.1
    )
    weak, weak_subject = configured_world(
        execution_capacity=0.4, legitimacy=0.4, resistance=0.4
    )

    strong_queued = directive_engine().step(strong, inputs=(submit(strong_subject),))
    weak_queued = directive_engine().step(weak, inputs=(submit(weak_subject),))
    strong_result = directive_engine().step(strong_queued.world)
    weak_result = directive_engine().step(weak_queued.world)

    strong_directive = strong_result.world.directives[0]
    weak_directive = weak_result.world.directives[0]
    assert strong_directive.status == "accepted"
    assert weak_directive.status == "partial"
    assert strong_directive.progress > weak_directive.progress
    assert weak_directive.progress == pytest.approx(0.16)


@pytest.mark.parametrize(
    ("capacity", "legitimacy", "resistance", "expected"),
    (
        (0.1, 0.9, 0.1, "delayed"),
        (0.9, 0.9, 0.8, "resisted"),
    ),
)
def test_blocked_directives_explain_delay_or_resistance(
    capacity: float, legitimacy: float, resistance: float, expected: str
) -> None:
    world, subject = configured_world(
        execution_capacity=capacity,
        legitimacy=legitimacy,
        resistance=resistance,
    )
    queued = directive_engine().step(world, inputs=(submit(subject),))
    result = directive_engine().step(queued.world)

    directive = result.world.directives[0]
    assert directive.status == expected
    assert directive.progress == 0.0
    event = next(event for event in result.events if event.kind == f"directive-{expected}")
    explanation = next(item for item in result.explanations if item.source == "directives")
    assert expected in event.reason.lower()
    assert expected in explanation.message.lower()


def test_missing_governance_target_fails_with_explanation() -> None:
    world, _ = configured_world()
    missing = entity_id(world.id, "society", "missing-target")
    queued = directive_engine().step(world, inputs=(submit(missing),))
    result = directive_engine().step(queued.world)

    directive = result.world.directives[0]
    assert directive.status == "failed"
    assert directive.progress == 0.0
    event = next(event for event in result.events if event.kind == "directive-failed")
    assert "no authoritative governance state" in event.reason


def test_partial_execution_records_real_progress_and_reason() -> None:
    world, subject = configured_world(execution_capacity=0.5, legitimacy=0.5, resistance=0.2)
    queued = directive_engine().step(world, inputs=(submit(subject),))
    result = directive_engine().step(queued.world)

    directive = result.world.directives[0]
    assert directive.status == "partial"
    assert 0.0 < directive.progress < 1.0
    event = next(event for event in result.events if event.kind == "directive-partial")
    assert "execution strength" in event.reason
    assert "economic feasibility" in event.reason


def test_food_reserve_directive_progresses_over_multiple_ticks_to_completion() -> None:
    world, subject = configured_world()
    run = directive_engine().run(
        world,
        years=4,
        inputs=((submit(subject),), (), (), ()),
    )

    statuses = [tick.world.directives[0].status for tick in run.ticks]
    progress = [tick.world.directives[0].progress for tick in run.ticks]
    assert statuses == ["queued", "accepted", "accepted", "completed"]
    assert progress == pytest.approx([0.0, 0.36, 0.72, 1.0])


def test_effects_are_applied_by_owning_economy_and_directive_domains() -> None:
    world, subject = configured_world()
    engine = directive_engine()
    first = engine.step(world, inputs=(submit(subject),))
    second = engine.step(first.world)
    third = engine.step(second.world)

    governance = second.world.governance
    economy = second.world.economy
    directive_change = next(change for change in second.changes if change.source == "directives")
    reduced = DirectiveDomain().apply_change(first.world, directive_change)
    assert reduced.governance == first.world.governance
    assert reduced.economy == first.world.economy

    assert economy is not None and third.world.economy is not None
    region_id = governance[0].region_id
    before_food = economy.region(region_id).resource("food")
    after_food = third.world.economy.region(region_id).resource("food")
    assert after_food.production_capacity > before_food.production_capacity
    assert any(
        change.source == "economy"
        and change.target == region_id
        and change.key == "economy.food.production_capacity"
        for change in third.changes
    )
    assert all(
        change.source == "directives"
        for event in third.events
        if event.source == "directives"
        for change in event.changes
    )


def test_directive_history_links_outcome_to_submission_and_explains_it() -> None:
    world, subject = configured_world()
    first = directive_engine().step(world, inputs=(submit(subject),))
    second = directive_engine().step(first.world)
    history = EventHistory((*first.events, *second.events))

    outcome = next(event for event in second.events if event.kind == "directive-accepted")
    submission = next(event for event in first.events if event.source == "player:one")
    chain = history.causal_chain(outcome.id)
    assert submission in chain
    assert chain[-1] == outcome
    explanations = history.why(outcome.id)
    assert explanations[-1].event_id == outcome.id
    assert explanations[-1].cause_event_ids == outcome.cause_event_ids


def test_replay_equivalence_for_same_ordered_directive_sequence() -> None:
    world, subject = configured_world(seed=97, world_key="directive-replay")
    inputs = ((submit(subject),), (), (), ())

    first = directive_engine().run(world, years=4, inputs=inputs)
    second = directive_engine().run(
        WorldState.model_validate_json(world.model_dump_json()),
        years=4,
        inputs=inputs,
    )

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
