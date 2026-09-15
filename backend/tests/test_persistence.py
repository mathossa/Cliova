import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psycopg
import pytest

from cliova.application.persistence import PersistedTickService
from cliova.infrastructure.persistence.migrations import apply_migrations
from cliova.infrastructure.persistence.postgres import PostgresPersistence, TickConflictError
from cliova.simulation.domains.directives import (
    DirectiveAwareEconomyDomain,
    DirectiveDomain,
    directive_input,
)
from cliova.simulation.domains.economy import initialize_economy
from cliova.simulation.domains.politics import GovernanceDomain, initialize_governance
from cliova.simulation.domains.population import initialize_population
from cliova.simulation.domains.world.fixtures import create_starter_world
from cliova.simulation.engine import SimulationEngine, TickContext, TickExecutionError, TickPhase
from cliova.simulation.history import EventHistory
from cliova.simulation.randomness import RandomSource
from cliova.simulation.types import (
    DomainResult,
    EntityId,
    GovernanceState,
    InstitutionProfile,
    SimulationChange,
    SimulationInput,
    WorldState,
    entity_id,
)

pytestmark = pytest.mark.integration

_PERSISTENCE_TABLES = (
    "cliova_history_event_causes",
    "cliova_history_events",
    "cliova_completed_ticks",
    "cliova_queued_inputs",
    "cliova_world_snapshots",
    "cliova_worlds",
)


def _database_url() -> str:
    url = os.environ.get("CLIOVA_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set CLIOVA_TEST_DATABASE_URL to a disposable PostgreSQL database")
    return url


@pytest.fixture
def database_url() -> str:
    url = _database_url()
    apply_migrations(url)
    with psycopg.connect(url) as connection:
        connection.execute(
            "TRUNCATE TABLE " + ", ".join(_PERSISTENCE_TABLES) + " RESTART IDENTITY CASCADE"
        )
    return url


def configured_world(
    *, seed: int = 91, world_key: str = "persistence-test"
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
        legitimacy=0.9,
        execution_capacity=0.9,
        internal_resistance=0.1,
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
    return directive_input(author=author, target_subject=target, priority="normal")


def _count(url: str, table: str) -> int:
    with psycopg.connect(url) as connection:
        row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        return int(row[0])


def test_migrations_initialize_empty_database() -> None:
    url = _database_url()
    with psycopg.connect(url) as connection:
        for table in _PERSISTENCE_TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        connection.execute("DROP TABLE IF EXISTS cliova_schema_migrations")

    assert apply_migrations(url) == ("0001_persistence.sql",)
    assert apply_migrations(url) == ()
    with psycopg.connect(url) as connection:
        for table in _PERSISTENCE_TABLES:
            row = connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()
            assert row is not None
            assert row[0] == table


def test_create_world_round_trips_authoritative_state_and_metadata(database_url: str) -> None:
    repository = PostgresPersistence(database_url)
    world = WorldState.create(seed=2**128, world_key="large-seed")

    repository.create_world(world)

    assert repository.load_world(world.id.value) == world
    assert repository.load_snapshot(world.id.value, 0) == world
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT seed, current_tick, current_year, schema_version,
                   simulation_version, rng_algorithm
              FROM cliova_worlds
             WHERE world_id = %s
            """,
            (world.id.value,),
        ).fetchone()
        assert row == (
            str(world.seed),
            0,
            0,
            world.metadata.schema_version,
            world.metadata.simulation_version,
            world.metadata.rng_algorithm,
        )


def test_actual_directive_input_survives_reload_in_stable_order(database_url: str) -> None:
    world, subject = configured_world()
    first_repository = PostgresPersistence(database_url)
    first_repository.create_world(world)
    first = first_repository.queue_input(world.id.value, submit(subject, author="player:first"))
    second = first_repository.queue_input(world.id.value, submit(subject, author="player:second"))

    reloaded = PostgresPersistence(database_url).load_pending_inputs(world.id.value)

    assert tuple(item.queue_id for item in reloaded) == (first.queue_id, second.queue_id)
    assert tuple(item.submitted_tick for item in reloaded) == (1, 1)
    assert tuple(item.value for item in reloaded) == (first.value, second.value)
    assert reloaded[0].value.directive is not None
    assert reloaded[0].value.directive.intent == "strengthen_food_reserves"


def test_successful_tick_commits_state_snapshot_history_and_input_atomically(
    database_url: str,
) -> None:
    world, subject = configured_world()
    repository = PostgresPersistence(database_url)
    repository.create_world(world)
    queued = repository.queue_input(world.id.value, submit(subject))
    service = PersistedTickService(directive_engine(), repository)

    result = service.advance_world(world.id.value, expected_tick=0)

    assert result.world.time.tick == 1
    assert result.world.directives[0].submitted_tick == queued.submitted_tick == 1
    assert repository.load_world(world.id.value) == result.world
    assert repository.load_snapshot(world.id.value, 0) == world
    assert repository.load_snapshot(world.id.value, 1) == result.world
    assert repository.load_pending_inputs(world.id.value) == ()
    assert repository.load_history(world.id.value).events == EventHistory(result.events).events
    assert _count(database_url, "cliova_completed_ticks") == 1


def test_failed_simulation_keeps_state_and_queue_then_retry_succeeds(database_url: str) -> None:
    class FailingDomain:
        name = "failing"
        phase = TickPhase.WORLD_ENVIRONMENT

        def step(self, world: WorldState, context: TickContext, rng: RandomSource) -> DomainResult:
            del world, context, rng
            raise RuntimeError("forced simulation failure")

        def apply_change(self, world: WorldState, change: SimulationChange) -> WorldState:
            del change
            return world

    world, subject = configured_world()
    repository = PostgresPersistence(database_url)
    repository.create_world(world)
    queued = repository.queue_input(world.id.value, submit(subject))

    with pytest.raises(TickExecutionError, match="forced simulation failure"):
        PersistedTickService(SimulationEngine((FailingDomain(),)), repository).advance_world(
            world.id.value,
            expected_tick=0,
        )

    assert repository.load_world(world.id.value) == world
    assert repository.load_pending_inputs(world.id.value) == (queued,)
    assert _count(database_url, "cliova_completed_ticks") == 0
    assert _count(database_url, "cliova_history_events") == 0

    retried = PersistedTickService(directive_engine(), repository).advance_world(
        world.id.value,
        expected_tick=0,
    )
    assert retried.world.time.tick == 1
    assert repository.load_pending_inputs(world.id.value) == ()


def test_database_error_mid_commit_rolls_back_all_authoritative_writes(database_url: str) -> None:
    class ExplodingPersistence(PostgresPersistence):
        def _persist_events(
            self,
            connection: Any,
            world_id: Any,
            events: Any,
        ) -> None:
            super()._persist_events(connection, world_id, events)
            raise RuntimeError("forced persistence failure")

    world, subject = configured_world(world_key="rollback-test")
    repository = ExplodingPersistence(database_url)
    repository.create_world(world)
    repository.queue_input(world.id.value, submit(subject))

    with pytest.raises(RuntimeError, match="forced persistence failure"):
        PersistedTickService(directive_engine(), repository).advance_world(
            world.id.value,
            expected_tick=0,
        )

    healthy_repository = PostgresPersistence(database_url)
    assert healthy_repository.load_world(world.id.value) == world
    assert len(healthy_repository.load_pending_inputs(world.id.value)) == 1
    assert _count(database_url, "cliova_completed_ticks") == 0
    assert _count(database_url, "cliova_history_events") == 0
    assert _count(database_url, "cliova_world_snapshots") == 1


def test_duplicate_expected_tick_is_rejected_even_with_concurrent_attempts(
    database_url: str,
) -> None:
    world = WorldState.create(seed=44, world_key="duplicate-tick")
    PostgresPersistence(database_url).create_world(world)

    def advance() -> str:
        repository = PostgresPersistence(database_url)
        try:
            repository.execute_tick(
                world.id.value,
                expected_tick=0,
                resolver=lambda state, inputs: SimulationEngine().step(state, inputs=inputs),
            )
        except TickConflictError:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (pool.submit(advance), pool.submit(advance))
        outcomes = sorted(future.result() for future in futures)

    assert outcomes == ["committed", "conflict"]
    assert PostgresPersistence(database_url).load_world(world.id.value).time.tick == 1
    assert _count(database_url, "cliova_completed_ticks") == 1


def test_history_event_ids_and_causal_ids_round_trip_unchanged(database_url: str) -> None:
    world, subject = configured_world(world_key="history-test")
    repository = PostgresPersistence(database_url)
    repository.create_world(world)
    repository.queue_input(world.id.value, submit(subject))

    result = PersistedTickService(directive_engine(), repository).advance_world(
        world.id.value,
        expected_tick=0,
    )
    loaded = repository.load_history(world.id.value)

    expected = {event.id: event for event in result.events}
    actual = {event.id: event for event in loaded.events}
    assert actual == expected
    queued_event = next(event for event in loaded.events if event.kind == "directive-queued")
    submitted_event = next(event for event in loaded.events if event.kind == "directive-submitted")
    assert queued_event.cause_event_ids == (submitted_event.id,)
