import os
from uuid import UUID, uuid5

import httpx2
import psycopg
import pytest

from cliova.api.dependencies import get_repository
from cliova.application.attention import (
    AttentionItem,
    AttentionPriority,
    AttentionProjection,
    DecisionOpportunity,
    DecisionOpportunityStatus,
)
from cliova.application.development import create_development_world, create_simulation_engine
from cliova.application.scheduling import ScheduledTickService
from cliova.infrastructure.persistence.attention import PostgresAttentionWorldRepository
from cliova.infrastructure.persistence.migrations import apply_migrations
from cliova.main import create_app
from cliova.simulation.types import TickResult, WorldState

pytestmark = pytest.mark.integration


class ApiFixtureProducer:
    def __init__(self, *, expires_at_tick: int | None = None) -> None:
        self.expires_at_tick = expires_at_tick

    def produce(self, before: WorldState, result: TickResult) -> AttentionProjection:
        del before
        if result.world.time.tick != 1:
            return AttentionProjection()
        world_id = result.world.id.value
        target = result.world.governance[0].subject_id
        related_event_ids = tuple(event.id for event in result.events[:1])
        return AttentionProjection(
            attention_items=(
                AttentionItem(
                    id=uuid5(world_id, "api-attention"),
                    world_id=world_id,
                    target_subject=target,
                    created_tick=1,
                    created_year=result.world.time.year,
                    category="api-attention",
                    priority=AttentionPriority.IMPORTANT,
                    context="An authoritative fact deserves attention.",
                    related_event_ids=related_event_ids,
                    related_subjects=(target,),
                ),
            ),
            decision_opportunities=(
                DecisionOpportunity(
                    id=uuid5(world_id, "api-decision"),
                    world_id=world_id,
                    target_subject=target,
                    created_tick=1,
                    created_year=result.world.time.year,
                    category="api-decision",
                    context="Future intent may be changed.",
                    related_event_ids=related_event_ids,
                    related_subjects=(target,),
                    earliest_effect_tick=2,
                    expires_at_tick=self.expires_at_tick,
                    default_behavior="Keep existing intent unchanged.",
                    response_intent="strengthen_food_reserves",
                    status=DecisionOpportunityStatus.OPEN,
                ),
            ),
        )


def _database_url() -> str:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    return url


def _repository(
    *, expires_at_tick: int | None = None
) -> tuple[PostgresAttentionWorldRepository, UUID]:
    database_url = _database_url()
    apply_migrations(database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute("TRUNCATE TABLE cliova_worlds RESTART IDENTITY CASCADE")
    repository = PostgresAttentionWorldRepository(
        database_url,
        producer=ApiFixtureProducer(expires_at_tick=expires_at_tick),
    )
    world = create_development_world(seed=164, world_key="attention-api")
    repository.create_world(world)
    return repository, world.id.value


@pytest.mark.anyio
async def test_api_queries_attention_separately_and_reuses_directive_submission() -> None:
    repository, world_id = _repository()
    ScheduledTickService(create_simulation_engine(), repository).advance_manual(
        world_id,
        expected_tick=0,
    )
    opportunity = repository.list_decision_opportunities(world_id)[0]

    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        attention = await client.get(f"/api/v1/worlds/{world_id}/attention-items")
        decisions = await client.get(
            f"/api/v1/worlds/{world_id}/decision-opportunities"
        )
        history = await client.get(f"/api/v1/worlds/{world_id}/history")

        assert attention.status_code == decisions.status_code == history.status_code == 200
        assert attention.json()["items"][0]["id"] != history.json()["events"][0]["id"]
        assert decisions.json()["opportunities"][0]["id"] == str(opportunity.id)
        assert decisions.json()["opportunities"][0]["earliest_effect_tick"] == 2

        response = await client.post(
            f"/api/v1/worlds/{world_id}/directives",
            json={
                "author": "player:test",
                "target": {
                    "kind": opportunity.target_subject.kind,
                    "id": str(opportunity.target_subject.value),
                },
                "intent": opportunity.response_intent,
                "priority": "normal",
                "decision_opportunity_id": str(opportunity.id),
            },
        )
        assert response.status_code == 202
        assert response.json()["submitted_tick"] == 2

        open_after = await client.get(
            f"/api/v1/worlds/{world_id}/decision-opportunities"
        )
        responded = await client.get(
            f"/api/v1/worlds/{world_id}/decision-opportunities",
            params={"status": "responded"},
        )
        assert open_after.json()["opportunities"] == []
        assert (
            responded.json()["opportunities"][0]["response_queue_id"]
            == response.json()["queue_id"]
        )

        duplicate = await client.post(
            f"/api/v1/worlds/{world_id}/directives",
            json={
                "author": "player:test",
                "target": {
                    "kind": opportunity.target_subject.kind,
                    "id": str(opportunity.target_subject.value),
                },
                "intent": opportunity.response_intent,
                "priority": "normal",
                "decision_opportunity_id": str(opportunity.id),
            },
        )
        assert duplicate.status_code == 409
        assert (
            duplicate.json()["error"]["code"]
            == "decision_opportunity_already_responded"
        )


@pytest.mark.anyio
async def test_api_returns_stable_error_for_expired_opportunity() -> None:
    repository, world_id = _repository(expires_at_tick=2)
    service = ScheduledTickService(create_simulation_engine(), repository)
    service.advance_manual(world_id, expected_tick=0)
    opportunity = repository.list_decision_opportunities(world_id)[0]
    service.advance_manual(world_id, expected_tick=1)

    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repository
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/api/v1/worlds/{world_id}/directives",
            json={
                "author": "player:test",
                "target": {
                    "kind": opportunity.target_subject.kind,
                    "id": str(opportunity.target_subject.value),
                },
                "intent": opportunity.response_intent,
                "priority": "normal",
                "decision_opportunity_id": str(opportunity.id),
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "decision_opportunity_expired"
