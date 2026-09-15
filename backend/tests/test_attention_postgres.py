import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
import pytest

from cliova.application.attention import (
    AttentionItem,
    AttentionPriority,
    AttentionProjection,
    DecisionOpportunity,
    DecisionOpportunityStatus,
    DecisionResponseError,
)
from cliova.application.development import create_development_world, create_simulation_engine
from cliova.application.scheduling import ScheduledTickService
from cliova.infrastructure.persistence.attention import PostgresAttentionWorldRepository
from cliova.infrastructure.persistence.migrations import apply_migrations
from cliova.simulation.domains.directives import directive_input
from cliova.simulation.types import SimulationInput, TickResult, WorldState

pytestmark = pytest.mark.integration


class FixtureAttentionProducer:
    def __init__(self, *, expires_at_tick: int | None = None) -> None:
        self.expires_at_tick = expires_at_tick

    def produce(self, before: WorldState, result: TickResult) -> AttentionProjection:
        del before
        if result.world.time.tick != 1:
            return AttentionProjection()
        target = result.world.governance[0].subject_id
        world_id = result.world.id.value
        related_events = tuple(event.id for event in result.events[:1])
        return AttentionProjection(
            attention_items=(
                AttentionItem(
                    id=uuid5(world_id, "test-attention"),
                    world_id=world_id,
                    target_subject=target,
                    created_tick=1,
                    created_year=result.world.time.year,
                    category="test-attention",
                    priority=AttentionPriority.IMPORTANT,
                    context="A committed fact deserves attention.",
                    related_event_ids=related_events,
                    related_subjects=(target,),
                ),
            ),
            decision_opportunities=(
                DecisionOpportunity(
                    id=uuid5(world_id, "test-decision"),
                    world_id=world_id,
                    target_subject=target,
                    created_tick=1,
                    created_year=result.world.time.year,
                    category="test-decision",
                    context="Future intent may be changed.",
                    related_event_ids=related_events,
                    related_subjects=(target,),
                    earliest_effect_tick=2,
                    expires_at_tick=self.expires_at_tick,
                    default_behavior="Take no new action; keep existing intent unchanged.",
                    response_intent="strengthen_food_reserves",
                    status=DecisionOpportunityStatus.OPEN,
                ),
            ),
        )


class RaisingProducer:
    def produce(self, before: WorldState, result: TickResult) -> AttentionProjection:
        del before, result
        raise RuntimeError("attention projection failed")


def _database_url() -> str:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    return url


def _fresh_repository(
    *, producer: FixtureAttentionProducer | RaisingProducer
) -> tuple[str, PostgresAttentionWorldRepository, UUID]:
    database_url = _database_url()
    apply_migrations(database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute("TRUNCATE TABLE cliova_worlds RESTART IDENTITY CASCADE")
    repository = PostgresAttentionWorldRepository(database_url, producer=producer)
    world = create_development_world(
        seed=64,
        world_key=str(uuid5(NAMESPACE_URL, "attention-db")),
    )
    repository.create_world(world)
    return database_url, repository, world.id.value


def _response_value(
    repository: PostgresAttentionWorldRepository, world_id: UUID
) -> SimulationInput:
    world = repository.load_world(world_id)
    return directive_input(
        author="player:test",
        target_subject=world.governance[0].subject_id,
        intent="strengthen_food_reserves",
        priority="normal",
    )


def _run_responded_replay() -> tuple[
    WorldState,
    UUID,
    DecisionOpportunityStatus,
    int | None,
    UUID | None,
]:
    _, repository, world_id = _fresh_repository(producer=FixtureAttentionProducer())
    service = ScheduledTickService(create_simulation_engine(), repository)
    service.advance_manual(world_id, expected_tick=0)
    opportunity = repository.list_decision_opportunities(world_id)[0]
    repository.queue_decision_response(
        world_id,
        opportunity_id=opportunity.id,
        value=_response_value(repository, world_id),
    )
    result = service.advance_manual(world_id, expected_tick=1)
    responded = repository.list_decision_opportunities(world_id)[0]
    return (
        result.world,
        responded.id,
        responded.status,
        responded.response_submitted_tick,
        responded.response_directive_id,
    )


def _run_expired_replay() -> tuple[
    WorldState,
    UUID,
    DecisionOpportunityStatus,
    int | None,
]:
    _, repository, world_id = _fresh_repository(
        producer=FixtureAttentionProducer(expires_at_tick=2)
    )
    service = ScheduledTickService(create_simulation_engine(), repository)
    service.advance_manual(world_id, expected_tick=0)
    service.advance_manual(world_id, expected_tick=1)
    expired = repository.list_decision_opportunities(world_id)[0]
    return result_tuple(repository.load_world(world_id), expired)


def result_tuple(
    world: WorldState,
    opportunity: DecisionOpportunity,
) -> tuple[WorldState, UUID, DecisionOpportunityStatus, int | None]:
    return (
        world,
        opportunity.id,
        opportunity.status,
        opportunity.expires_at_tick,
    )


def test_unanswered_opportunity_never_blocks_tick_and_expires_deterministically() -> None:
    database_url, repository, world_id = _fresh_repository(
        producer=FixtureAttentionProducer(expires_at_tick=2)
    )
    service = ScheduledTickService(create_simulation_engine(), repository)

    first = service.advance_manual(world_id, expected_tick=0)
    assert first.world.time.tick == 1
    assert len(repository.list_attention_items(world_id)) == 1
    opportunity = repository.list_decision_opportunities(world_id)[0]
    assert opportunity.status is DecisionOpportunityStatus.OPEN

    second = service.advance_manual(world_id, expected_tick=1)
    assert second.world.time.tick == 2
    expired = repository.list_decision_opportunities(world_id)[0]
    assert expired.status is DecisionOpportunityStatus.EXPIRED
    assert expired.response_queue_id is None
    assert repository.load_pending_inputs(world_id) == ()

    restarted = PostgresAttentionWorldRepository(
        database_url, producer=FixtureAttentionProducer(expires_at_tick=2)
    )
    assert restarted.load_world(world_id).time.tick == 2
    assert restarted.list_attention_items(world_id) == repository.list_attention_items(world_id)
    assert restarted.list_decision_opportunities(world_id) == (expired,)


def test_response_reuses_future_directive_input_and_survives_restart() -> None:
    database_url, repository, world_id = _fresh_repository(producer=FixtureAttentionProducer())
    service = ScheduledTickService(create_simulation_engine(), repository)
    service.advance_manual(world_id, expected_tick=0)
    opportunity = repository.list_decision_opportunities(world_id)[0]

    queued = repository.queue_decision_response(
        world_id,
        opportunity_id=opportunity.id,
        value=_response_value(repository, world_id),
    )
    assert queued.submitted_tick == 2
    responded = repository.list_decision_opportunities(world_id)[0]
    assert responded.status is DecisionOpportunityStatus.RESPONDED
    assert responded.response_queue_id == queued.queue_id
    assert responded.response_directive_id is None

    with pytest.raises(DecisionResponseError) as duplicate:
        repository.queue_decision_response(
            world_id,
            opportunity_id=opportunity.id,
            value=_response_value(repository, world_id),
        )
    assert duplicate.value.code == "decision_opportunity_already_responded"

    result = service.advance_manual(world_id, expected_tick=1)
    linked = repository.list_decision_opportunities(world_id)[0]
    assert linked.response_directive_id is not None
    assert any(
        directive.id == linked.response_directive_id for directive in result.world.directives
    )

    restarted = PostgresAttentionWorldRepository(
        database_url,
        producer=FixtureAttentionProducer(),
    )
    assert restarted.list_decision_opportunities(world_id)[0] == linked


def test_responded_lifecycle_replays_deterministically() -> None:
    first = _run_responded_replay()
    second = _run_responded_replay()

    assert first == second
    assert first[2] is DecisionOpportunityStatus.RESPONDED
    assert first[3] == 2
    assert first[4] is not None


def test_non_response_expiry_replays_deterministically() -> None:
    first = _run_expired_replay()
    second = _run_expired_replay()

    assert first == second
    assert first[2] is DecisionOpportunityStatus.EXPIRED
    assert first[3] == 2


def test_response_after_tick_input_freeze_is_assigned_to_next_future_tick() -> None:
    _, repository, world_id = _fresh_repository(producer=FixtureAttentionProducer())
    engine = create_simulation_engine()
    ScheduledTickService(engine, repository).advance_manual(world_id, expected_tick=0)
    opportunity = repository.list_decision_opportunities(world_id)[0]

    claim = repository.claim_manual_tick(
        world_id,
        expected_tick=1,
        now=datetime.now(UTC),
    )
    resolver_entered = Event()
    release_resolver = Event()
    response_started = Event()

    def blocking_resolver(world: WorldState, inputs: tuple[SimulationInput, ...]) -> TickResult:
        resolver_entered.set()
        assert release_resolver.wait(timeout=5)
        return engine.step(world, inputs=inputs)

    def queue_late_response():
        response_started.set()
        return repository.queue_decision_response(
            world_id,
            opportunity_id=opportunity.id,
            value=_response_value(repository, world_id),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        tick_future = executor.submit(
            lambda: repository.execute_claimed_tick(
                claim,
                resolver=blocking_resolver,
                next_eligible_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        assert resolver_entered.wait(timeout=5)
        response_future = executor.submit(queue_late_response)
        assert response_started.wait(timeout=5)
        time.sleep(0.05)
        assert not response_future.done()
        release_resolver.set()
        current_tick = tick_future.result(timeout=5)
        queued = response_future.result(timeout=5)

    assert current_tick.world.time.tick == 2
    assert current_tick.world.directives == ()
    assert queued.submitted_tick == 3

    future = ScheduledTickService(engine, repository).advance_manual(
        world_id,
        expected_tick=2,
    )
    assert any(directive.submitted_tick == 3 for directive in future.world.directives)


def test_tick_failure_rolls_back_attention_created_in_same_transaction() -> None:
    _, repository, world_id = _fresh_repository(producer=RaisingProducer())
    service = ScheduledTickService(create_simulation_engine(), repository)

    with pytest.raises(RuntimeError, match="attention projection failed"):
        service.advance_manual(world_id, expected_tick=0)

    assert repository.load_world(world_id).time.tick == 0
    assert repository.list_attention_items(world_id) == ()
    assert repository.list_decision_opportunities(world_id) == ()
