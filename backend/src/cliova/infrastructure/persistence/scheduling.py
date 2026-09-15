"""PostgreSQL scheduling/claim adapter built on the existing atomic tick persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from cliova.application.persistence import TickResolver
from cliova.application.scheduling import (
    TickRunClaim,
    TickRunRecord,
    TickRunStatus,
    TickRunTrigger,
    WorldScheduleState,
    WorldScheduleStatus,
)
from cliova.infrastructure.persistence.postgres import (
    DbConnection,
    DbRow,
    PersistenceError,
    TickConflictError,
)
from cliova.infrastructure.persistence.worlds import PostgresWorldRepository
from cliova.simulation.types import TickResult

_CLAIM_LEASE = timedelta(minutes=15)
_MAX_FAILURE_REASON = 2000


class PostgresScheduledWorldRepository(PostgresWorldRepository):
    """Add durable scheduler state without moving wall-clock concerns into simulation domains."""

    def list_due_world_ids(self, *, now: datetime) -> tuple[UUID, ...]:
        now = _aware_utc(now)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT w.world_id
                  FROM cliova_worlds AS w
             LEFT JOIN cliova_world_schedules AS s ON s.world_id = w.world_id
                 WHERE COALESCE(s.status, 'active') = 'active'
                   AND (s.next_eligible_at IS NULL OR s.next_eligible_at <= %s)
                 ORDER BY w.world_id
                """,
                (now,),
            ).fetchall()
        return tuple(cast(UUID, row["world_id"]) for row in rows)

    def claim_scheduled_tick(self, world_id: UUID, *, now: datetime) -> TickRunClaim | None:
        return self._claim_tick(
            world_id,
            now=_aware_utc(now),
            trigger=TickRunTrigger.SCHEDULED,
            expected_tick=None,
            enforce_due=True,
            strict=False,
        )

    def claim_manual_tick(
        self,
        world_id: UUID,
        *,
        expected_tick: int,
        now: datetime,
    ) -> TickRunClaim:
        if expected_tick < 0:
            raise ValueError("expected_tick must be non-negative")
        claim = self._claim_tick(
            world_id,
            now=_aware_utc(now),
            trigger=TickRunTrigger.MANUAL,
            expected_tick=expected_tick,
            enforce_due=False,
            strict=True,
        )
        if claim is None:  # pragma: no cover - strict claims raise rather than return None.
            raise TickConflictError(f"world {world_id} could not be claimed for manual execution")
        return claim

    def execute_claimed_tick(
        self,
        claim: TickRunClaim,
        *,
        resolver: TickResolver,
        next_eligible_at: datetime,
    ) -> TickResult:
        """Freeze accepted inputs, resolve, commit, and complete run metadata atomically."""

        next_eligible_at = _aware_utc(next_eligible_at)
        accepted_boundary: int | None = None
        accepted_count = 0

        try:
            with self._connect() as connection:
                schedule = self._load_schedule_row(connection, claim.world_id, for_update=True)
                if schedule["current_run_id"] != claim.run_id:
                    raise TickConflictError("tick claim is no longer the active world run")

                run = connection.execute(
                    """
                    SELECT run_id, world_id, target_tick, status, claim_token
                      FROM cliova_tick_runs
                     WHERE run_id = %s
                     FOR UPDATE
                    """,
                    (claim.run_id,),
                ).fetchone()
                if run is None:
                    raise PersistenceError(f"tick run {claim.run_id} does not exist")
                if run["status"] != TickRunStatus.RUNNING.value:
                    raise TickConflictError(f"tick run {claim.run_id} is not running")
                if run["claim_token"] != claim.claim_token:
                    raise TickConflictError(f"tick run {claim.run_id} claim token is stale")
                if cast(UUID, run["world_id"]) != claim.world_id:
                    raise PersistenceError("tick run world identity does not match claim")
                if int(run["target_tick"]) != claim.target_tick:
                    raise PersistenceError("tick run target does not match claim")

                world = self._load_world(connection, claim.world_id, for_update=True)
                expected_tick = claim.target_tick - 1
                if world.time.tick != expected_tick:
                    raise TickConflictError(
                        f"world {claim.world_id} is at tick {world.time.tick}, "
                        f"expected {expected_tick}"
                    )

                queued = self._load_pending_inputs(
                    connection,
                    claim.world_id,
                    submitted_tick=claim.target_tick,
                )
                accepted_count = len(queued)
                accepted_boundary = max((item.queue_id for item in queued), default=None)

                result = resolver(world, tuple(item.value for item in queued))
                self._validate_tick_result(world, result, expected_tick=expected_tick)
                self._commit_tick(connection, world, result, queued)

                completed_at = datetime.now(UTC)
                updated_run = connection.execute(
                    """
                    UPDATE cliova_tick_runs
                       SET status = 'completed',
                           completed_at = %s,
                           failed_at = NULL,
                           failure_reason = NULL,
                           accepted_input_max_queue_id = %s,
                           accepted_input_count = %s
                     WHERE run_id = %s
                       AND status = 'running'
                       AND claim_token = %s
                    """,
                    (
                        completed_at,
                        accepted_boundary,
                        accepted_count,
                        claim.run_id,
                        claim.claim_token,
                    ),
                )
                if updated_run.rowcount != 1:
                    raise TickConflictError("tick run ownership changed before completion")

                updated_schedule = connection.execute(
                    """
                    UPDATE cliova_world_schedules
                       SET current_run_id = NULL,
                           last_completed_run_id = %s,
                           last_completed_at = %s,
                           next_eligible_at = %s
                     WHERE world_id = %s
                       AND current_run_id = %s
                    """,
                    (
                        claim.run_id,
                        completed_at,
                        next_eligible_at,
                        claim.world_id,
                        claim.run_id,
                    ),
                )
                if updated_schedule.rowcount != 1:
                    raise TickConflictError("world schedule changed before tick completion")
                return result
        except Exception as exc:
            self._record_failure(
                claim,
                reason=_failure_reason(exc),
                accepted_boundary=accepted_boundary,
                accepted_count=accepted_count,
            )
            raise

    def set_schedule_status(
        self,
        world_id: UUID,
        *,
        status: WorldScheduleStatus,
        now: datetime,
    ) -> WorldScheduleState:
        _aware_utc(now)
        with self._connect() as connection:
            self._require_world(connection, world_id)
            self._ensure_schedule(connection, world_id)
            connection.execute(
                "UPDATE cliova_world_schedules SET status = %s WHERE world_id = %s",
                (status.value, world_id),
            )
            row = self._load_schedule_row(connection, world_id, for_update=False)
            return _schedule_state(row)

    def load_schedule_state(self, world_id: UUID) -> WorldScheduleState:
        with self._connect() as connection:
            self._require_world(connection, world_id)
            self._ensure_schedule(connection, world_id)
            return _schedule_state(self._load_schedule_row(connection, world_id, for_update=False))

    def load_tick_run(self, world_id: UUID, *, target_tick: int) -> TickRunRecord | None:
        if target_tick <= 0:
            raise ValueError("target_tick must be positive")
        with self._connect() as connection:
            self._require_world(connection, world_id)
            row = connection.execute(
                """
                SELECT run_id, world_id, target_tick, trigger, status, scheduled_for,
                       started_at, completed_at, failed_at, failure_reason,
                       accepted_input_max_queue_id, accepted_input_count, attempt_count
                  FROM cliova_tick_runs
                 WHERE world_id = %s AND target_tick = %s
                """,
                (world_id, target_tick),
            ).fetchone()
        return None if row is None else _tick_run_record(row)

    def _claim_tick(
        self,
        world_id: UUID,
        *,
        now: datetime,
        trigger: TickRunTrigger,
        expected_tick: int | None,
        enforce_due: bool,
        strict: bool,
    ) -> TickRunClaim | None:
        with self._connect() as connection:
            self._require_world(connection, world_id)
            self._ensure_schedule(connection, world_id)
            schedule = self._load_schedule_row(connection, world_id, for_update=True)

            if schedule["status"] == WorldScheduleStatus.PAUSED.value:
                if strict:
                    raise TickConflictError(f"world {world_id} is administratively paused")
                return None

            next_eligible_at = cast(datetime | None, schedule["next_eligible_at"])
            if enforce_due and next_eligible_at is not None and next_eligible_at > now:
                return None

            current_run_id = cast(UUID | None, schedule["current_run_id"])
            if current_run_id is not None:
                current = connection.execute(
                    """
                    SELECT run_id, target_tick, status, claim_expires_at, attempt_count
                      FROM cliova_tick_runs
                     WHERE run_id = %s
                    """,
                    (current_run_id,),
                ).fetchone()
                if current is None:
                    raise PersistenceError("world schedule references a missing tick run")
                if current["status"] == TickRunStatus.RUNNING.value:
                    claim_expires_at = cast(datetime, current["claim_expires_at"])
                    if claim_expires_at > now:
                        connection.execute(
                            """
                            UPDATE cliova_world_schedules
                               SET duplicate_attempt_count = duplicate_attempt_count + 1
                             WHERE world_id = %s
                            """,
                            (world_id,),
                        )
                        if strict:
                            raise TickConflictError(f"world {world_id} already has a running tick")
                        return None
                    return self._reclaim_expired_run(
                        connection,
                        world_id=world_id,
                        run_id=current_run_id,
                        current=current,
                        now=now,
                        trigger=trigger,
                        expected_tick=expected_tick,
                    )
                raise PersistenceError("world schedule current run is not in running state")

            world = self._load_world(connection, world_id, for_update=True)
            if expected_tick is not None and world.time.tick != expected_tick:
                raise TickConflictError(
                    f"world {world_id} is at tick {world.time.tick}, expected {expected_tick}"
                )
            target_tick = world.time.tick + 1
            existing = connection.execute(
                """
                SELECT run_id, target_tick, status, attempt_count
                  FROM cliova_tick_runs
                 WHERE world_id = %s AND target_tick = %s
                 FOR UPDATE
                """,
                (world_id, target_tick),
            ).fetchone()

            claim_token = uuid4()
            claim_expires_at = now + _CLAIM_LEASE
            if existing is None:
                run_id = uuid4()
                attempt_count = 1
                connection.execute(
                    """
                    INSERT INTO cliova_tick_runs (
                        run_id, world_id, target_tick, trigger, status, scheduled_for,
                        claim_token, claim_expires_at, started_at, attempt_count
                    ) VALUES (%s, %s, %s, %s, 'running', %s, %s, %s, %s, 1)
                    """,
                    (
                        run_id,
                        world_id,
                        target_tick,
                        trigger.value,
                        now if trigger is TickRunTrigger.SCHEDULED else None,
                        claim_token,
                        claim_expires_at,
                        now,
                    ),
                )
            else:
                if existing["status"] != TickRunStatus.FAILED.value:
                    raise TickConflictError(
                        f"world {world_id} tick {target_tick} already has a non-retryable run"
                    )
                run_id = cast(UUID, existing["run_id"])
                attempt_count = int(existing["attempt_count"]) + 1
                connection.execute(
                    """
                    UPDATE cliova_tick_runs
                       SET trigger = %s,
                           status = 'running',
                           scheduled_for = %s,
                           claim_token = %s,
                           claim_expires_at = %s,
                           started_at = %s,
                           completed_at = NULL,
                           failed_at = NULL,
                           failure_reason = NULL,
                           accepted_input_max_queue_id = NULL,
                           accepted_input_count = 0,
                           attempt_count = %s
                     WHERE run_id = %s
                    """,
                    (
                        trigger.value,
                        now if trigger is TickRunTrigger.SCHEDULED else None,
                        claim_token,
                        claim_expires_at,
                        now,
                        attempt_count,
                        run_id,
                    ),
                )

            connection.execute(
                "UPDATE cliova_world_schedules SET current_run_id = %s WHERE world_id = %s",
                (run_id, world_id),
            )
            return TickRunClaim(
                run_id=run_id,
                world_id=world_id,
                target_tick=target_tick,
                trigger=trigger,
                claim_token=claim_token,
                started_at=now,
                attempt_count=attempt_count,
            )

    def _reclaim_expired_run(
        self,
        connection: DbConnection,
        *,
        world_id: UUID,
        run_id: UUID,
        current: DbRow,
        now: datetime,
        trigger: TickRunTrigger,
        expected_tick: int | None,
    ) -> TickRunClaim:
        world = self._load_world(connection, world_id, for_update=True)
        if expected_tick is not None and world.time.tick != expected_tick:
            raise TickConflictError(
                f"world {world_id} is at tick {world.time.tick}, expected {expected_tick}"
            )
        target_tick = world.time.tick + 1
        if int(current["target_tick"]) != target_tick:
            raise PersistenceError("expired run target no longer matches authoritative world state")

        claim_token = uuid4()
        attempt_count = int(current["attempt_count"]) + 1
        updated = connection.execute(
            """
            UPDATE cliova_tick_runs
               SET trigger = %s,
                   scheduled_for = %s,
                   claim_token = %s,
                   claim_expires_at = %s,
                   started_at = %s,
                   attempt_count = %s
             WHERE run_id = %s AND status = 'running'
            """,
            (
                trigger.value,
                now if trigger is TickRunTrigger.SCHEDULED else None,
                claim_token,
                now + _CLAIM_LEASE,
                now,
                attempt_count,
                run_id,
            ),
        )
        if updated.rowcount != 1:
            raise TickConflictError("expired tick claim changed before it could be reclaimed")
        return TickRunClaim(
            run_id=run_id,
            world_id=world_id,
            target_tick=target_tick,
            trigger=trigger,
            claim_token=claim_token,
            started_at=now,
            attempt_count=attempt_count,
        )

    def _record_failure(
        self,
        claim: TickRunClaim,
        *,
        reason: str,
        accepted_boundary: int | None,
        accepted_count: int,
    ) -> None:
        failed_at = datetime.now(UTC)
        with self._connect() as connection:
            self._ensure_schedule(connection, claim.world_id)
            self._load_schedule_row(connection, claim.world_id, for_update=True)
            run = connection.execute(
                "SELECT status, claim_token FROM cliova_tick_runs WHERE run_id = %s FOR UPDATE",
                (claim.run_id,),
            ).fetchone()
            if run is None:
                return
            if (
                run["status"] != TickRunStatus.RUNNING.value
                or run["claim_token"] != claim.claim_token
            ):
                return
            connection.execute(
                """
                UPDATE cliova_tick_runs
                   SET status = 'failed',
                       failed_at = %s,
                       failure_reason = %s,
                       accepted_input_max_queue_id = %s,
                       accepted_input_count = %s
                 WHERE run_id = %s
                """,
                (failed_at, reason, accepted_boundary, accepted_count, claim.run_id),
            )
            connection.execute(
                """
                UPDATE cliova_world_schedules
                   SET current_run_id = NULL,
                       last_failure_at = %s,
                       last_failure_reason = %s
                 WHERE world_id = %s AND current_run_id = %s
                """,
                (failed_at, reason, claim.world_id, claim.run_id),
            )

    def _ensure_schedule(self, connection: DbConnection, world_id: UUID) -> None:
        connection.execute(
            """
            INSERT INTO cliova_world_schedules (world_id, status)
            VALUES (%s, 'active')
            ON CONFLICT (world_id) DO NOTHING
            """,
            (world_id,),
        )

    def _load_schedule_row(
        self,
        connection: DbConnection,
        world_id: UUID,
        *,
        for_update: bool,
    ) -> DbRow:
        lock = " FOR UPDATE" if for_update else ""
        row = connection.execute(
            """
            SELECT world_id, status, next_eligible_at, current_run_id,
                   last_completed_run_id, last_completed_at,
                   last_failure_at, last_failure_reason, duplicate_attempt_count
              FROM cliova_world_schedules
             WHERE world_id = %s
            """
            + lock,
            (world_id,),
        ).fetchone()
        if row is None:
            raise PersistenceError(f"world {world_id} has no scheduling state")
        return row


def _schedule_state(row: DbRow) -> WorldScheduleState:
    return WorldScheduleState(
        world_id=cast(UUID, row["world_id"]),
        status=WorldScheduleStatus(str(row["status"])),
        next_eligible_at=cast(datetime | None, row["next_eligible_at"]),
        current_run_id=cast(UUID | None, row["current_run_id"]),
        last_completed_run_id=cast(UUID | None, row["last_completed_run_id"]),
        last_completed_at=cast(datetime | None, row["last_completed_at"]),
        last_failure_at=cast(datetime | None, row["last_failure_at"]),
        last_failure_reason=cast(str | None, row["last_failure_reason"]),
        duplicate_attempt_count=int(row["duplicate_attempt_count"]),
    )


def _tick_run_record(row: DbRow) -> TickRunRecord:
    return TickRunRecord(
        run_id=cast(UUID, row["run_id"]),
        world_id=cast(UUID, row["world_id"]),
        target_tick=int(row["target_tick"]),
        trigger=TickRunTrigger(str(row["trigger"])),
        status=TickRunStatus(str(row["status"])),
        scheduled_for=cast(datetime | None, row["scheduled_for"]),
        started_at=cast(datetime, row["started_at"]),
        completed_at=cast(datetime | None, row["completed_at"]),
        failed_at=cast(datetime | None, row["failed_at"]),
        failure_reason=cast(str | None, row["failure_reason"]),
        accepted_input_max_queue_id=cast(int | None, row["accepted_input_max_queue_id"]),
        accepted_input_count=int(row["accepted_input_count"]),
        attempt_count=int(row["attempt_count"]),
    )


def _failure_reason(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    return message[:_MAX_FAILURE_REASON]


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler timestamps must be timezone-aware")
    return value.astimezone(UTC)
