from uuid import uuid4

from cliova.application.attention import (
    AttentionPriority,
    DecisionOpportunityStatus,
    FoodShortageAttentionProducer,
)
from cliova.application.development import create_development_world
from cliova.simulation.types import (
    GovernanceState,
    SimulationChange,
    SimulationEvent,
    SimulationTime,
    TickResult,
    entity_id,
)


def _availability_result(*, kind: str = "resource-shortage") -> tuple[object, TickResult]:
    before = create_development_world(seed=64, world_key="attention-unit")
    region = before.governance[0].region_id
    time = SimulationTime(year=1, tick=1)
    after = before.model_copy(update={"time": time})
    event = SimulationEvent(
        id=uuid4(),
        time=time,
        source="economy",
        kind=kind,
        reason="Food availability changed materially.",
        subjects=(region,),
        changes=(
            SimulationChange(
                source="economy",
                key="economy.food.shortage_severity",
                delta=0.4 if kind == "resource-shortage" else -0.4,
                reason="Food availability changed materially.",
                target=region,
            ),
        ),
    )
    return before, TickResult(
        world=after,
        phases=("economy",),
        events=(event,),
    )


def test_shortage_creates_notice_and_future_opportunity_without_simulation_change() -> None:
    before, result = _availability_result()

    projection = FoodShortageAttentionProducer().produce(before, result)

    assert result.world.time.tick == 1
    assert len(projection.attention_items) == 1
    assert len(projection.decision_opportunities) == 1
    notice = projection.attention_items[0]
    opportunity = projection.decision_opportunities[0]
    assert notice.priority is AttentionPriority.IMPORTANT
    assert notice.related_event_ids == (result.events[0].id,)
    assert opportunity.status is DecisionOpportunityStatus.OPEN
    assert opportunity.earliest_effect_tick == 2
    assert opportunity.expires_at_tick is None
    assert opportunity.response_intent == "strengthen_food_reserves"
    assert "continue unchanged" in opportunity.default_behavior


def test_projection_ids_are_deterministic_for_replay() -> None:
    before, result = _availability_result()
    producer = FoodShortageAttentionProducer()

    left = producer.produce(before, result)
    right = producer.produce(before, result)

    assert left == right
    assert left.attention_items[0].id == right.attention_items[0].id
    assert left.decision_opportunities[0].id == right.decision_opportunities[0].id


def test_recovery_is_attention_only() -> None:
    before, result = _availability_result(kind="resource-recovery")

    projection = FoodShortageAttentionProducer().produce(before, result)

    assert len(projection.attention_items) == 1
    assert projection.attention_items[0].priority is AttentionPriority.INFORMATIONAL
    assert projection.decision_opportunities == ()


def test_one_event_can_target_multiple_societies_without_a_player_barrier() -> None:
    before, result = _availability_result()
    original = result.world.governance[0]
    second_subject = entity_id(result.world.id, "polity", "second-polity")
    second = GovernanceState(
        subject_id=second_subject,
        region_id=original.region_id,
        institution=original.institution,
        legitimacy=original.legitimacy,
        execution_capacity=original.execution_capacity,
        internal_resistance=original.internal_resistance,
    )
    multi_world = result.world.model_copy(update={"governance": (original, second)})
    multi_result = result.model_copy(update={"world": multi_world})

    projection = FoodShortageAttentionProducer().produce(before, multi_result)

    assert len(projection.attention_items) == 2
    assert len(projection.decision_opportunities) == 2
    assert {item.target_subject for item in projection.decision_opportunities} == {
        original.subject_id,
        second_subject,
    }
