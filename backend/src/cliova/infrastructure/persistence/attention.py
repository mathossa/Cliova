"""PostgreSQL adapter for non-blocking attention and decision-opportunity state."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from cliova.application.attention import (
    AttentionItem,
    AttentionPriority,
    AttentionProducer,
    DecisionOpportunity,
    DecisionOpportunityStatus,
    DecisionResponseError,
    FoodShortageAttentionProducer,
)
from cliova.application.persistence import QueuedSimulationInput
from cliova.infrastructure.persistence.postgres import (
    DbConnection,
    PersistenceError,
    WorldNotFoundError,
    _encode_input,
    _INPUT_PAYLOAD_VERSION,
)
from cliova.infrastructure.persistence.scheduling import PostgresScheduledWorldRepository
from cliova.simulation.types import EntityId, SimulationInput, TickResult, WorldState


class PostgresAttentionWorldRepository(PostgresScheduledWorldRepository):
    """Persist player-facing lifecycle state without changing authoritative tick semantics."""

    def __init__(
        self,
        database_url: str,
        *,
        producer: AttentionProducer | None = None,
    ) -> None:
        super().__init__(database_url)
        self._attention_producer = producer or FoodShortageAttentionProducer()

    def list_attention_items(self, world_id: UUID) -> tuple[AttentionItem, ...]:
        with self._connect() as connection:
            self._require_world(connection, world_id)
            rows = connection.execute(
                """
                SELECT attention_id, world_id, target_kind, target_id, created_tick, created_year,
                       category, priority, context, related_event_ids, related_subjects
                  FROM cliova_attention_items
                 WHERE world_id = %s
                 ORDER BY created_tick DESC, attention_id
                """,
                (world_id,),
            ).fetchall()
        return tuple(_attention_item(row) for row in rows)

    def list_decision_opportunities(
        self, world_id: UUID
    ) -> tuple[DecisionOpportunity, ...]:
        with self._connect() as connection:
            self._require_world(connection, world_id)
            rows = connection.execute(
                """
                SELECT opportunity_id, world_id, target_kind, target_id,
                       created_tick, created_year, category, context, related_event_ids,
                       related_subjects, earliest_effect_tick, expires_at_tick,
                       default_behavior, response_intent, status, response_queue_id,
                       response_submitted_tick, response_directive_id
                  FROM cliova_decision_opportunities
                 WHERE world_id = %s
                 ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'responded' THEN 1 ELSE 2 END,
                          created_tick DESC, opportunity_id
                """,
                (world_id,),
            ).fetchall()
        return tuple(_decision_opportunity(row) for row in rows)

    def queue_decision_response(
        self,
        world_id: UUID,
        *,
        opportunity_id: UUID,
        value: SimulationInput,
    ) -> QueuedSimulationInput:
        """Atomically validate the opportunity and assign its directive to a future input window."""

        if value.directive is None or len(value.subjects) != 1:
            raise DecisionResponseError(
                "invalid_decision_response", "Decision responses must contain one directive target."
            )
        target = value.subjects[0]
        if target.kind not in {"society", "polity"}:
            raise DecisionResponseError(
                "invalid_decision_response", "Decision responses must target a society or polity."
            )

        payload = _encode_input(value)
        with self._connect() as connection:
            world_row = connection.execute(
                "SELECT current_tick FROM cliova_worlds WHERE world_id = %s FOR UPDATE",
                (world_id,),
            ).fetchone()
            if world_row is None:
                raise WorldNotFoundError(f"world {world_id} does not exist")

            row = connection.execute(
                """
                SELECT opportunity_id, world_id, target_kind, target_id,
                       earliest_effect_tick, expires_at_tick, response_intent, status
                  FROM cliova_decision_opportunities
                 WHERE world_id = %s AND opportunity_id = %s
                 FOR UPDATE
                """,
                (world_id, opportunity_id),
            ).fetchone()
            if row is None:
                raise DecisionResponseError(
                    "decision_opportunity_not_found", "Decision opportunity does not exist."
                )
            if row["status"] != DecisionOpportunityStatus.OPEN.value:
                code = (
                    "decision_opportunity_expired"
                    if row["status"] == DecisionOpportunityStatus.EXPIRED.value
                    else "decision_opportunity_already_responded"
                )
                raise DecisionResponseError(code, f"Decision opportunity is {row['status']}.")

            expected_target = EntityId.model_validate(
                {"kind": str(row["target_kind"]), "value": cast(UUID, row["target_id"])}
            )
            if target != expected_target:
                raise DecisionResponseError(
                    "decision_response_target_mismatch",
                    "Directive target does not match the decision opportunity target.",
                )
            if value.directive.intent != str(row["response_intent"]):
                raise DecisionResponseError(
                    "decision_response_action_mismatch",
                    "Directive action is not valid for this decision opportunity.",
                )

            submitted_tick = int(world_row["current_tick"]) + 1
            earliest = int(row["earliest_effect_tick"])
            expires_at = cast(int | None, row["expires_at_tick"])
            if submitted_tick < earliest:
                raise DecisionResponseError(
                    "decision_response_too_early",
                    f"Decision response cannot take effect before tick {earliest}.",
                )
            if expires_at is not None and submitted_tick > expires_at:
                connection.execute(
                    """
                    UPDATE cliova_decision_opportunities
                       SET status = 'expired'
                     WHERE opportunity_id = %s AND status = 'open'
                    """,
                    (opportunity_id,),
                )
                raise DecisionResponseError(
                    "decision_opportunity_expired",
                    f"Decision opportunity expired after tick {expires_at}.",
                )

            inserted = connection.execute(
                """
                INSERT INTO cliova_queued_inputs (
                    world_id, submitted_tick, payload_schema_version, input_json
                ) VALUES (%s, %s, %s, %s)
                RETURNING queue_id
                """,
                (world_id, submitted_tick, _INPUT_PAYLOAD_VERSION, Jsonb(payload)),
            ).fetchone()
            if inserted is None:
                raise PersistenceError("queued decision response returned no identity")
            queue_id = int(inserted["queue_id"])
            updated = connection.execute(
                """
                UPDATE cliova_decision_opportunities
                   SET status = 'responded',
                       response_queue_id = %s,
                       response_submitted_tick = %s
                 WHERE opportunity_id = %s AND status = 'open'
                """,
                (queue_id, submitted_tick, opportunity_id),
            )
            if updated.rowcount != 1:
                raise DecisionResponseError(
                    "decision_opportunity_already_responded",
                    "Decision opportunity was responded to concurrently.",
                )
            return QueuedSimulationInput(
                queue_id=queue_id,
                submitted_tick=submitted_tick,
                value=value,
            )

    def _commit_tick(
        self,
        connection: DbConnection,
        before: WorldState,
        result: TickResult,
        queued: tuple[QueuedSimulationInput, ...],
    ) -> None:
        """Commit lifecycle projection in the same transaction as the authoritative tick."""

        super()._commit_tick(connection, before, result, queued)
        self._link_committed_responses(connection, result, queued)
        connection.execute(
            """
            UPDATE cliova_decision_opportunities
               SET status = 'expired'
             WHERE world_id = %s
               AND status = 'open'
               AND expires_at_tick IS NOT NULL
               AND expires_at_tick <= %s
            """,
            (result.world.id.value, result.world.time.tick),
        )
        projection = self._attention_producer.produce(before, result)
        for item in projection.attention_items:
            self._insert_attention_item(connection, item)
        for opportunity in projection.decision_opportunities:
            self._insert_decision_opportunity(connection, opportunity)

    def _link_committed_responses(
        self,
        connection: DbConnection,
        result: TickResult,
        queued: tuple[QueuedSimulationInput, ...],
    ) -> None:
        if not queued:
            return
        if len(result.events) < len(queued):
            raise PersistenceError("tick result is missing deterministic input ingest events")
        for queued_item, ingest_event in zip(
            queued, result.events[: len(queued)], strict=True
        ):
            response = connection.execute(
                """
                SELECT opportunity_id
                  FROM cliova_decision_opportunities
                 WHERE world_id = %s AND response_queue_id = %s
                """,
                (result.world.id.value, queued_item.queue_id),
            ).fetchone()
            if response is None:
                continue
            if queued_item.value.directive is None or not any(
                directive.id == ingest_event.id for directive in result.world.directives
            ):
                raise PersistenceError(
                    "decision response did not materialize through the authoritative directive boundary"
                )
            connection.execute(
                """
                UPDATE cliova_decision_opportunities
                   SET response_directive_id = %s
                 WHERE opportunity_id = %s
                """,
                (ingest_event.id, response["opportunity_id"]),
            )

    @staticmethod
    def _insert_attention_item(connection: DbConnection, item: AttentionItem) -> None:
        connection.execute(
            """
            INSERT INTO cliova_attention_items (
                attention_id, world_id, target_kind, target_id, created_tick, created_year,
                category, priority, context, related_event_ids, related_subjects
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (attention_id) DO NOTHING
            """,
            (
                item.id,
                item.world_id,
                item.target_subject.kind if item.target_subject else None,
                item.target_subject.value if item.target_subject else None,
                item.created_tick,
                item.created_year,
                item.category,
                item.priority.value,
                item.context,
                list(item.related_event_ids),
                Jsonb([subject.model_dump(mode="json") for subject in item.related_subjects]),
            ),
        )

    @staticmethod
    def _insert_decision_opportunity(
        connection: DbConnection, opportunity: DecisionOpportunity
    ) -> None:
        connection.execute(
            """
            INSERT INTO cliova_decision_opportunities (
                opportunity_id, world_id, target_kind, target_id, created_tick, created_year,
                category, context, related_event_ids, related_subjects, earliest_effect_tick,
                expires_at_tick, default_behavior, response_intent, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (opportunity_id) DO NOTHING
            """,
            (
                opportunity.id,
                opportunity.world_id,
                opportunity.target_subject.kind,
                opportunity.target_subject.value,
                opportunity.created_tick,
                opportunity.created_year,
                opportunity.category,
                opportunity.context,
                list(opportunity.related_event_ids),
                Jsonb([subject.model_dump(mode="json") for subject in opportunity.related_subjects]),
                opportunity.earliest_effect_tick,
                opportunity.expires_at_tick,
                opportunity.default_behavior,
                opportunity.response_intent,
                opportunity.status.value,
            ),
        )


def _attention_item(row: dict[str, Any]) -> AttentionItem:
    target = _optional_target(row)
    return AttentionItem(
        id=cast(UUID, row["attention_id"]),
        world_id=cast(UUID, row["world_id"]),
        target_subject=target,
        created_tick=int(row["created_tick"]),
        created_year=int(row["created_year"]),
        category=str(row["category"]),
        priority=AttentionPriority(str(row["priority"])),
        context=str(row["context"]),
        related_event_ids=tuple(cast(list[UUID], row["related_event_ids"])),
        related_subjects=_subjects(row["related_subjects"]),
    )


def _decision_opportunity(row: dict[str, Any]) -> DecisionOpportunity:
    target = _optional_target(row)
    if target is None:
        raise PersistenceError("decision opportunity is missing its target subject")
    return DecisionOpportunity(
        id=cast(UUID, row["opportunity_id"]),
        world_id=cast(UUID, row["world_id"]),
        target_subject=target,
        created_tick=int(row["created_tick"]),
        created_year=int(row["created_year"]),
        category=str(row["category"]),
        context=str(row["context"]),
        related_event_ids=tuple(cast(list[UUID], row["related_event_ids"])),
        related_subjects=_subjects(row["related_subjects"]),
        earliest_effect_tick=int(row["earliest_effect_tick"]),
        expires_at_tick=cast(int | None, row["expires_at_tick"]),
        default_behavior=str(row["default_behavior"]),
        response_intent=str(row["response_intent"]),
        status=DecisionOpportunityStatus(str(row["status"])),
        response_queue_id=cast(int | None, row["response_queue_id"]),
        response_submitted_tick=cast(int | None, row["response_submitted_tick"]),
        response_directive_id=cast(UUID | None, row["response_directive_id"]),
    )


def _optional_target(row: dict[str, Any]) -> EntityId | None:
    if row["target_kind"] is None or row["target_id"] is None:
        return None
    return EntityId.model_validate(
        {"kind": str(row["target_kind"]), "value": cast(UUID, row["target_id"])}
    )


def _subjects(value: object) -> tuple[EntityId, ...]:
    if not isinstance(value, list):
        raise PersistenceError("related_subjects must decode as a JSON list")
    return tuple(EntityId.model_validate(item) for item in value)
