"""Concrete PostgreSQL repositories for durable Cliova world progression."""

from __future__ import annotations

import hashlib
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cliova.application.persistence import QueuedSimulationInput, TickResolver
from cliova.simulation.history import EventHistory
from cliova.simulation.types import SimulationEvent, SimulationInput, TickResult, WorldState

_WORLD_PAYLOAD_VERSION = 1
_INPUT_PAYLOAD_VERSION = 1
_EVENT_PAYLOAD_VERSION = 1

DbRow = dict[str, Any]
DbConnection = Connection[DbRow]


class PersistenceError(RuntimeError):
    """Base persistence failure."""


class WorldNotFoundError(PersistenceError):
    """Requested world/snapshot is not present."""


class TickConflictError(PersistenceError):
    """The caller attempted to persist a stale or duplicate tick."""


class UnsupportedPayloadVersionError(PersistenceError):
    """Persisted payload needs an explicit migration before it can be loaded."""


class PostgresPersistence:
    """Psycopg-backed implementation of the application persistence boundary."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url must be non-empty")
        self._database_url = database_url

    def _connect(self) -> DbConnection:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def create_world(self, world: WorldState) -> None:
        payload = _encode_world(world)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cliova_worlds (
                    world_id, seed, current_tick, current_year,
                    schema_version, simulation_version, rng_algorithm,
                    payload_schema_version, state_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    world.id.value,
                    str(world.seed),
                    world.time.tick,
                    world.time.year,
                    world.metadata.schema_version,
                    world.metadata.simulation_version,
                    world.metadata.rng_algorithm,
                    _WORLD_PAYLOAD_VERSION,
                    Jsonb(payload),
                ),
            )
            self._insert_snapshot(connection, world)

    def load_world(self, world_id: UUID) -> WorldState:
        with self._connect() as connection:
            return self._load_world(connection, world_id, for_update=False)

    def load_snapshot(self, world_id: UUID, tick: int) -> WorldState:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT seed, tick, year, schema_version, simulation_version,
                       rng_algorithm, payload_schema_version, state_json
                  FROM cliova_world_snapshots
                 WHERE world_id = %s AND tick = %s
                """,
                (world_id, tick),
            ).fetchone()
            if row is None:
                raise WorldNotFoundError(f"snapshot {world_id}/{tick} does not exist")
            return self._world_from_row(row, expected_world_id=world_id)

    def queue_input(self, world_id: UUID, value: SimulationInput) -> QueuedSimulationInput:
        payload = _encode_input(value)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT current_tick FROM cliova_worlds WHERE world_id = %s FOR UPDATE",
                (world_id,),
            ).fetchone()
            if row is None:
                raise WorldNotFoundError(f"world {world_id} does not exist")
            submitted_tick = int(row["current_tick"]) + 1
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
                raise PersistenceError("queued input insert returned no identity")
            return QueuedSimulationInput(
                queue_id=int(inserted["queue_id"]),
                submitted_tick=submitted_tick,
                value=value,
            )

    def load_pending_inputs(self, world_id: UUID) -> tuple[QueuedSimulationInput, ...]:
        with self._connect() as connection:
            self._require_world(connection, world_id)
            return self._load_pending_inputs(connection, world_id, submitted_tick=None)

    def execute_tick(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        resolver: TickResolver,
    ) -> TickResult:
        """Lock, resolve and commit one expected next tick in one DB transaction."""

        if expected_tick < 0:
            raise ValueError("expected_tick must be non-negative")

        with self._connect() as connection:
            world = self._load_world(connection, world_id, for_update=True)
            if world.time.tick != expected_tick:
                raise TickConflictError(
                    f"world {world_id} is at tick {world.time.tick}, expected {expected_tick}"
                )

            submitted_tick = expected_tick + 1
            queued = self._load_pending_inputs(
                connection,
                world_id,
                submitted_tick=submitted_tick,
            )
            result = resolver(world, tuple(item.value for item in queued))
            self._validate_tick_result(world, result, expected_tick=expected_tick)
            self._commit_tick(connection, world, result, queued)
            return result

    def load_history(self, world_id: UUID) -> EventHistory:
        with self._connect() as connection:
            self._require_world(connection, world_id)
            rows = connection.execute(
                """
                SELECT event_id, payload_schema_version, event_json
                  FROM cliova_history_events
                 WHERE world_id = %s
                 ORDER BY tick, ordinal
                """,
                (world_id,),
            ).fetchall()
            cause_rows = connection.execute(
                """
                SELECT event_id, ordinal, cause_event_id
                  FROM cliova_history_event_causes
                 WHERE world_id = %s
                 ORDER BY event_id, ordinal
                """,
                (world_id,),
            ).fetchall()

        causes: dict[UUID, list[UUID]] = {}
        for row in cause_rows:
            event_id = cast(UUID, row["event_id"])
            causes.setdefault(event_id, []).append(cast(UUID, row["cause_event_id"]))

        events: list[SimulationEvent] = []
        for row in rows:
            version = int(row["payload_schema_version"])
            if version != _EVENT_PAYLOAD_VERSION:
                raise UnsupportedPayloadVersionError(
                    f"event payload version {version} requires migration"
                )
            event = _decode_event(cast(dict[str, Any], row["event_json"]))
            indexed_causes = tuple(causes.get(event.id, []))
            if indexed_causes != event.cause_event_ids:
                raise PersistenceError(f"causal index mismatch for event {event.id}")
            events.append(event)
        return EventHistory(events)

    def _require_world(self, connection: DbConnection, world_id: UUID) -> None:
        row = connection.execute(
            "SELECT 1 AS present FROM cliova_worlds WHERE world_id = %s", (world_id,)
        ).fetchone()
        if row is None:
            raise WorldNotFoundError(f"world {world_id} does not exist")

    def _load_world(
        self, connection: DbConnection, world_id: UUID, *, for_update: bool
    ) -> WorldState:
        lock = " FOR UPDATE" if for_update else ""
        row = connection.execute(
            """
            SELECT seed, current_tick AS tick, current_year AS year,
                   schema_version, simulation_version, rng_algorithm,
                   payload_schema_version, state_json
              FROM cliova_worlds
             WHERE world_id = %s
            """
            + lock,
            (world_id,),
        ).fetchone()
        if row is None:
            raise WorldNotFoundError(f"world {world_id} does not exist")
        return self._world_from_row(row, expected_world_id=world_id)

    def _world_from_row(self, row: DbRow, *, expected_world_id: UUID) -> WorldState:
        version = int(row["payload_schema_version"])
        if version != _WORLD_PAYLOAD_VERSION:
            raise UnsupportedPayloadVersionError(
                f"world payload version {version} requires migration"
            )
        world = _decode_world(cast(dict[str, Any], row["state_json"]))
        if world.id.value != expected_world_id:
            raise PersistenceError("stored world identity does not match row key")
        if str(world.seed) != str(row["seed"]):
            raise PersistenceError("stored world seed metadata does not match payload")
        if world.time.tick != int(row["tick"]) or world.time.year != int(row["year"]):
            raise PersistenceError("stored world time metadata does not match payload")
        if (
            world.metadata.schema_version != int(row["schema_version"])
            or world.metadata.simulation_version != int(row["simulation_version"])
            or world.metadata.rng_algorithm != str(row["rng_algorithm"])
        ):
            raise PersistenceError("stored world version metadata does not match payload")
        return world

    def _load_pending_inputs(
        self,
        connection: DbConnection,
        world_id: UUID,
        *,
        submitted_tick: int | None,
    ) -> tuple[QueuedSimulationInput, ...]:
        query = """
            SELECT queue_id, submitted_tick, payload_schema_version, input_json
              FROM cliova_queued_inputs
             WHERE world_id = %s AND consumed_tick IS NULL
        """
        params: tuple[object, ...]
        if submitted_tick is not None:
            query += " AND submitted_tick = %s"
            params = (world_id, submitted_tick)
        else:
            params = (world_id,)
        query += " ORDER BY submitted_tick, queue_id"

        rows = connection.execute(query, params).fetchall()
        queued: list[QueuedSimulationInput] = []
        for row in rows:
            version = int(row["payload_schema_version"])
            if version != _INPUT_PAYLOAD_VERSION:
                raise UnsupportedPayloadVersionError(
                    f"input payload version {version} requires migration"
                )
            queued.append(
                QueuedSimulationInput(
                    queue_id=int(row["queue_id"]),
                    submitted_tick=int(row["submitted_tick"]),
                    value=_decode_input(cast(dict[str, Any], row["input_json"])),
                )
            )
        return tuple(queued)

    def _validate_tick_result(
        self, before: WorldState, result: TickResult, *, expected_tick: int
    ) -> None:
        after = result.world
        if after.id != before.id or after.seed != before.seed or after.metadata != before.metadata:
            raise PersistenceError("tick result changed immutable world identity/metadata")
        if after.time.tick != expected_tick + 1 or after.time.year != before.time.year + 1:
            raise PersistenceError("tick result does not advance exactly one authoritative tick")
        if any(event.time != after.time for event in result.events):
            raise PersistenceError("tick event time does not match committed world time")
        event_ids = [event.id for event in result.events]
        if len(event_ids) != len(set(event_ids)):
            raise PersistenceError("tick result contains duplicate event IDs")

    def _commit_tick(
        self,
        connection: DbConnection,
        before: WorldState,
        result: TickResult,
        queued: tuple[QueuedSimulationInput, ...],
    ) -> None:
        after = result.world
        state_payload = _encode_world(after)
        digest = hashlib.sha256(after.model_dump_json().encode("utf-8")).hexdigest()

        try:
            connection.execute(
                """
                INSERT INTO cliova_completed_ticks (
                    world_id, tick, year, previous_tick, input_count, event_count,
                    schema_version, simulation_version, state_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    after.id.value,
                    after.time.tick,
                    after.time.year,
                    before.time.tick,
                    len(queued),
                    len(result.events),
                    after.metadata.schema_version,
                    after.metadata.simulation_version,
                    digest,
                ),
            )
        except UniqueViolation as exc:
            raise TickConflictError(
                f"world {after.id.value} tick {after.time.tick} is already completed"
            ) from exc

        updated = connection.execute(
            """
            UPDATE cliova_worlds
               SET seed = %s,
                   current_tick = %s,
                   current_year = %s,
                   schema_version = %s,
                   simulation_version = %s,
                   rng_algorithm = %s,
                   payload_schema_version = %s,
                   state_json = %s
             WHERE world_id = %s AND current_tick = %s
            """,
            (
                str(after.seed),
                after.time.tick,
                after.time.year,
                after.metadata.schema_version,
                after.metadata.simulation_version,
                after.metadata.rng_algorithm,
                _WORLD_PAYLOAD_VERSION,
                Jsonb(state_payload),
                after.id.value,
                before.time.tick,
            ),
        )
        if updated.rowcount != 1:
            raise TickConflictError("world advanced concurrently before commit")

        self._insert_snapshot(connection, after)
        self._persist_events(connection, after.id.value, result.events)

        if queued:
            queue_ids = [item.queue_id for item in queued]
            consumed = connection.execute(
                """
                UPDATE cliova_queued_inputs
                   SET consumed_tick = %s
                 WHERE world_id = %s
                   AND queue_id = ANY(%s)
                   AND submitted_tick = %s
                   AND consumed_tick IS NULL
                """,
                (after.time.tick, after.id.value, queue_ids, after.time.tick),
            )
            if consumed.rowcount != len(queue_ids):
                raise TickConflictError("queued inputs changed before tick commit")

    def _insert_snapshot(self, connection: DbConnection, world: WorldState) -> None:
        connection.execute(
            """
            INSERT INTO cliova_world_snapshots (
                world_id, tick, year, seed, schema_version, simulation_version,
                rng_algorithm, payload_schema_version, state_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                world.id.value,
                world.time.tick,
                world.time.year,
                str(world.seed),
                world.metadata.schema_version,
                world.metadata.simulation_version,
                world.metadata.rng_algorithm,
                _WORLD_PAYLOAD_VERSION,
                Jsonb(_encode_world(world)),
            ),
        )

    def _persist_events(
        self,
        connection: DbConnection,
        world_id: UUID,
        events: tuple[SimulationEvent, ...],
    ) -> None:
        for ordinal, event in enumerate(events):
            connection.execute(
                """
                INSERT INTO cliova_history_events (
                    world_id, event_id, tick, year, ordinal, source, kind,
                    payload_schema_version, event_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    world_id,
                    event.id,
                    event.time.tick,
                    event.time.year,
                    ordinal,
                    event.source,
                    event.kind,
                    _EVENT_PAYLOAD_VERSION,
                    Jsonb(_encode_event(event)),
                ),
            )

        for event in events:
            for ordinal, cause_event_id in enumerate(event.cause_event_ids):
                connection.execute(
                    """
                    INSERT INTO cliova_history_event_causes (
                        world_id, event_id, ordinal, cause_event_id
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (world_id, event.id, ordinal, cause_event_id),
                )


def _encode_world(world: WorldState) -> dict[str, Any]:
    return world.model_dump(mode="json")


def _decode_world(payload: dict[str, Any]) -> WorldState:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise PersistenceError("world payload has no version metadata")
    schema_version = metadata.get("schema_version")
    if schema_version != 1:
        raise UnsupportedPayloadVersionError(
            f"world schema version {schema_version!r} requires migration"
        )
    return WorldState.model_validate(payload)


def _encode_input(value: SimulationInput) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _decode_input(payload: dict[str, Any]) -> SimulationInput:
    return SimulationInput.model_validate(payload)


def _encode_event(event: SimulationEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def _decode_event(payload: dict[str, Any]) -> SimulationEvent:
    return SimulationEvent.model_validate(payload)
